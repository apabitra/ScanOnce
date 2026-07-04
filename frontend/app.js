const form = document.getElementById('upload-form');
const notification = document.getElementById('share-notification');
const statusMessage = document.getElementById('status-message');
const uploadProgressShell = document.getElementById('upload-progress-shell');
const uploadProgressBar = document.getElementById('upload-progress-bar');
const uploadProgressLabel = document.getElementById('upload-progress-label');

let currentShare = { url: '', pin: '', fileId: '', filename: '' };

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
      const shareUrl = xhr.getResponseHeader('X-Share-URL') || '';
      const pin = xhr.getResponseHeader('X-Share-PIN') || '';
      const fileId = shareUrl.split('/portal/')[1] || '';
      const fileInput = form.querySelector('input[name="file"]');
      const filename = (fileInput.files && fileInput.files[0] && fileInput.files[0].name) || 'file';
      currentShare = { url: shareUrl, pin, fileId, filename };

      document.getElementById('share-url').textContent = shareUrl;
      document.getElementById('share-pin').textContent = pin;
      const qrImg = document.getElementById('share-qr');
      qrImg.src = fileId ? `/qr/${fileId}` : '';
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

function togglePinVisibility() {
  const masked = document.getElementById('share-pin-masked');
  const revealed = document.getElementById('share-pin');
  const btn = document.getElementById('reveal-pin-btn');
  const isHidden = revealed.style.display === 'none';
  revealed.style.display = isHidden ? 'inline' : 'none';
  masked.style.display = isHidden ? 'none' : 'inline';
  btn.textContent = isHidden ? 'Hide PIN' : 'Reveal PIN';
}

function dismissNotification() {
  notification.classList.remove('show');
  document.getElementById('share-url').textContent = '';
  document.getElementById('share-pin').textContent = '';
  document.getElementById('share-pin').style.display = 'none';
  document.getElementById('share-pin-masked').style.display = 'inline';
  document.getElementById('reveal-pin-btn').textContent = 'Reveal PIN';
  document.getElementById('share-qr').src = '';
  currentShare = { url: '', pin: '', fileId: '', filename: '' };
  form.reset();
  showStatus('');
  updateUploadProgress(-1, '');
  setTimeout(() => {
    if (window.confirm('Upload complete. Close this window?')) {
      window.close();
    }
  }, 200);
}

async function shareCard() {
  if (!currentShare.url) return;
  const shareText = `File: ${currentShare.filename}\nLink: ${currentShare.url}\nPIN: ${currentShare.pin}\n(Link works once and expires in 1 hour.)`;
  if (navigator.share) {
    try {
      await navigator.share({ title: 'ScanOnce file share', text: shareText, url: currentShare.url });
      return;
    } catch (error) {
      // user cancelled or share failed — fall through to clipboard fallback
    }
  }
  try {
    await navigator.clipboard.writeText(shareText);
    showStatus('Share details copied to clipboard (share isn\'t supported on this browser).', 'success');
  } catch (error) {
    showStatus('Could not share or copy automatically. Use Copy URL / Copy PIN instead.', 'error');
  }
}

async function downloadShareCard() {
  if (!currentShare.fileId) return;

  let qrDataUrl = '';
  try {
    const response = await fetch(`/qr/${currentShare.fileId}`);
    const blob = await response.blob();
    qrDataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch (error) {
    // proceed without the embedded QR image if it can't be fetched
  }

  const escapedFilename = currentShare.filename.replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ScanOnce share card — ${escapedFilename}</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 420px; margin: 40px auto; padding: 24px; border: 1px solid #ddd; border-radius: 12px; }
  h1 { font-size: 1.1rem; }
  .row { margin: 16px 0; }
  .label { font-size: 0.8rem; color: #666; text-transform: uppercase; }
  .value { font-size: 1rem; word-break: break-all; }
  img { max-width: 200px; display: block; margin-top: 8px; }
  .note { font-size: 0.8rem; color: #888; margin-top: 24px; }
</style>
</head>
<body>
  <h1>${escapedFilename}</h1>
  <div class="row">
    <div class="label">Link</div>
    <div class="value"><a href="${currentShare.url}">${currentShare.url}</a></div>
  </div>
  <div class="row">
    <div class="label">PIN</div>
    <div class="value">${currentShare.pin}</div>
  </div>
  ${qrDataUrl ? `<div class="row"><div class="label">QR code</div><img src="${qrDataUrl}" alt="QR code"></div>` : ''}
  <p class="note">This link works once and expires automatically. This file was generated by ScanOnce for offline reference — it does not refresh itself if the link expires or is used.</p>
</body>
</html>`;

  const blob = new Blob([html], { type: 'text/html' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `scanonce-share-${currentShare.fileId.slice(0, 8)}.html`;
  document.body.appendChild(link);
  link.click();
  link.remove();
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
