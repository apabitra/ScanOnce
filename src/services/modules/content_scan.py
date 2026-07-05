"""
Structural file-safety checks:
  1. Extension blocklist for auto-executing file types.
  2. Magic-byte signature detection for known executable formats,
     checked regardless of the claimed extension.
  3. Content-vs-extension validation: detects the file's *real* type from
     its content and rejects it if that doesn't match what the filename
     claims (e.g. a .exe renamed to report.pdf, or a script saved as
     photo.jpg). This is what makes extension checks meaningful — an
     extension blocklist alone is trivially bypassed by renaming.

This is NOT a substitute for real antivirus/malware scanning. It can't
detect an actual virus signature embedded inside an otherwise legitimate
file type (e.g. a malicious macro inside a real .docx, or an exploit
payload inside a well-formed .pdf). That requires signature-based
scanning (ClamAV) or a hosted API (VirusTotal/Cloudmersive) — a separate,
larger addition.
"""

from pathlib import Path

BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".com", ".scr", ".msi", ".msp", ".msc",
    ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".wsf", ".wsh",
    ".js", ".jse", ".jar",
    ".sh", ".bash", ".run",
    ".apk", ".app", ".dmg", ".pkg",
    ".scpt", ".workflow",
}

_EXECUTABLE_SIGNATURES = [
    (b"MZ", "Windows executable (PE/EXE/DLL)"),
    (b"\x7fELF", "Linux/Unix executable (ELF)"),
    (b"\xca\xfe\xba\xbe", "macOS universal binary (Mach-O)"),
    (b"\xfe\xed\xfa\xce", "macOS executable (Mach-O 32-bit)"),
    (b"\xfe\xed\xfa\xcf", "macOS executable (Mach-O 64-bit)"),
    (b"\xcf\xfa\xed\xfe", "macOS executable (Mach-O, reversed)"),
    (b"#!/", "Script with a shebang line"),
]

# (offset, magic bytes, detected type label, extensions this signature is
# legitimately allowed to appear under). If the file's content matches a
# signature here but the claimed extension isn't in that set, it's rejected
# as a mismatch — regardless of whether the real type itself is "safe."
_KNOWN_SIGNATURES = [
    (0, b"\x89PNG\r\n\x1a\n", "PNG image", {".png"}),
    (0, b"\xff\xd8\xff", "JPEG image", {".jpg", ".jpeg"}),
    (0, b"GIF87a", "GIF image", {".gif"}),
    (0, b"GIF89a", "GIF image", {".gif"}),
    (0, b"BM", "BMP image", {".bmp"}),
    (0, b"%PDF", "PDF document", {".pdf"}),
    (0, b"\x1a\x45\xdf\xa3", "Matroska/WebM video", {".mkv", ".webm"}),
    (0, b"\x1f\x8b", "GZIP archive", {".gz", ".tgz"}),
    (0, b"7z\xbc\xaf\x27\x1c", "7-Zip archive", {".7z"}),
    (0, b"Rar!\x1a\x07", "RAR archive", {".rar"}),
    (0, b"ID3", "MP3 audio", {".mp3"}),
    (0, b"\xff\xfb", "MP3 audio", {".mp3"}),
    (0, b"RIFF", "RIFF container (WAV/AVI)", {".wav", ".avi"}),
    # ZIP-based formats share one signature — Office docs, plain zips, and
    # a few other container formats are all "PK\x03\x04" under the hood.
    (0, b"PK\x03\x04", "ZIP-based file (zip/docx/xlsx/pptx)",
     {".zip", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}),
    # MP4/MOV/M4A: signature bytes sit at offset 4, not 0.
    (4, b"ftyp", "MP4/MOV/M4A media", {".mp4", ".mov", ".m4a", ".m4v"}),
]

# Extensions with no reliable magic-byte signature (plain text formats).
# These get a lighter check: content should look like actual text, not
# binary data pretending to be text.
_TEXT_EXTENSIONS = {".txt", ".csv", ".md", ".log", ".json", ".xml", ".yaml", ".yml", ".html", ".htm", ".css"}


def _has_blocked_extension(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in BLOCKED_EXTENSIONS else None


def _detect_executable_signature(contents: bytes) -> str | None:
    header = contents[:8]
    for signature, label in _EXECUTABLE_SIGNATURES:
        if header[:len(signature)] == signature:
            return label
    return None


def _detect_known_type(contents: bytes):
    """Returns (label, allowed_extensions) if the content matches a known
    signature, else None if the type can't be determined from content."""
    for offset, signature, label, allowed_exts in _KNOWN_SIGNATURES:
        window = contents[offset:offset + len(signature)]
        if window == signature:
            return label, allowed_exts
    return None


def _looks_like_text(contents: bytes) -> bool:
    sample = contents[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def assert_file_is_safe(filename: str, contents: bytes) -> None:
    """Raises ValueError with a user-facing reason if the file is rejected."""
    suffix = Path(filename).suffix.lower()

    blocked_ext = _has_blocked_extension(filename)
    if blocked_ext:
        raise ValueError(
            f"Files with the '{blocked_ext}' extension aren't allowed "
            f"(executable/script file types are blocked for safety)."
        )

    exec_signature = _detect_executable_signature(contents)
    if exec_signature:
        raise ValueError(
            f"This file was rejected: its content matches a "
            f"{exec_signature}, regardless of its filename/extension."
        )

    known = _detect_known_type(contents)
    if known:
        label, allowed_exts = known
        if suffix not in allowed_exts:
            raise ValueError(
                f"This file's content looks like a {label}, but its "
                f"filename claims '{suffix or '(no extension)'}'. "
                f"Rename it to match its real type, or re-export it correctly."
            )
        return

    # No binary signature matched. If it claims to be a text-like format,
    # make sure it actually looks like text rather than opaque binary data.
    if suffix in _TEXT_EXTENSIONS and not _looks_like_text(contents):
        raise ValueError(
            f"This file's content doesn't look like plain text, but its "
            f"filename claims '{suffix}'. Rejected as a possible mismatch."
        )

    # Unrecognized content with no signature and no text-extension claim:
    # nothing to compare the extension against, so let it through — this
    # only validates the formats above, it doesn't block everything else.
