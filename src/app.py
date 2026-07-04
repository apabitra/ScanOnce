import html
import io
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from src.services.file_service import file_service

app = FastAPI(title="QR File Share")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _notification_response(message: str, status_code: int = 200, notification_type: str = "success", headers: dict | None = None) -> Response:
    response_headers = {
        "X-Notification-Type": notification_type,
        "X-Notification-Message": message,
    }
    if headers:
        response_headers.update(headers)
    return Response(status_code=status_code, headers=response_headers)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> PlainTextResponse:
    return PlainTextResponse(
        str(exc.detail),
        status_code=exc.status_code,
        headers={
            "X-Notification-Type": "error",
            "X-Notification-Message": str(exc.detail),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> PlainTextResponse:
    return PlainTextResponse(
        "Please provide a valid upload request.",
        status_code=422,
        headers={
            "X-Notification-Type": "error",
            "X-Notification-Message": "Please provide a valid upload request.",
        },
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...), pin: str = Form(...)):
    try:
        payload = file_service.create_file(file.filename or "upload", await file.read(), pin, request)
    except ValueError as exc:
        raise HTTPException(status_code=400 if "PIN" in str(exc) else 413, detail=str(exc)) from exc

    return _notification_response(
        "Upload complete.",
        headers={
            "X-Share-URL": payload["portal_url"],
            "X-Share-PIN": payload["pin"],
        },
    )


@app.get("/qr/{file_id}")
async def get_qr(request: Request, file_id: str):
    entry = file_service.get_entry(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found or expired")
    return file_service.build_qr_stream(request, file_id)


@app.get("/portal/{file_id}", response_class=HTMLResponse)
async def download_portal(file_id: str):
    entry = file_service.get_entry(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    template = (FRONTEND_DIR / "portal.html").read_text(encoding="utf-8")
    return template.replace("__FILENAME__", html.escape(entry.filename)).replace("__FILE_ID__", file_id)


@app.post("/portal/{file_id}", response_class=HTMLResponse)
async def unlock_portal(file_id: str, pin: str = Form(default="")):
    entry = file_service.get_entry(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    allowed, lockout_message = file_service.check_pin_access(entry)
    if not allowed:
        raise HTTPException(status_code=429, detail=lockout_message or "PIN is temporarily locked")

    if entry.pin_hash and not file_service.pin_matches(entry, pin.strip()):
        allowed, lockout_message = file_service.record_failed_pin_attempt(entry)
        if not allowed:
            raise HTTPException(status_code=429, detail=lockout_message or "PIN is temporarily locked")
        raise HTTPException(status_code=403, detail="Incorrect PIN")

    template = (FRONTEND_DIR / "unlock.html").read_text(encoding="utf-8")
    return template.replace("__FILE_ID__", file_id)


@app.get("/redeem/{file_id}", response_class=HTMLResponse)
async def redeem_page(file_id: str):
    entry = file_service.get_entry(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    template = (FRONTEND_DIR / "redeem.html").read_text(encoding="utf-8")
    return (
        template.replace("__FILENAME__", html.escape(entry.filename))
        .replace("__FILENAME_JS__", json.dumps(entry.filename))
        .replace("__FILE_ID__", file_id)
    )


@app.get("/file/{file_id}")
async def download_file(file_id: str):
    try:
        return file_service.build_download_response(file_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/health")
async def health():
    return {"status": "ok", "active_files": file_service.active_file_count()}
