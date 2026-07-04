import io

import qrcode
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.services.file_service import FILES
from src.services.modules.upload import UploadService


class QRService:
    def __init__(self, upload_service: UploadService | None = None) -> None:
        self.upload_service = upload_service or UploadService()

    def build_qr_stream(self, request: Request, file_id: str):
        portal_url = f"{self.upload_service.public_base_url(request)}/portal/{file_id}"
        img = qrcode.make(portal_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")
