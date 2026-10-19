import hashlib
import os
import secrets
import uuid
import mimetypes
from io import BytesIO
from datetime import datetime

import boto3
from azure.storage.blob import BlobServiceClient, ContentSettings
from PIL import Image, ImageOps

from app.core.config import settings
from app.utils.timezone import utc_to_ph


def _watermark_timestamp(
    file,
    geofence_label: str | None = None,
    lat: float | None = None,
    long: float | None = None,
):
    """Burns the current PH timestamp, the raw GPS coordinates (when
    available), and a geofence/location line (e.g. "TPC Yard (42m)" or
    "Outside geofence - nearest: ...") onto the bottom-right corner of an
    uploaded photo before storage, so the stored image itself carries
    proof of when and exactly where it was taken (panel with the Tytan
    Prime logo, drawn by app/services/watermark.py). Only touches image
    uploads; anything else (or any Pillow failure) passes through
    untouched rather than blocking the action."""
    try:
        content_type = getattr(file, "content_type", "") or ""
        if not content_type.startswith("image/"):
            return file

        file.file.seek(0)
        image = Image.open(file.file)
        # Phones (iPhones especially) save photos sideways with an EXIF
        # "rotate me" tag. Re-saving below drops that tag, so turn the
        # pixels upright first -- otherwise the stored selfie is rotated
        # and face matching scores it low.
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")

        captured_utc = datetime.utcnow()
        captured_ph = utc_to_ph(captured_utc)
        stamp_time = captured_ph.strftime("%b %d, %Y %I:%M %p")

        # This photo's own code: on the stamp and in the faint pattern over
        # the whole photo, and recorded with the file's SHA-256 (PhotoSeal)
        # so a cropped / edited / re-pasted copy can be told apart.
        ref = _new_photo_ref()
        info = {
            "when": captured_ph.strftime("%A, %m/%d/%Y %I:%M %p") + " GMT+08:00",
            "label": geofence_label,
            "ref": ref,
            "tile_text": f"TYTAN PRIME · {ref} · {stamp_time}",
        }
        if lat is not None and long is not None:
            info["lat"], info["lng"] = lat, long
            # Map with a pin + street address (OpenStreetMap, cached; any
            # failure just leaves them out).
            from app.services.map_snapshot import map_thumbnail, reverse_geocode

            place = reverse_geocode(lat, long)
            if place:
                info["title"], info["address"] = place.get("title"), place.get("address")
            info["map"] = map_thumbnail(lat, long)

        # GPS-camera style stamp + the pattern (look: app/services/watermark.py).
        from app.services.watermark import stamp

        image = stamp(image, info)

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        data = buffer.getvalue()
        buffer.seek(0)
        file._seal_id = _save_photo_seal(
            ref, hashlib.sha256(data).hexdigest(), captured_utc, lat, long, geofence_label
        )

        file.file = buffer
        return file
    except Exception:
        try:
            file.file.seek(0)
        except Exception:
            pass
        return file


def _new_photo_ref() -> str:
    # e.g. TP-7F3K-92QD (no 0/O/1/I to keep it easy to read out)
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"TP-{code[:4]}-{code[4:]}"


def _save_photo_seal(ref, sha256, captured_utc, lat, long, label):
    """Records the stamped photo (own session: callers commit their own
    work separately). Never blocks the upload -- returns the id or None."""
    try:
        from app.core.database import SessionLocal
        from app.models.photo_seal import PhotoSeal

        db = SessionLocal()
        try:
            seal = PhotoSeal(
                ref=ref,
                sha256=sha256,
                captured_at=captured_utc,
                latitude=lat,
                longitude=long,
                label=label,
            )
            db.add(seal)
            db.commit()
            return seal.id
        finally:
            db.close()
    except Exception:
        return None


def _attach_seal_url(file, url):
    seal_id = getattr(file, "_seal_id", None)
    if not seal_id or not url:
        return
    try:
        from app.core.database import SessionLocal
        from app.models.photo_seal import PhotoSeal

        db = SessionLocal()
        try:
            db.query(PhotoSeal).filter(PhotoSeal.id == seal_id).update({"file_url": url})
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


