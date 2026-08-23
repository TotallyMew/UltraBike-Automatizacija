"""Portable authenticated backups for UltraBike's local SQLite data."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sqlite3
import struct
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from Database.DatabaseManager import DatabaseManager
from Utilities.Version import get_app_version


MAGIC = b"ULTRABIKE-BACKUP\x01"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class BackupInfo:
    format_version: int
    created_at: str
    app_version: str
    schema_version: int
    database_size: int


class BackupManager:
    """Create, inspect, and atomically restore encrypted ``.ubbackup`` files."""

    def __init__(self, database: DatabaseManager):
        self.database = database

    @staticmethod
    def _derive_key(password: str, salt: bytes, *, n: int, r: int, p: int) -> bytes:
        if not isinstance(password, str) or len(password) < 10:
            raise ValueError("Backup password must contain at least 10 characters")
        if n != 2**14 or r != 8 or p != 1:
            raise ValueError("Unsupported backup key-derivation parameters")
        return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode("utf-8"))

    def _snapshot_database(self, destination: Path) -> None:
        target = sqlite3.connect(str(destination))
        try:
            with self.database.write_lock:
                self.database.conn.backup(target)
            target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            target.close()

    @staticmethod
    def _build_payload(snapshot: Path, info: BackupInfo) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(asdict(info), sort_keys=True))
            archive.write(snapshot, "ultrabike.db")
        return output.getvalue()

    @staticmethod
    def _read_payload(payload: bytes) -> tuple[BackupInfo, bytes]:
        try:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
                names = set(archive.namelist())
                if names != {"manifest.json", "ultrabike.db"}:
                    raise ValueError("Backup contains unexpected files")
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                info = BackupInfo(**manifest)
                database_bytes = archive.read("ultrabike.db")
        except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("Backup payload is invalid") from error
        if info.format_version != FORMAT_VERSION:
            raise ValueError(f"Unsupported backup format: {info.format_version}")
        if info.database_size != len(database_bytes):
            raise ValueError("Backup database size does not match its manifest")
        return info, database_bytes

    @staticmethod
    def _encode(payload: bytes, password: str) -> bytes:
        salt = os.urandom(16)
        nonce = os.urandom(12)
        parameters = {
            "format_version": FORMAT_VERSION,
            "kdf": "scrypt",
            "n": 2**14,
            "r": 8,
            "p": 1,
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
        }
        header = json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key = BackupManager._derive_key(password, salt, n=2**14, r=8, p=1)
        ciphertext = AESGCM(key).encrypt(nonce, payload, header)
        return MAGIC + struct.pack(">I", len(header)) + header + ciphertext

    @staticmethod
    def _decode(data: bytes, password: str) -> bytes:
        if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 4:
            raise ValueError("This is not an UltraBike backup")
        header_length = struct.unpack(">I", data[len(MAGIC):len(MAGIC) + 4])[0]
        if header_length < 2 or header_length > 64 * 1024:
            raise ValueError("Backup header is invalid")
        offset = len(MAGIC) + 4
        header = data[offset:offset + header_length]
        ciphertext = data[offset + header_length:]
        try:
            parameters = json.loads(header.decode("utf-8"))
            if parameters.get("format_version") != FORMAT_VERSION or parameters.get("kdf") != "scrypt":
                raise ValueError("Unsupported backup format")
            salt = base64.b64decode(parameters["salt"], validate=True)
            nonce = base64.b64decode(parameters["nonce"], validate=True)
            key = BackupManager._derive_key(
                password,
                salt,
                n=int(parameters["n"]),
                r=int(parameters["r"]),
                p=int(parameters["p"]),
            )
            return AESGCM(key).decrypt(nonce, ciphertext, header)
        except InvalidTag as error:
            raise ValueError("Backup password is incorrect or the backup was modified") from error
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
            if isinstance(error, ValueError) and str(error).startswith("Backup password"):
                raise
            raise ValueError("Backup header is invalid") from error

    @staticmethod
    def _validate_database(path: Path, info: BackupInfo) -> None:
        connection = sqlite3.connect(str(path))
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("Backup database failed its integrity check")
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if schema_version != info.schema_version:
                raise ValueError("Backup schema metadata does not match its database")
            if schema_version > DatabaseManager.LATEST_SCHEMA_VERSION:
                raise ValueError("Backup was created by a newer UltraBike version")
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            required = {
                "settings", "credentials", "external_credentials", "processing_history",
            }
            if schema_version >= 3:
                required.add("earning_goal_adjustments")
            if not required.issubset(tables):
                raise ValueError("Backup database is missing required application tables")
        finally:
            connection.close()

    def create(self, path: str | Path, password: str) -> BackupInfo:
        destination = Path(path).expanduser().resolve()
        if destination.suffix.lower() != ".ubbackup":
            destination = destination.with_suffix(".ubbackup")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ultrabike-backup-") as temp_dir:
            snapshot = Path(temp_dir) / "ultrabike.db"
            self._snapshot_database(snapshot)
            info = BackupInfo(
                format_version=FORMAT_VERSION,
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                app_version=get_app_version("0.0.0"),
                schema_version=int(self.database.conn.execute("PRAGMA user_version").fetchone()[0]),
                database_size=snapshot.stat().st_size,
            )
            encoded = self._encode(self._build_payload(snapshot, info), password)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
        )
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return info

    def inspect(self, path: str | Path, password: str) -> BackupInfo:
        payload = self._decode(Path(path).read_bytes(), password)
        info, database_bytes = self._read_payload(payload)
        with tempfile.TemporaryDirectory(prefix="ultrabike-inspect-") as temp_dir:
            candidate = Path(temp_dir) / "ultrabike.db"
            candidate.write_bytes(database_bytes)
            self._validate_database(candidate, info)
        return info

    def restore(self, path: str | Path, password: str) -> BackupInfo:
        payload = self._decode(Path(path).read_bytes(), password)
        info, database_bytes = self._read_payload(payload)
        current = Path(self.database.db_path).resolve()
        current.parent.mkdir(parents=True, exist_ok=True)
        handle, candidate_name = tempfile.mkstemp(
            prefix=".ultrabike-restore-", suffix=".db", dir=str(current.parent)
        )
        rollback = current.with_name(
            f"{current.stem}.restore-backup-{datetime.now():%Y%m%d_%H%M%S}{current.suffix}"
        )
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(database_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            candidate = Path(candidate_name)
            self._validate_database(candidate, info)
            with self.database.write_lock:
                if self.database.conn is not None:
                    self.database.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    self.database.close()
                if current.exists():
                    shutil.copy2(current, rollback)
                os.replace(candidate, current)
        except Exception:
            try:
                Path(candidate_name).unlink(missing_ok=True)
            except OSError:
                pass
            if self.database.conn is None:
                self.database._connect()
            raise
        return info
