"""
Gated product downloads: storing installers, and the links that release them.

The file side mirrors app/uploads.py, for files that are private rather than
public:

* Installers live under PROTECTED_UPLOADS_DIR, outside /static, so nginx has
  no route to them. The only way out is the view that checks a download link.
* The type is decided by the file's bytes, not its name: each allowed
  extension has a signature, and an upload whose bytes do not match the
  extension it claims is rejected.
* The name on disk is random (downloads/<32 hex>.<ext>). The name the visitor
  sees is kept separately, cleaned, and never used to build a path.
* The upload is streamed to disk while its size and SHA-256 are measured, so
  a several-hundred-megabyte installer is never held in memory, then moved
  into place atomically so a half-written file is never served.

The link side: a download link carries a random token. Only its SHA-256 is
stored, so the table alone cannot be turned back into working links, and the
URL contains no database id.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import uuid
from dataclasses import dataclass

from flask import current_app

SUBDIR = "downloads"

# Extension -> (platform label, signature check). The label is only for
# display ("Windows installer"); the check is what decides acceptance.
_HEAD = 16      # bytes read from the start of the file
_TAIL = 512     # bytes read from the end (the DMG trailer lives there)


def _starts(*prefixes: bytes):
    return lambda head, tail: any(head.startswith(p) for p in prefixes)


_ZIP = b"PK\x03\x04"
_TYPES: dict[str, tuple[str | None, object]] = {
    "exe": ("Windows", _starts(b"MZ")),
    "msi": ("Windows", _starts(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")),   # OLE compound file
    "msix": ("Windows", _starts(_ZIP)),
    "zip": (None, _starts(_ZIP)),
    "dmg": ("macOS", lambda head, tail: tail[:4] == b"koly"),           # UDIF trailer
    "pkg": ("macOS", _starts(b"xar!")),
    "appimage": ("Linux", _starts(b"\x7fELF")),
    "deb": ("Linux", _starts(b"!<arch>\n")),
    "rpm": ("Linux", _starts(b"\xed\xab\xee\xdb")),
}

ALLOWED_EXTENSIONS = frozenset(_TYPES)
# For the admin file picker. Display only: enforcement is in store_download.
ACCEPT_ATTR = ",".join(f".{ext}" for ext in sorted(ALLOWED_EXTENSIONS))

_STORED_PATH_RE = re.compile(rf"^{SUBDIR}/[0-9a-f]{{32}}\.(?:{'|'.join(sorted(ALLOWED_EXTENSIONS))})$")
# What a visitor's browser may be told to name the file.
_NAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9 ._()+-]+")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")   # secrets.token_urlsafe(32)

_CHUNK = 1024 * 1024


class DownloadFileError(ValueError):
    """Raised with a message that is safe to show the admin."""


@dataclass(frozen=True)
class StoredDownload:
    path: str        # relative to PROTECTED_UPLOADS_DIR, e.g. downloads/ab12...exe
    filename: str    # what the visitor's browser saves it as
    size: int
    sha256: str


# ---------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------

def _root() -> str:
    return current_app.config["PROTECTED_UPLOADS_DIR"]


def extension_of(filename: str | None) -> str:
    base = _basename(filename or "")
    return base.rsplit(".", 1)[1].lower() if "." in base else ""


def platform_for(filename: str | None) -> str | None:
    entry = _TYPES.get(extension_of(filename))
    return entry[0] if entry else None


def _basename(filename: str) -> str:
    # Browsers on Windows have historically sent the full client path.
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def clean_download_name(filename: str | None, fallback_stem: str = "download") -> str:
    """
    The name the visitor's browser saves the file as, e.g.
    "JSWM Abbreviator Setup 2.0.0.exe". Path parts and anything outside a
    plain set of characters are dropped; the extension is kept lower-case.
    """
    ext = extension_of(filename)
    stem = _basename(filename or "")
    if ext:
        stem = stem[: -(len(ext) + 1)]
    stem = _NAME_UNSAFE_RE.sub(" ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")[:150]
    stem = stem or fallback_stem
    return f"{stem}.{ext}" if ext else stem


def store_download(file_storage, fallback_stem: str = "download") -> StoredDownload:
    """
    Validate an uploaded installer and write it into the protected store.

    Raises DownloadFileError for anything that should not be published.
    """
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise DownloadFileError("Choose a file to upload.")

    ext = extension_of(file_storage.filename)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(f".{e}" for e in sorted(ALLOWED_EXTENSIONS))
        raise DownloadFileError(f"That file type is not supported. Allowed: {allowed}.")

    max_bytes = current_app.config["MAX_DOWNLOAD_UPLOAD_BYTES"]
    directory = os.path.join(_root(), SUBDIR)
    os.makedirs(directory, exist_ok=True)

    name = f"{uuid.uuid4().hex}.{ext}"
    final_path = os.path.join(directory, name)
    temp_path = final_path + ".part"

    digest = hashlib.sha256()
    size = 0
    try:
        with open(temp_path, "wb") as out:
            stream = file_storage.stream
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise DownloadFileError(
                        f"That file is larger than the {format_size(max_bytes)} limit."
                    )
                digest.update(chunk)
                out.write(chunk)

        if size == 0:
            raise DownloadFileError("That file is empty.")

        with open(temp_path, "rb") as check:
            head = check.read(_HEAD)
            check.seek(max(size - _TAIL, 0))
            tail = check.read(_TAIL)
        if not _TYPES[ext][1](head, tail):
            raise DownloadFileError(
                f"That file's contents do not match a .{ext} file. "
                "Check that you picked the right installer."
            )

        os.replace(temp_path, final_path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    return StoredDownload(
        path=f"{SUBDIR}/{name}",
        filename=clean_download_name(file_storage.filename, fallback_stem=fallback_stem),
        size=size,
        sha256=digest.hexdigest(),
    )


def is_stored_download(path: str | None) -> bool:
    return bool(path) and bool(_STORED_PATH_RE.match(path))


def delete_download(path: str | None) -> None:
    """Remove a stored installer. Anything not shaped like one is left alone."""
    if not is_stored_download(path):
        return
    full = os.path.join(_root(), path)
    try:
        os.remove(full)
    except FileNotFoundError:
        pass


def download_exists(path: str | None) -> bool:
    return is_stored_download(path) and os.path.isfile(os.path.join(_root(), path))


def format_size(num_bytes: int | None) -> str:
    """15513636 -> "14.8 MB", matching what Windows Explorer reports."""
    if not num_bytes:
        return ""
    size = float(num_bytes)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "bytes":
                return f"{int(size)} bytes"
            return f"{size:.1f} {unit}" if size < 100 else f"{size:.0f} {unit}"
        size /= 1024
    return ""  # unreachable


# ---------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------

def new_download_token() -> tuple[str, str]:
    """A fresh (token, sha256-of-token) pair. Only the hash is stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_download_token(token)


def hash_download_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def looks_like_token(token: str | None) -> bool:
    """Cheap shape check, so junk never reaches the database."""
    return bool(token) and bool(_TOKEN_RE.match(token))
