from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit


def canonicalize_url(raw_url: str) -> str:
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        return ""
    parts = urlsplit(raw_url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    scheme = "https" if parts.scheme.lower() == "http" else parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        return ""
    netloc = hostname
    if port and not (scheme == "https" and port == 443):
        netloc = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def slugify(value: str, fallback: str = "orbea-bike") -> str:
    value = unicodedata.normalize("NFKD", unquote(str(value or "")))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or fallback)[:80].rstrip("-")


def image_folder_name(model: str, canonical_url: str) -> str:
    digest = hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:8]
    return f"{slugify(model)}--{digest}"


def relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(Path(path).resolve())

