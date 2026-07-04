document.addEventListener('DOMContentLoaded', () => {
  const qrCloseButton = document.getElementById('qr-close');
  if (qrCloseButton) {
    qrCloseButton.addEventListener('click', () => {
      try { window.close(); } catch (e) {}
      try { window.open('', '_self'); window.close(); } catch (e) {}
      window.location.href = 'about:blank';
    });
  }
});
