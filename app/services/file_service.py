import os
import uuid
import mimetypes
import boto3
from azure.storage.blob import BlobServiceClient, ContentSettings
from app.core.config import settings


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
        base_path = f"uploads/{folder_path}"
        os.makedirs(base_path, exist_ok=True)

        extension = (
            file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
        )
        filename = f"{uuid.uuid4()}.{extension}"
        file_path = f"{base_path}/{filename}"

        file.file.seek(0)
        with open(file_path, "wb") as buffer:
            buffer.write(file.file.read())

        return f"{settings.API_BASE_URL}/{file_path}"

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

    def upload_trip_start_photo(self, file, trip_id):
        folder = f"trips/{trip_id}/start"
        return self.upload(file, folder)

    def upload_trip_stop_photo(self, file, trip_id):
        folder = f"trips/{trip_id}/stop"
        return self.upload(file, folder)

    def upload_gps_log_photo(self, file, trip_id):
        folder = f"gps_logs/{trip_id}"
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
