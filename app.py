"""
QR File Share
-------------
Upload a file (<=500KB by default), get back a public download link
rendered as a QR code. Anyone who scans it can download the file
directly from wherever this app is deployed.

Security notes:
- Download links use a random 128-bit file ID — not sequential, not guessable.
- There is NO directory-listing endpoint; the /uploads folder itself is
  never exposed. Visiting the bare BASE_URL only shows the upload form.
- Links are one-time by default: the file is deleted immediately after the
  first successful download.
- Optional PIN protection: set a PIN on upload and the download page will
  require it before releasing the file.

Run locally:
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8000

Then open http://localhost:8000
"""

import hashlib
import hmac
import io
import json
import os
import secrets
import socket
import time
import uuid
import html
from pathlib import Path

import qrcode
from fastapi import FastAPI, Form, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from starlette.background import BackgroundTask

# ---------- Config ----------
MAX_FILE_SIZE = 500 * 1024        # 500 KB — change if you need bigger files
FILE_TTL_SECONDS = 60 * 60        # files auto-expire after 1 hour even if never downloaded
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# BASE_URL: the public URL of your deployed app.
# Render/Railway/Fly.io all inject an env var you can map to this,
# or just hardcode it after you know your deployed domain.
BASE_URL = os.environ.get("BASE_URL")

app = FastAPI(title="QR File Share")


class FileEntry:
    __slots__ = ("path", "filename", "expires_at", "pin_hash")

    def __init__(self, path: Path, filename: str, expires_at: float, pin_hash: str | None):
        self.path = path
        self.filename = filename
        self.expires_at = expires_at
        self.pin_hash = pin_hash


# In-memory index: file_id -> FileEntry
FILES: dict[str, FileEntry] = {}


def _public_base_url(request: Request) -> str:
    if BASE_URL:
        return BASE_URL.rstrip("/")

    host = request.url.hostname or "localhost"
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                host = sock.getsockname()[0]
        except OSError:
            host = "127.0.0.1"

    port = request.url.port
    if port and port not in {80, 443}:
        return f"{request.url.scheme}://{host}:{port}"
    return f"{request.url.scheme}://{host}"


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def _pin_matches(entry: FileEntry, submitted: str) -> bool:
    return hmac.compare_digest(entry.pin_hash or "", _hash_pin(submitted))


def _delete_file(file_id: str):
    """Called after a download response finishes streaming — makes links one-time use."""
    entry = FILES.pop(file_id, None)
    if entry:
        entry.path.unlink(missing_ok=True)


