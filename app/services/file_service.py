import os
import uuid
from azure.storage.blob import BlobServiceClient
from app.core.config import settings


class FileService:

    def __init__(self):
        self.storage = settings.FILE_STORAGE

        if self.storage == "azure":
            self.client = BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            )

    # ===============================
    # GENERIC UPLOAD HANDLER
    # ===============================

    def upload(self, file, folder_path):

        if self.storage == "azure":
            return self._upload_azure(file, folder_path)

        return self._upload_local(file, folder_path)

    # ===============================
    # LOCAL STORAGE
    # ===============================

    def _upload_local(self, file, folder_path):

        base_path = f"uploads/{folder_path}"
        os.makedirs(base_path, exist_ok=True)

        extension = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{extension}"

        file_path = f"{base_path}/{filename}"

        with open(file_path, "wb") as buffer:
            buffer.write(file.file.read())

        return file_path

    # ===============================
    # AZURE BLOB STORAGE
    # ===============================

    def _upload_azure(self, file, folder_path):

        extension = file.filename.split(".")[-1]
        filename = f"{uuid.uuid4()}.{extension}"

        blob_path = f"{folder_path}/{filename}"

        blob_client = self.client.get_blob_client(
            container=settings.AZURE_CONTAINER, blob=blob_path
        )

        blob_client.upload_blob(file.file, overwrite=True)

        return blob_client.url

    # ===============================
    # SPECIFIC FILE TYPES
    # ===============================

    def upload_trip_start_photo(self, file, trip_id):
        folder = f"trips/{trip_id}/start"
        return self.upload(file, folder)

    def upload_trip_stop_photo(self, file, trip_id):
        folder = f"trips/{trip_id}/stop"
        return self.upload(file, folder)

    def upload_employee_photo(self, file, employee_id):
        folder = f"employees/{employee_id}"
        return self.upload(file, folder)

    def upload_gps_log_photo(self, file, trip_id):
        folder = f"gps_logs/{trip_id}"
        return self.upload(file, folder)
