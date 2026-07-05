import html
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from src.services.file_service import file_service
from src.services.modules.notify import notify_service
from src.services.modules.rate_limit import pin_rate_limiter
from src.services.modules.upload import FileTooLarge

app = FastAPI(title="QR File Share")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


def _notification_response(message: str, status_code: int = 200, notification_type: str = "success", headers: dict | None = None) -> Response:
    response_headers = {
        "X-Notification-Type": notification_type,
        "X-Notification-Message": message,
    }
    if headers:
        response_headers.update(headers)
    return Response(status_code=status_code, headers=response_headers)


def _render_frontend_template(template_name: str, **context: str) -> str:
    template_path = FRONTEND_DIR / template_name
    content = template_path.read_text(encoding="utf-8")
    for key, value in context.items():
        content = content.replace(f"__{key.upper()}__", value)
    return content


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
    return _render_frontend_template("index.html")


@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...), pin: str = Form(...), contact: str = Form(default="")):
    try:
        payload = file_service.create_file(file.filename or "upload", await file.read(), pin, request)
    except FileTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    message = "Upload complete."
    contact = contact.strip()
    if contact:
        try:
            notify_service.send_share_details(contact, payload["filename"], payload["portal_url"], payload["pin"])
            message = f"Upload complete. Share details sent to {contact}."
        except Exception as exc:
            message = f"Upload complete, but could not notify {contact}: {exc}"

    return _notification_response(
        message,
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

    return _render_frontend_template("portal.html", filename=html.escape(entry.filename), file_id=file_id)


@app.post("/portal/{file_id}", response_class=HTMLResponse)
async def unlock_portal(request: Request, file_id: str, pin: str = Form(default="")):
    entry = file_service.get_entry(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    client_ip = request.client.host if request.client else "unknown"
    if not pin_rate_limiter.allow_attempt(file_id, client_ip):
        raise HTTPException(status_code=429, detail="Too many incorrect PIN attempts. Please wait and try again.")

    if entry.pin_hash and not file_service.pin_matches(entry, pin.strip()):
        pin_rate_limiter.record_failure(file_id, client_ip)
        raise HTTPException(status_code=403, detail="Incorrect PIN")

    pin_rate_limiter.reset(file_id, client_ip)
    return _render_frontend_template(
        "redeem.html",
        filename=html.escape(entry.filename),
        filename_js=json.dumps(entry.filename),
        file_id=file_id,
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
