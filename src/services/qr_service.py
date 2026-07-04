import io

import qrcode
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.services.upload_service import UploadService


def build_qr_stream(request: Request, file_id: str, upload_service: UploadService | None = None):
    service = upload_service or UploadService()
    download_url = f"{service.public_base_url(request)}/redeem/{file_id}"
    img = qrcode.make(download_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
