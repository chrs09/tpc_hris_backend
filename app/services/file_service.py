import os
import uuid
import mimetypes
from io import BytesIO
from datetime import datetime

import boto3
from azure.storage.blob import BlobServiceClient, ContentSettings
from PIL import Image, ImageDraw, ImageFont

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
    proof of when and exactly where it was taken. Matches the same
    watermarking done on mobile-captured photos. Only touches image
    uploads; anything else (or any Pillow failure) passes through
    untouched rather than blocking the action."""
    try:
        content_type = getattr(file, "content_type", "") or ""
        if not content_type.startswith("image/"):
            return file

        file.file.seek(0)
        image = Image.open(file.file)
        image = image.convert("RGB")

        draw = ImageDraw.Draw(image)
        lines = [
            utc_to_ph(datetime.utcnow()).strftime("%b %d, %Y %I:%M %p") + " PHT"
        ]
        if lat is not None and long is not None:
            lines.append(f"GPS: {lat:.6f}, {long:.6f}")
        if geofence_label:
            lines.append(geofence_label)

        try:
            font = ImageFont.truetype("arial.ttf", size=max(16, image.width // 45))
        except Exception:
            font = ImageFont.load_default()

        line_metrics = []
        max_text_w = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            line_metrics.append((line, w, h))
            max_text_w = max(max_text_w, w)

        padding = 8
        line_spacing = 4
        total_text_h = sum(h for _, _, h in line_metrics) + line_spacing * (
            len(line_metrics) - 1
        )

        bar_top = image.height - total_text_h - padding * 2
        draw.rectangle([0, bar_top, image.width, image.height], fill=(0, 0, 0))

        y = bar_top + padding
        for line, w, h in line_metrics:
            draw.text(
                (image.width - w - padding, y),
                line,
                fill=(255, 255, 255),
                font=font,
            )
            y += h + line_spacing

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)

        file.file = buffer
        return file
    except Exception:
        try:
            file.file.seek(0)
        except Exception:
            pass
        return file


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
            return self._upload_azure(file, folder_path)

        if self.storage == "s3":
            return self._upload_s3(file, folder_path)

        return self._upload_local(file, folder_path)

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