class FileService:
    def __init__(self):
        self.storage = settings.FILE_STORAGE

        if self.storage == "azure":
            self.client = BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            )

        if self.storage == "s3":
            self.client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )

    # ===============================
    # GENERIC UPLOAD HANDLER
    # ===============================

    def upload(self, file, folder_path):
        if self.storage == "azure":
            url = self._upload_azure(file, folder_path)
        elif self.storage == "s3":
            url = self._upload_s3(file, folder_path)
        else:
            url = self._upload_local(file, folder_path)
        # A stamped photo: remember where it's stored (Verify Photo).
        _attach_seal_url(file, url)
        return url

    # ===============================
    # LOCAL STORAGE
    # ===============================

    def _upload_local(self, file, folder_path):
        base_path = os.path.join(settings.UPLOAD_FOLDER, folder_path)
        os.makedirs(base_path, exist_ok=True)

        extension = (
            file.filename.split(".")[-1].lower()
            if "." in file.filename
            else "bin"
        )

        filename = f"{uuid.uuid4()}.{extension}"
        file_path = os.path.join(base_path, filename)

        file.file.seek(0)

        with open(file_path, "wb") as buffer:
            buffer.write(file.file.read())

        # URL used by the frontend
        url_path = f"/uploads/{folder_path}/{filename}"

        return f"{settings.API_BASE_URL.rstrip('/')}{url_path}"

    
    # ===============================
    # AZURE BLOB STORAGE
    # ===============================

    def _upload_azure(self, file, folder_path):
        extension = (
            file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
        )
        filename = f"{uuid.uuid4()}.{extension}"
        blob_path = f"{folder_path}/{filename}"

        content_type, _ = mimetypes.guess_type(file.filename)
        if not content_type:
            content_type = (
                getattr(file, "content_type", None) or "application/octet-stream"
            )

        blob_client = self.client.get_blob_client(
            container=settings.AZURE_CONTAINER,
            blob=blob_path,
        )

        file.file.seek(0)
        blob_client.upload_blob(
            file.file,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

        return blob_client.url

    # ===============================
    # AWS S3 STORAGE
    # ===============================

    def _upload_s3(self, file, folder_path):
        extension = (
            file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
        )
        filename = f"{uuid.uuid4()}.{extension}"
        key = f"{folder_path}/{filename}"

        content_type, _ = mimetypes.guess_type(file.filename)
        if not content_type:
            content_type = (
                getattr(file, "content_type", None) or "application/octet-stream"
            )

        content_disposition = (
            "inline"
            if content_type == "application/pdf" or content_type.startswith("image/")
            else "attachment"
        )

        file.file.seek(0)
        self.client.upload_fileobj(
            file.file,
            settings.AWS_BUCKET_NAME,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "ContentDisposition": content_disposition,
            },
        )

        return f"https://{settings.AWS_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"

    # ===============================
    # SPECIFIC FILE TYPES
    # ===============================

    # ===============================
    # TRIP FILES
    # ===============================

    def upload_trip_start_photo(
        self, file, trip_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload photo taken when starting a trip.

        Structure:
        trips/{trip_id}/start/{filename}
        """
        folder = f"trips/{trip_id}/start"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )


    def upload_trip_pod_photo(
        self, file, trip_id, stop_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload Proof of Delivery (POD) for a specific trip stop.

        Structure:
        trips/{trip_id}/pod/{stop_id}/{filename}
        """
        folder = f"trips/{trip_id}/pod/{stop_id}"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )


    def upload_trip_end_photo(
        self, file, trip_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload stamped invoice / end-of-trip photo.

        Structure:
        trips/{trip_id}/end/{filename}
        """
        folder = f"trips/{trip_id}/end"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )


    def upload_gps_log_photo(self, file, trip_id):
        folder = f"gps_logs/{trip_id}"
        return self.upload(file, folder)

    def upload_trip_checkout_invoice(
        self, file, trip_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload the Invoice photo taken during the Checkout step.

        Structure:
        trips/{trip_id}/checkout/invoice/{filename}
        """
        folder = f"trips/{trip_id}/checkout/invoice"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )

    def upload_trip_checkout_lm(
        self, file, trip_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload the LM (loading manifest) photo taken during the Checkout
        step.

        Structure:
        trips/{trip_id}/checkout/lm/{filename}
        """
        folder = f"trips/{trip_id}/checkout/lm"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )

    def upload_trip_checkout_lm_stamped(
        self, file, trip_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload the LM photo physically stamped/marked "checkout" -- proof
        the checkout step happened, separate from the plain LM photo.

        Structure:
        trips/{trip_id}/checkout/lm_stamped/{filename}
        """
        folder = f"trips/{trip_id}/checkout/lm_stamped"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )

    def upload_trip_unloading_photo(
        self, file, trip_id, stop_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload the Start Unloading photo for a specific trip stop.

        Structure:
        trips/{trip_id}/unloading/{stop_id}/{filename}
        """
        folder = f"trips/{trip_id}/unloading/{stop_id}"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )

    def upload_trip_back_to_source_photo(
        self, file, trip_id, geofence_label=None, lat=None, long=None
    ):
        """
        Upload the LM-with-Perma photo taken during the Back to Source
        step.

        Structure:
        trips/{trip_id}/back_to_source/{filename}
        """
        folder = f"trips/{trip_id}/back_to_source"
        return self.upload(
            _watermark_timestamp(file, geofence_label, lat, long), folder
        )

    # ===============================
    # TICKET FILES
    # ===============================

    def upload_ticket_image(self, file, ticket_id):
        """
        Upload a screenshot/reference image attached to a ticket.

        Structure:
        tickets/{ticket_id}/{filename}
        """
        folder = f"tickets/{ticket_id}"
        return self.upload(file, folder)

    # ===============================
    # VEHICLE FILES
    # ===============================

    def upload_vehicle_cr(self, file, vehicle_unit_id):
        """
        Upload a vehicle's CR (Certificate of Registration) document -- a
        live link to the actual scanned document. CR and OR are two
        separate physical documents, uploaded/stored separately.

        Structure:
        vehicles/{vehicle_unit_id}/cr/{filename}
        """
        folder = f"vehicles/{vehicle_unit_id}/cr"
        return self.upload(file, folder)

    def upload_vehicle_or(self, file, vehicle_unit_id):
        """
        Upload a vehicle's OR (Official Receipt) document -- a live link
        to the actual scanned document.

        Structure:
        vehicles/{vehicle_unit_id}/or/{filename}
        """
        folder = f"vehicles/{vehicle_unit_id}/or"
        return self.upload(file, folder)

    # ===============================
    # STORE FILES
    # ===============================

    def upload_store_photo(self, file, store_id):
        """
        Upload a photo of the actual physical store.

        Structure:
        stores/{store_id}/photo/{filename}
        """
        folder = f"stores/{store_id}/photo"
        return self.upload(file, folder)

    # ===============================
    # EMPLOYEE FILES
    # ===============================

    def upload_employee_profile(self, file, employee_id):
        folder = f"employees/{employee_id}/profile"
        return self.upload(file, folder)

    def upload_employee_resume(self, file, employee_id):
        folder = f"employees/{employee_id}/resume"
        return self.upload(file, folder)

    def upload_employee_document(self, file, employee_id, doc_type):
        folder = f"employees/{employee_id}/{doc_type}"
        return self.upload(file, folder)

    def upload_employee_photo(self, file, employee_id):
        folder = f"employees/{employee_id}"
        return self.upload(file, folder)

    # ===============================
    # OVERTIME FILES
    # ===============================

    def upload_overtime_selfie(self, file, overtime_request_id, geofence_label=None):
        """
        Upload the live selfie taken when an employee clocks in to
        callback overtime.

        Structure:
        overtime/{overtime_request_id}/selfie/{filename}
        """
        folder = f"overtime/{overtime_request_id}/selfie"
        return self.upload(_watermark_timestamp(file, geofence_label), folder)