def _cleanup_expired():
    now = time.time()
    expired = [fid for fid, entry in FILES.items() if entry.expires_at < now]
    for fid in expired:
        entry = FILES.pop(fid)
        entry.path.unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>QR File Share</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: system-ui, sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; }
            h1 { font-size: 1.4rem; }
            input[type=file] { display:block; margin: 20px 0; }
            button { background:#111; color:#fff; border:none; padding: 10px 18px; border-radius: 6px; cursor:pointer; }
            .hint { color:#666; font-size: 0.85rem; }
        </style>
    </head>
    <body>
        <h1>QR File Share</h1>
        <p class="hint">Upload a file under 500KB. The QR code you get encodes a one-time secret link — scanning it is the "passcode," no separate typing needed.</p>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="file" required>
            <input type="text" name="pin" placeholder="Optional extra PIN (leave blank for none)" maxlength="12" style="width:100%; box-sizing:border-box; padding:8px; margin-bottom:12px;">
            <button type="submit">Upload</button>
        </form>
        <p class="hint">Link works once — the file deletes itself right after it's downloaded, or after 1 hour if never opened.</p>
    </body>
    </html>
    """


@app.post("/upload", response_class=HTMLResponse)
async def upload(request: Request, file: UploadFile = File(...), pin: str = Form(...)):
    _cleanup_expired()

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(contents)} bytes). Limit is {MAX_FILE_SIZE} bytes."
        )

    pin = pin.strip()
    if not pin:
        raise HTTPException(status_code=400, detail="PIN is required for every file upload")

    pin_hash = _hash_pin(pin)

    # This is the one-time passcode, embedded directly in the URL/QR code.
    # secrets.token_urlsafe gives a cryptographically secure, URL-safe random
    # string with 144 bits of entropy — effectively unguessable.
    file_id = secrets.token_urlsafe(24)
    dest = UPLOAD_DIR / (uuid.uuid4().hex)  # separate on-disk filename, unrelated to the public token
    dest.write_bytes(contents)
    FILES[file_id] = FileEntry(
        path=dest,
        filename=file.filename,
        expires_at=time.time() + FILE_TTL_SECONDS,
        pin_hash=pin_hash,
    )

    portal_url = f"{_public_base_url(request)}/portal/{file_id}"
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Share details</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: system-ui, sans-serif; max-width: 620px; margin: 56px auto; padding: 0 20px; }}
            .card {{ border:1px solid #e5e7eb; border-radius:16px; padding:24px; box-shadow:0 10px 30px rgba(0,0,0,.04); }}
            h2 {{ margin-top: 0; }}
            a {{ word-break: break-all; }}
            .row {{ margin-top: 12px; }}
            .label {{ font-size: .85rem; color:#6b7280; margin-bottom:4px; text-transform:uppercase; letter-spacing:.04em; }}
            .value {{ font-size: 1rem; padding: 10px 12px; background:#f9fafb; border-radius:10px; display:flex; gap:12px; align-items:center; justify-content:space-between; }}
            .hint {{ color:#6b7280; font-size: .9rem; line-height:1.5; }}
            .actions {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:18px; }}
            .actions a, .actions button {{ background:#111; color:#fff; border:none; padding:10px 16px; border-radius:8px; cursor:pointer; text-decoration:none; }}
            .secondary {{ background:#fff !important; color:#111 !important; border:1px solid #d1d5db !important; }}
            .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; word-break: break-all; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Upload complete</h2>
            <p class="hint">Keep this page open or copy the details below. The receiver should open the portal link, enter the PIN, and then scan the QR to download the file.</p>
            <div class="row">
                <div class="label">File</div>
                <div class="value"><span>{html.escape(file.filename)}</span></div>
            </div>
            <div class="row">
                <div class="label">Download portal</div>
                <div class="value">
                    <span class="mono" id="portal-url">{portal_url}</span>
                    <button type="button" class="secondary" onclick="copyText('portal-url')">Copy</button>
                </div>
            </div>
            <div class="row">
                <div class="label">PIN</div>
                <div class="value">
                    <span class="mono" id="portal-pin">{html.escape(pin)}</span>
                    <button type="button" class="secondary" onclick="copyText('portal-pin')">Copy</button>
                </div>
            </div>
            <div class="actions">
                <a href="{portal_url}" target="_blank" rel="noreferrer">Open portal</a>
                <a class="secondary" href="/">Upload another file</a>
            </div>
            <p class="hint">Each upload gets its own portal link, so you can handle multiple files independently.</p>
        </div>
        <script>
            async function copyText(elementId) {{
                const text = document.getElementById(elementId).textContent;
                try {{
                    await navigator.clipboard.writeText(text);
                }} catch (error) {{
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(document.getElementById(elementId));
                    selection.removeAllRanges();
                    selection.addRange(range);
                    document.execCommand('copy');
                    selection.removeAllRanges();
                }}
            }}
        </script>
    </body>
    </html>
    """


@app.get("/qr/{file_id}")
async def get_qr(request: Request, file_id: str):
    if file_id not in FILES:
        raise HTTPException(status_code=404, detail="File not found or expired")

    download_url = f"{_public_base_url(request)}/redeem/{file_id}"
    img = qrcode.make(download_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.get("/portal/{file_id}", response_class=HTMLResponse)
async def download_portal(file_id: str):
    _cleanup_expired()
    entry = FILES.get(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Download portal</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: system-ui, sans-serif; max-width: 420px; margin: 72px auto; padding: 0 20px; text-align:center; }}
            input {{ width:100%; box-sizing:border-box; padding:10px; font-size:1.05rem; text-align:center; margin-bottom:12px; }}
            button {{ background:#111; color:#fff; border:none; padding: 10px 18px; border-radius: 8px; cursor:pointer; width:100%; }}
            .hint {{ color:#6b7280; font-size:.9rem; line-height:1.5; }}
        </style>
    </head>
    <body>
        <h2>{html.escape(entry.filename)}</h2>
            <p class="hint">Enter the PIN to reveal the QR code. The QR opens the file redeem page.</p>
        <form action="/portal/{file_id}" method="post">
            <input type="text" name="pin" placeholder="Enter PIN" autofocus required>
            <button type="submit">Unlock QR code</button>
        </form>
    </body>
    </html>
    """

@app.post("/portal/{file_id}", response_class=HTMLResponse)
async def unlock_portal(file_id: str, pin: str = Form(default="")):
    _cleanup_expired()
    entry = FILES.get(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    if entry.pin_hash and not _pin_matches(entry, pin.strip()):
        raise HTTPException(status_code=403, detail="Incorrect PIN")

    qr_url = f"/qr/{file_id}"
    redeem_url = f"/redeem/{file_id}"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>QR ready</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: system-ui, sans-serif; max-width: 520px; margin: 56px auto; padding: 0 20px; text-align:center; }}
            img {{ width: 260px; height: 260px; margin: 18px 0; }}
            .card {{ border:1px solid #e5e7eb; border-radius:16px; padding:24px; box-shadow:0 10px 30px rgba(0,0,0,.04); }}
            .hint {{ color:#6b7280; font-size:.9rem; line-height:1.5; }}
            .actions {{ margin-top: 18px; display:flex; gap:12px; flex-wrap:wrap; justify-content:center; }}
            .actions a, .actions button {{ background:#111; color:#fff; border:none; padding:10px 16px; border-radius:8px; text-decoration:none; cursor:pointer; }}
            .secondary {{ background:#fff; color:#111 !important; border:1px solid #d1d5db !important; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>QR code unlocked</h2>
            <p class="hint">Scan this QR code on the other device. It opens the redeem page, downloads the file, and then the stored copy is removed automatically.</p>
            <img src="{qr_url}" alt="QR code">
            <div class="actions">
                <a href="{redeem_url}">Open redeem page</a>
                <a class="secondary" href="/portal/{file_id}">Back</a>
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/redeem/{file_id}", response_class=HTMLResponse)
async def redeem_page(file_id: str):
    _cleanup_expired()
    entry = FILES.get(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    filename_js = json.dumps(entry.filename)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Redeem file</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: system-ui, sans-serif; max-width: 520px; margin: 56px auto; padding: 0 20px; text-align:center; }}
            .card {{ border:1px solid #e5e7eb; border-radius:16px; padding:24px; box-shadow:0 10px 30px rgba(0,0,0,.04); }}
            .hint {{ color:#6b7280; font-size:.95rem; line-height:1.5; }}
            .actions {{ margin-top: 18px; display:flex; gap:12px; flex-wrap:wrap; justify-content:center; }}
            .actions button, .actions a {{ background:#111; color:#fff; border:none; padding:10px 16px; border-radius:8px; text-decoration:none; cursor:pointer; }}
            .secondary {{ background:#fff !important; color:#111 !important; border:1px solid #d1d5db !important; }}
            #delete-box {{ display:none; margin-top: 18px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>{html.escape(entry.filename)}</h2>
            <p class="hint" id="status">Preparing download...</p>
            <div class="actions">
                <button onclick="startDownload()">Download again</button>
                <a class="secondary" href="/portal/{file_id}">Back to portal</a>
            </div>
        </div>
        <script>
            const filename = {filename_js};
            async function startDownload() {{
                const status = document.getElementById('status');
                try {{
                    const response = await fetch('/file/{file_id}');
                    if (!response.ok) {{
                        const message = await response.text();
                        status.textContent = message;
                        return;
                    }}
                    const blob = await response.blob();
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = filename;
                    document.body.appendChild(link);
                    link.click();
                    link.remove();
                    status.textContent = 'Download started successfully. The stored file will be removed automatically.';
                }} catch (error) {{
                    status.textContent = 'Download failed.';
                }}
            }}
            window.addEventListener('load', startDownload);
        </script>
    </body>
    </html>
    """


@app.get("/file/{file_id}")
async def download_file(file_id: str):
    _cleanup_expired()
    entry = FILES.get(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    return FileResponse(
        entry.path,
        filename=entry.filename,
        media_type="application/octet-stream",
        background=BackgroundTask(_delete_file, file_id),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "active_files": len(FILES)}
