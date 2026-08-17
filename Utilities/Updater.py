from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

import requests


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    url: str
    sha256: str | None = None
    notes: str | None = None


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a semantic-ish version into a tuple for comparison.

    Accepts things like "1.2.3" or "v1.2.3". Non-numeric parts are ignored.
    """
    v = (version or "").strip()
    if v.lower().startswith("v"):
        v = v[1:]

    parts: list[int] = []
    for part in v.split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        if num == "":
            parts.append(0)
        else:
            try:
                parts.append(int(num))
            except Exception:
                parts.append(0)
    return tuple(parts) if parts else (0,)


def is_newer_version(current: str, candidate: str) -> bool:
    cur = _parse_version(current)
    cand = _parse_version(candidate)

    # Normalize lengths
    max_len = max(len(cur), len(cand))
    cur += (0,) * (max_len - len(cur))
    cand += (0,) * (max_len - len(cand))

    return cand > cur


def fetch_update_manifest(url: str, timeout: float = 10.0) -> UpdateManifest:
    # Enforce HTTPS for security - prevent MITM attacks
    if not url.startswith('https://'):
        raise ValueError("Update manifest URL must use HTTPS")

    r = requests.get(url, timeout=timeout, verify=True)
    r.raise_for_status()
    if not str(r.url).lower().startswith("https://"):
        raise ValueError("Update manifest redirected to a non-HTTPS URL")
    data = r.json()

    version = str(data.get("version", "")).strip()
    download_url = str(data.get("url", "")).strip()
    sha256 = data.get("sha256")
    notes = data.get("notes")

    # Require all critical fields including SHA256 for security
    if not version or not download_url:
        raise ValueError("Update manifest must include 'version' and 'url'")

    # Make SHA256 mandatory to prevent serving compromised installers
    if not sha256:
        raise ValueError("Update manifest must include 'sha256' for security verification")

    sha256_s = str(sha256).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256_s):
        raise ValueError("Update manifest 'sha256' must be a 64-character hexadecimal digest")
    if not download_url.lower().startswith("https://"):
        raise ValueError("Update download URL must use HTTPS")

    notes_s = str(notes) if notes is not None else None
    return UpdateManifest(version=version, url=download_url, sha256=sha256_s, notes=notes_s)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_to_temp(
    url: str,
    filename_hint: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    timeout: float = 120.0,  # Increased from 20s to 120s for large installers on slow connections
) -> str:
    """Download to %TEMP% and return the file path."""
    # Enforce HTTPS for download URL security
    if not url.startswith('https://'):
        raise ValueError("Download URL must use HTTPS")

    safe_name = "".join(ch for ch in filename_hint if ch.isalnum() or ch in ("-", "_", "."))
    if not safe_name.lower().endswith(".exe"):
        safe_name += ".exe"

    # Use an exclusive, per-download path. A deterministic file in the shared
    # temp folder could be stale, overwritten by another update, or replaced
    # between two concurrent app instances.
    file_descriptor, dest = tempfile.mkstemp(
        prefix="ultrabike-update-",
        suffix=f"-{safe_name}",
    )
    os.close(file_descriptor)

    max_download_bytes = 1024 * 1024 * 1024  # 1 GiB safety limit
    try:
        with requests.get(url, stream=True, timeout=timeout, verify=True) as r:
            r.raise_for_status()
            if not str(r.url).lower().startswith("https://"):
                raise ValueError("Update download redirected to a non-HTTPS URL")
            total = int(r.headers.get("Content-Length", "0") or "0")
            if total > max_download_bytes:
                raise ValueError("Update installer exceeds the 1 GiB safety limit")
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > max_download_bytes:
                        raise ValueError("Update installer exceeds the 1 GiB safety limit")
                    f.write(chunk)
                    if progress_cb:
                        try:
                            progress_cb(downloaded, total)
                        except Exception:
                            pass
    except Exception:
        try:
            if os.path.isfile(dest):
                os.remove(dest)
        except OSError:
            pass
        raise

    return dest


def run_installer(installer_path: str, silent: bool = True) -> None:
    import sys
    import os

    # Verify installer exists before attempting to run
    if not os.path.exists(installer_path):
        raise FileNotFoundError(f"Installer not found: {installer_path}")

    # Build command-line arguments for Inno Setup
    args = [installer_path]
    if silent:
        args += [
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NOCANCEL",
            "/SP-",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS=no",
        ]

    # Use Windows-specific ShellExecute for proper UAC elevation handling
    # This keeps the process alive through the UAC dialog, preventing orphaning
    if sys.platform == 'win32':
        import ctypes

        # Join arguments for ShellExecuteW (skip first arg which is the exe path)
        params = " ".join(args[1:]) if len(args) > 1 else None

        # ShellExecuteW with "runas" verb requests UAC elevation
        # This is more robust than subprocess.Popen for installers
        result = ctypes.windll.shell32.ShellExecuteW(
            None,           # hwnd - no parent window
            "open",         # lpOperation - use "open" instead of "runas" since installer handles elevation
            installer_path, # lpFile - path to installer
            params,         # lpParameters - command-line args
            None,           # lpDirectory - use installer's directory
            1               # nShowCmd - SW_SHOWNORMAL (1)
        )

        # ShellExecuteW returns a value > 32 on success, <= 32 on error
        if result <= 32:
            raise RuntimeError(f"Failed to launch installer (error code: {result})")
    else:
        # Fallback for non-Windows platforms (shouldn't happen for this app)
        subprocess.Popen(args, close_fds=True)


def build_manifest_dict(version: str, installer_url: str, sha256: str | None = None, notes: str | None = None) -> dict:
    d: dict = {"version": version, "url": installer_url}
    if sha256:
        d["sha256"] = sha256
    if notes is not None:
        d["notes"] = notes
    return d


def write_manifest(path: str, manifest: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
