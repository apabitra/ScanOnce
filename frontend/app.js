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
      const shareUrl = xhr.getResponseHeader('X-Share-URL') || '';
      document.getElementById('share-url').textContent = shareUrl;
      document.getElementById('share-pin').textContent = xhr.getResponseHeader('X-Share-PIN') || '';
      const fileId = shareUrl.split('/portal/')[1] || '';
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

function dismissNotification() {
  notification.classList.remove('show');
  document.getElementById('share-url').textContent = '';
  document.getElementById('share-pin').textContent = '';
  document.getElementById('share-qr').src = '';
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
