# QR File Share

Upload a file (≤500KB), get a QR code that links to a public download URL.
Anyone who scans it downloads the file directly — no app install needed.

## How it works
- `POST /upload` saves the file and returns a page with a QR code.
- The QR code encodes `{BASE_URL}/download/{file_id}`.
- Files auto-expire after 1 hour (in-memory index — resets if the server restarts).

## Run locally
```bash
pip install -r requirements.txt
uvicorn src.app:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000

## Deploy to a public URL

The important part: set the `BASE_URL` environment variable to your deployed
domain, so the QR codes point to a URL the outside world can actually reach.

### Option A — Render.com (free tier, easiest)
1. Push this folder to a GitHub repo.
2. On Render: New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn src.app:app --host 0.0.0.0 --port $PORT`
5. Add environment variable `BASE_URL` = the `https://your-app.onrender.com` URL Render gives you (you can add this after the first deploy once you know the URL).
6. Note: Render's free tier has an ephemeral filesystem — fine here since files are meant to expire in an hour anyway. Don't use this for anything you need to persist.

### Option B — Railway.app
1. `railway init` in this folder, then `railway up`.
2. Railway auto-detects Python; add a `Procfile` if needed:
   ```
   web: uvicorn src.app:app --host 0.0.0.0 --port $PORT
   ```
3. Set `BASE_URL` in Railway's environment variables to your generated `*.up.railway.app` domain.

### Option C — Fly.io
1. `fly launch` (it'll generate a `fly.toml` and Dockerfile-free Python deploy).
2. `fly secrets set BASE_URL=https://your-app.fly.dev`
3. `fly deploy`

### Option D — Quick test without deploying (ngrok)
If you just want a public link right now without deploying anywhere:
```bash
uvicorn src.app:app --host 0.0.0.0 --port 8000 &
ngrok http 8000
```
Then set `BASE_URL` to the `https://xxxx.ngrok-free.app` URL ngrok gives you
(you'll need to restart the app with that env var set, since the QR is built
from `BASE_URL`).

## Security

- **No directory listing.** The `/uploads` folder is never mounted as static
  files — visiting the base URL only shows the upload form, never other
  people's files.
- **The URL is the passcode.** Each download link contains a 144-bit random
  token generated with Python's `secrets` module (cryptographically secure).
  This token isn't a "location," it's a one-time credential — scanning the
  QR code is the whole authentication step, no separate typing needed.
- **One-time links.** The moment a file is successfully downloaded, it's
  deleted and the token is invalidated — scanning the same QR twice gets a
  404 the second time.
- **Optional second-factor PIN.** If you want protection beyond "whoever has
  the link/QR," set a PIN on upload. Then even someone with the exact link
  needs to also type the PIN before the file releases.
- Files still auto-expire after 1 hour even if never downloaded, so nothing
  lingers on disk indefinitely.

## Things to change before real public use
- **Storage**: in-memory index + local disk won't survive restarts or scale
  past one server instance. For real usage, swap `UPLOAD_DIR` writes for
  S3 / Cloudflare R2 / Supabase Storage, and store the file index in Redis
  or a small database instead of a Python dict.
- **Abuse prevention**: right now anyone can upload anything. Consider a
  rate limit (e.g. `slowapi`) and maybe basic content-type checks.
- **HTTPS**: Render/Railway/Fly all give you HTTPS by default — keep it,
  don't downgrade to plain http for `BASE_URL`.
- **File size limit**: raise `MAX_FILE_SIZE` in `app.py` if you need more
  than 500KB — the QR-code constraint doesn't apply here since the QR only
  ever encodes a short URL, not the file itself.
