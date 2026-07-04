import html
import io
import json
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from src.services.file_service import file_service

app = FastAPI(title="QR File Share")


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
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>QR File Share</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: system-ui, sans-serif; max-width: 520px; margin: 60px auto; padding: 0 20px; }
            h1 { font-size: 1.4rem; }
            input[type=file] { display:block; margin: 20px 0; }
            button { background:#111; color:#fff; border:none; padding: 10px 18px; border-radius: 6px; cursor:pointer; }
            .hint { color:#666; font-size: 0.85rem; }
            .notification { display:none; border:1px solid #d1d5db; border-radius: 14px; padding: 16px; margin-top: 18px; background:#f9fafb; box-shadow:0 10px 30px rgba(0,0,0,.04); }
            .notification.show { display:block; }
            .notification .label { font-size: .8rem; color:#6b7280; text-transform:uppercase; letter-spacing:.04em; margin-bottom: 6px; }
            .notification .value { background:#fff; border-radius:10px; padding:10px 12px; margin-top:8px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; word-break:break-all; }
            .notification .actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
            .notification .actions button, .notification .actions a { background:#111; color:#fff; border:none; padding:8px 12px; border-radius:8px; cursor:pointer; text-decoration:none; }
            .notification .actions .secondary { background:#fff !important; color:#111 !important; border:1px solid #d1d5db !important; }
            .progress-shell { display:none; width:100%; height:8px; border-radius:999px; overflow:hidden; background:#e5e7eb; margin-top:10px; }
            .progress-bar { height:100%; width:0%; background:#111; transition:width 0.2s ease; }
            .progress-label { margin-top:6px; font-size:0.85rem; color:#4b5563; }
            #status-message { margin-top: 10px; color:#b91c1c; font-size: .9rem; }
            #status-message[data-type="success"] { color:#166534; }
        </style>
    </head>
    <body>
        <h1>QR File Share</h1>
        <p class="hint">Upload a file under 500KB. The QR code you get encodes a one-time secret link — scanning it is the "passcode," no separate typing needed.</p>
        <form id="upload-form" enctype="multipart/form-data">
            <input type="file" name="file" required>
            <input type="text" name="pin" placeholder="PIN required for every upload" maxlength="12" style="width:100%; box-sizing:border-box; padding:8px; margin-bottom:12px;">
            <button type="submit">Upload</button>
        </form>
        <div id="status-message" role="status"></div>
        <div class="progress-shell" id="upload-progress-shell">
            <div class="progress-bar" id="upload-progress-bar"></div>
        </div>
        <div class="progress-label" id="upload-progress-label"></div>
        <div id="share-notification" class="notification" role="status" aria-live="polite">
            <div class="label">Share details</div>
            <div class="label">Public URL</div>
            <div class="value" id="share-url"></div>
            <div class="label">PIN</div>
            <div class="value" id="share-pin"></div>
            <div class="actions">
                <button type="button" onclick="copyText('share-url')">Copy URL</button>
                <button type="button" onclick="copyText('share-pin')">Copy PIN</button>
                <button type="button" class="secondary" onclick="dismissNotification()">Acknowledge</button>
            </div>
        </div>
        <p class="hint">Link works once — the file deletes itself right after it's downloaded, or after 1 hour if never opened.</p>
        <script>
            const form = document.getElementById('upload-form');
            const notification = document.getElementById('share-notification');
            const statusMessage = document.getElementById('status-message');
            const uploadProgressShell = document.getElementById('upload-progress-shell');
            const uploadProgressBar = document.getElementById('upload-progress-bar');
            const uploadProgressLabel = document.getElementById('upload-progress-label');

            function showStatus(message, type = 'error') {
                statusMessage.textContent = message;
                statusMessage.dataset.type = type;
            }

            function updateUploadProgress(percent, label) {
                uploadProgressShell.style.display = percent >= 0 ? 'block' : 'none';
                uploadProgressBar.style.width = `${Math.min(100, Math.max(0, percent))}%`;
                uploadProgressLabel.textContent = label || '';
            }

            form.addEventListener('submit', (event) => {
                event.preventDefault();
                const data = new FormData(form);
                showStatus('');
                notification.classList.remove('show');
                updateUploadProgress(0, 'Preparing upload...');

                const xhr = new XMLHttpRequest();
                xhr.open('POST', '/upload', true);
                xhr.upload.onprogress = (event) => {
                    if (event.lengthComputable) {
                        const percent = Math.round((event.loaded / event.total) * 100);
                        updateUploadProgress(percent, `Uploading ${percent}%`);
                    }
                };
                xhr.onload = () => {
                    updateUploadProgress(-1, '');
                    if (xhr.status >= 200 && xhr.status < 300) {
                        document.getElementById('share-url').textContent = xhr.getResponseHeader('X-Share-URL') || '';
                        document.getElementById('share-pin').textContent = xhr.getResponseHeader('X-Share-PIN') || '';
                        notification.classList.add('show');
                        showStatus(xhr.getResponseHeader('X-Notification-Message') || 'Upload complete.', 'success');
                    } else {
                        showStatus(xhr.responseText || 'Upload failed.', 'error');
                    }
                };
                xhr.onerror = () => {
                    updateUploadProgress(-1, '');
                    showStatus('Upload failed.', 'error');
                };
                xhr.send(data);
            });

            function dismissNotification() {
                notification.classList.remove('show');
                document.getElementById('share-url').textContent = '';
                document.getElementById('share-pin').textContent = '';
                form.reset();
                showStatus('');
                updateUploadProgress(-1, '');
                setTimeout(() => {
                    if (window.confirm('Upload complete. Close this window?')) {
                        window.close();
                    }
                }, 200);
            }

            async function copyText(elementId) {
                const text = document.getElementById(elementId).textContent;
                try {
                    await navigator.clipboard.writeText(text);
                } catch (error) {
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(document.getElementById(elementId));
                    selection.removeAllRanges();
                    selection.addRange(range);
                    document.execCommand('copy');
                    selection.removeAllRanges();
                }
            }
        </script>
    </body>
    </html>
    """


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
    entry = file_service.get_entry(file_id)
    if not entry:
        raise HTTPException(status_code=404, detail="File not found, already downloaded, or expired")

    if entry.pin_hash and not file_service.pin_matches(entry, pin.strip()):
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
                <button id="qr-close" class="secondary">Close this page</button>
            </div>
            <div class="finish-box">You can now close this page. Tap the button to close the app.</div>
        </div>
        <script>
            // Attempt to close the QR page when the user clicks the Close button.
            (function() {{
                const btn = document.getElementById('qr-close');
                if (!btn) return;
                btn.addEventListener('click', () => {{
                    try {{ window.close(); }} catch (e) {{}}
                    try {{ window.open('', '_self'); window.close(); }} catch (e) {{}}
                    // Fallback: navigate away so user can close the tab/window manually.
                    window.location.href = 'about:blank';
                }});
            }})();
        </script>
    </body>
    </html>
    """


@app.get("/redeem/{file_id}", response_class=HTMLResponse)
async def redeem_page(file_id: str):
    entry = file_service.get_entry(file_id)
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
            .progress-shell {{ display:none; width:100%; height:8px; border-radius:999px; overflow:hidden; background:#e5e7eb; margin-top:12px; }}
            .progress-bar {{ height:100%; width:0%; background:#111; transition:width 0.2s ease; }}
            .progress-label {{ margin-top:6px; font-size:0.85rem; color:#4b5563; }}
            #delete-box {{ display:none; margin-top: 18px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>{html.escape(entry.filename)}</h2>
            <div class="progress-shell" id="progress-shell">
                <div class="progress-bar" id="progress-bar"></div>
            </div>
            <div class="progress-label" id="progress-label">Preparing download...</div>
            <p class="hint" id="status">Preparing download...</p>
            <div class="actions">
                <button onclick="startDownload()">Download again</button>
                <a class="secondary" href="/portal/{file_id}">Back to portal</a>
            </div>
            <div class="finish-box" id="finish-box">Download will finish here. Close this page after the notification appears.</div>
        </div>
        <script>
            const filename = {filename_js};
            const status = document.getElementById('status');
            const progressShell = document.getElementById('progress-shell');
            const progressBar = document.getElementById('progress-bar');
            const progressLabel = document.getElementById('progress-label');

            function updateDownloadProgress(percent, label) {{
                progressShell.style.display = 'block';
                progressBar.style.width = `${{Math.min(100, Math.max(0, percent))}}%`;
                progressLabel.textContent = label;
            }}

            function startDownload() {{
                updateDownloadProgress(0, 'Starting download...');
                const xhr = new XMLHttpRequest();
                xhr.open('GET', '/file/{file_id}', true);
                xhr.responseType = 'blob';
                xhr.onprogress = (event) => {{
                    if (event.lengthComputable) {{
                        const percent = Math.round((event.loaded / event.total) * 100);
                        updateDownloadProgress(percent, `Downloading ${{percent}}%`);
                    }}
                }};
                xhr.onload = () => {{
                    if (xhr.status >= 200 && xhr.status < 300) {{
                        const blob = xhr.response;
                        const link = document.createElement('a');
                        link.href = URL.createObjectURL(blob);
                        link.download = filename;
                        document.body.appendChild(link);
                        link.click();
                        link.remove();
                        updateDownloadProgress(100, 'Download started successfully.');
                        status.textContent = 'Download started successfully. The stored file will be removed automatically.';
                        const finishBox = document.getElementById('finish-box');
                        if (finishBox) {{
                            finishBox.innerHTML = 'Download complete. <button id="close-btn">Close this tab</button>';
                        }}

                        // Try to close the tab programmatically (may be blocked by some browsers).
                        // Provide a visible fallback button which the user can tap to close.
                        setTimeout(() => {{
                            try {{
                                window.close();
                            }} catch (e) {{
                                // ignore
                            }}
                            try {{
                                // Some browsers allow closing if we replace the current window first.
                                window.open('', '_self');
                                window.close();
                            }} catch (e) {{
                                // ignore
                            }}

                            const btn = document.getElementById('close-btn');
                            if (btn) {{
                                btn.addEventListener('click', () => {{
                                    try {{ window.close(); }} catch (e) {{}}
                                    try {{ window.open('', '_self'); window.close(); }} catch (e) {{}}
                                    // Last-resort: navigate away so user can close tab manually.
                                    window.location.href = 'about:blank';
                                }});
                            }}
                        }}, 600);
                    }} else {{
                        status.textContent = xhr.responseText || 'Download failed.';
                    }}
                }};
                xhr.onerror = () => {{
                    status.textContent = 'Download failed.';
                }};
                xhr.send();
            }}
            window.addEventListener('load', startDownload);
        </script>
    </body>
    </html>
    """


@app.get("/file/{file_id}")
async def download_file(file_id: str):
    try:
        return file_service.build_download_response(file_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/health")
async def health():
    return {"status": "ok", "active_files": file_service.active_file_count()}
