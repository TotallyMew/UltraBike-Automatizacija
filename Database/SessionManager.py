"""
Session Manager - Handles 24h auto-login sessions
Uses Windows current-user DPAPI protection for session files

Security: Uses Scrypt for password-based key derivation (memory-hard, GPU-resistant)
Backward compatible: Auto-migrates old SHA256-based encryption to Scrypt
Migration is transparent - old credentials are re-encrypted on first use
"""

# Standard library
import base64
import getpass
import hashlib
import hmac
import json
import os
import platform
import secrets
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

# Third-party packages
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Local
from Utilities.AppPaths import get_default_session_path

class SessionManager:
    """
    Manages user sessions and encrypted credential storage.

    Security features:
    - Scrypt KDF (memory-hard, resistant to GPU/ASIC attacks)
    - Per-credential random salts
    - Configurable work factors stored in DB
    - Automatic migration from legacy SHA256 encryption

    Encryption Strategies:

    1. **Windows DPAPI** (Session Files):
       - Used for: Temporary 24h session files only
       - Method: Current-user Windows Data Protection API
       - Purpose: Bind auto-login data to the signed-in Windows account
       - Compatibility: Legacy machine-derived Fernet files remain readable

    2. **Scrypt KDF** (Credentials - CURRENT):
    - Used for: admin passwords, external API credentials
       - Method: Scrypt(password, random_salt, N=2^14, r=8, p=1) → Fernet key
       - Purpose: Memory-hard key derivation resists GPU/ASIC brute-force
       - Security: OWASP 2023 recommended parameters
       - Storage: Encrypted password + base64(salt) + JSON(kdf_params)

    3. **Legacy SHA256** (DEPRECATED - Backward Compatibility Only):
       - Used for: Auto-migrating old credentials on first decrypt
       - Method: SHA256(password + salt_hex) → Fernet key
       - Purpose: Decrypt existing credentials, immediately re-encrypt with Scrypt
       - Security: INSECURE - vulnerable to GPU attacks
       - Migration: Transparent, triggered on get_credentials() or get_external_credentials()
       - Deprecation: Will be removed once all users migrate (target: v2.0)

    When to use which:
    - Session files: Current-user DPAPI (Windows)
    - Passwords: Scrypt KDF (secure, persistent)
    - Never use: Legacy SHA256 for new data
    """

    # Scrypt parameters (OWASP recommendations 2023)
    # These provide strong security while remaining usable on typical hardware
    SCRYPT_N = 2**14  # CPU/memory cost (16384) - ~100ms on modern CPU
    SCRYPT_R = 8      # Block size
    SCRYPT_P = 1      # Parallelization
    SCRYPT_LENGTH = 32  # Output key length (256 bits for Fernet)

    def __init__(self, db_manager, logger=None):
        self.db = db_manager
        self.logger = logger
        self.session_file = str(get_default_session_path())
        self.session_duration_hours = 24

        # Ensure kdf_params column exists for storing Scrypt parameters
        try:
            self.db._ensure_column("credentials", "kdf_params", "TEXT")
            self.db._ensure_column("external_credentials", "kdf_params", "TEXT")
        except Exception:
            pass  # Column might already exist or DB might not be ready yet

    def _log(self, message, **context):
        """Log message if logger is available"""
        if self.logger:
            self.logger.log("SessionManager", message, **context)

    def _get_machine_id(self):
        """Get unique machine identifier"""
        # Use computer name + username as machine ID
        machine_string = f"{platform.node()}-{getpass.getuser()}"
        return hashlib.sha256(machine_string.encode()).hexdigest()

    def _get_encryption_key(self):
        """Generate the legacy machine key used to read older session files."""
        machine_id = self._get_machine_id()
        # Derive a valid Fernet key from machine ID
        key_material = hashlib.sha256(machine_id.encode()).digest()
        return base64.urlsafe_b64encode(key_material)

    def _derive_key_scrypt(self, password: str, salt: bytes) -> bytes:
        """
        Derive encryption key using Scrypt KDF (secure, memory-hard).

        Args:
            password: Master password or passphrase
            salt: Random salt (should be 16+ bytes)

        Returns:
            32-byte key suitable for Fernet encryption
        """
        kdf = Scrypt(
            salt=salt,
            length=self.SCRYPT_LENGTH,
            n=self.SCRYPT_N,
            r=self.SCRYPT_R,
            p=self.SCRYPT_P,
            backend=default_backend()
        )
        return kdf.derive(password.encode())

    def _derive_key_scrypt_params(self, password: str, salt: bytes, params: dict) -> bytes:
        """Derive a key from validated stored parameters.

        Parameter limits prevent a corrupted local database from requesting an
        unbounded amount of memory or CPU during unlock.
        """
        n = int(params.get("n", self.SCRYPT_N))
        r = int(params.get("r", self.SCRYPT_R))
        p = int(params.get("p", self.SCRYPT_P))
        length = int(params.get("length", self.SCRYPT_LENGTH))
        if n < 2**14 or n > 2**18 or n & (n - 1):
            raise ValueError("Invalid Scrypt work factor")
        if not 1 <= r <= 16 or not 1 <= p <= 4 or length != 32:
            raise ValueError("Invalid Scrypt parameters")
        kdf = Scrypt(
            salt=salt,
            length=length,
            n=n,
            r=r,
            p=p,
            backend=default_backend(),
        )
        return kdf.derive(password.encode())

    def _derive_key_legacy_sha256(self, password: str, salt_hex: str) -> bytes:
        """
        Legacy key derivation using SHA256 (INSECURE - for backward compatibility only).

        This method is only used to decrypt old credentials during migration.
        New credentials always use Scrypt.

        Args:
            password: Master password
            salt_hex: Salt as hex string

        Returns:
            32-byte key (SHA256 hash)
        """
        combined_key = hashlib.sha256(f"{password}{salt_hex}".encode()).digest()
        return combined_key

    def _get_kdf_params(self) -> Dict[str, Any]:
        """Get current KDF parameters as dict for storage"""
        return {
            "kdf": "scrypt",
            "n": self.SCRYPT_N,
            "r": self.SCRYPT_R,
            "p": self.SCRYPT_P,
            "length": self.SCRYPT_LENGTH
        }
    
    @staticmethod
    def _dpapi_protect(data: bytes) -> bytes:
        """Protect bytes for the current Windows user with DPAPI."""
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        source_buffer = ctypes.create_string_buffer(data)
        source = DATA_BLOB(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        protected = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(protected)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(protected.pbData, protected.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(protected.pbData)

    @staticmethod
    def _dpapi_unprotect(data: bytes) -> bytes:
        """Unprotect current-user DPAPI bytes."""
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        source_buffer = ctypes.create_string_buffer(data)
        source = DATA_BLOB(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        clear = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(clear)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(clear.pbData, clear.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(clear.pbData)

    def _encrypt(self, data: str) -> str:
        """Encrypt session data with Windows DPAPI when available."""
        if os.name == "nt":
            protected = self._dpapi_protect(data.encode("utf-8"))
            return "dpapi:" + base64.b64encode(protected).decode("ascii")

        # Non-Windows development fallback. Existing Windows session files
        # using this legacy scheme remain readable and migrate on next write.
        key = self._get_encryption_key()
        f = Fernet(key)
        return f.encrypt(data.encode()).decode()
    
    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt DPAPI sessions, with legacy Fernet compatibility."""
        try:
            if str(encrypted_data).startswith("dpapi:"):
                if os.name != "nt":
                    return None
                payload = base64.b64decode(str(encrypted_data)[6:], validate=True)
                return self._dpapi_unprotect(payload).decode("utf-8")
            key = self._get_encryption_key()
            f = Fernet(key)
            return f.decrypt(encrypted_data.encode()).decode()
        except (ValueError, TypeError, AttributeError) as e:
            # Invalid encrypted data format or key mismatch
            return None
        except Exception as e:
            # Unexpected error during decryption
            self._log(f"Unexpected decryption error: {e}", error=str(e), traceback=traceback.format_exc())
            return None
    
    def has_master_password(self) -> bool:
        """Check if master password is set in database"""
        cursor = self.db.conn.cursor()
    
        # Check if master password hash exists in settings
        result = cursor.execute("""
            SELECT value FROM settings WHERE key = 'master_password_hash'
        """).fetchone()
    
        return result is not None

    def _make_master_password_verifier(self, master_password: str) -> str:
        """Create a salted, memory-hard verifier for the master password."""
        if not master_password:
            raise ValueError("Master password is required")
        salt = secrets.token_bytes(16)
        digest = self._derive_key_scrypt(master_password, salt)
        verifier = {
            "version": 2,
            **self._get_kdf_params(),
            "salt": base64.b64encode(salt).decode("ascii"),
            "hash": base64.b64encode(digest).decode("ascii"),
        }
        return json.dumps(verifier, sort_keys=True, separators=(",", ":"))

    def _store_master_password_verifier(self, master_password: str, cursor=None) -> None:
        cursor = cursor or self.db.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES ('master_password_hash', ?, ?)
            """,
            (
                self._make_master_password_verifier(master_password),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ),
        )

    def set_master_password(self, master_password: str) -> None:
        """Persist a salted, memory-hard password verifier."""
        cursor = self.db.conn.cursor()
        self._store_master_password_verifier(master_password, cursor)
        self.db.conn.commit()
    
    def store_credentials(self, email: str, password: str, master_password: str):
        """
        Store encrypted credentials in database using Scrypt KDF.

        Security: Uses Scrypt for key derivation (memory-hard, GPU-resistant)
        Old SHA256-based credentials are automatically re-encrypted with Scrypt

        Args:
            email: User email
            password: Admin password to encrypt
            master_password: Master password for encryption
        """
        # Generate random salt (16 bytes = 128 bits)
        salt = secrets.token_bytes(16)

        # Derive key using Scrypt
        encryption_key = self._derive_key_scrypt(master_password, salt)
        fernet_key = base64.urlsafe_b64encode(encryption_key)
        f = Fernet(fernet_key)
        encrypted_password = f.encrypt(password.encode()).decode()

        # Get KDF parameters for storage
        kdf_params_json = json.dumps(self._get_kdf_params())

        # Store in database
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO credentials
            (email, encrypted_password, salt, kdf_params, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            email,
            encrypted_password,
            base64.b64encode(salt).decode(),  # Store salt as base64
            kdf_params_json,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))

        # Store a separate salted verifier; never persist a fast unsalted hash.
        self._store_master_password_verifier(master_password, cursor)

        self.db.conn.commit()

    def has_external_credentials(self, service_key: str) -> bool:
        """Check if credentials exist for a given external service."""
        cursor = self.db.conn.cursor()
        result = cursor.execute(
            "SELECT 1 FROM external_credentials WHERE service_key = ?",
            (service_key,),
        ).fetchone()
        return result is not None

    def store_external_credentials(self, service_key: str, username: str, password: str, master_password: str) -> None:
        """
        Store encrypted external-service credentials in database using Scrypt KDF.

        Args:
            service_key: Unique identifier for the service (e.g., "deepl_api")
            username: Username or API key
            password: Password or secret to encrypt
            master_password: Master password for encryption
        """
        # Generate random salt
        salt = secrets.token_bytes(16)

        # Derive key using Scrypt
        encryption_key = self._derive_key_scrypt(master_password, salt)
        fernet_key = base64.urlsafe_b64encode(encryption_key)
        f = Fernet(fernet_key)
        encrypted_password = f.encrypt(password.encode()).decode()

        # Get KDF parameters for storage
        kdf_params_json = json.dumps(self._get_kdf_params())

        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO external_credentials
            (service_key, username, encrypted_password, salt, kdf_params, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                service_key,
                username,
                encrypted_password,
                base64.b64encode(salt).decode(),
                kdf_params_json,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ),
        )
        self.db.conn.commit()

    def get_external_credentials(self, service_key: str, master_password: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Decrypt and return (username, password) for external service.

        Auto-migrates legacy SHA256-encrypted credentials to Scrypt on first use.

        Args:
            service_key: Service identifier
            master_password: Master password for decryption

        Returns:
            Tuple of (username, password) or (None, None) if not found/invalid
        """
        if not self.verify_master_password(master_password):
            return None, None

        cursor = self.db.conn.cursor()
        row = cursor.execute(
            """
            SELECT username, encrypted_password, salt, kdf_params
            FROM external_credentials
            WHERE service_key = ?
            """,
            (service_key,),
        ).fetchone()

        if not row:
            return None, None

        username, encrypted_password, salt_b64, kdf_params_json = row

        try:
            # Check if this is a legacy SHA256-encrypted credential (no kdf_params)
            if kdf_params_json is None:
                # Legacy decryption using SHA256
                encryption_key = self._derive_key_legacy_sha256(master_password, salt_b64)
                fernet_key = base64.urlsafe_b64encode(encryption_key)
                f = Fernet(fernet_key)
                password = f.decrypt(encrypted_password.encode()).decode()

                # Auto-migrate to Scrypt
                self.store_external_credentials(service_key, username, password, master_password)

                return username, password
            else:
                # Modern Scrypt decryption
                kdf_params = json.loads(kdf_params_json)

                if kdf_params.get("kdf") == "scrypt":
                    salt = base64.b64decode(salt_b64)
                    encryption_key = self._derive_key_scrypt_params(master_password, salt, kdf_params)
                    fernet_key = base64.urlsafe_b64encode(encryption_key)
                    f = Fernet(fernet_key)
                    password = f.decrypt(encrypted_password.encode()).decode()
                    return username, password
                else:
                    # Unknown KDF
                    return None, None

        except (ValueError, TypeError) as e:
            # Invalid encrypted data or key format
            return None, None
        except Exception as e:
            # Unexpected decryption error - log it
            self._log(f"Unexpected error in get_external_credentials: {e}", error=str(e), service_key=service_key)
            return None, None

    def get_external_username(self, service_key: str) -> str:
        """Return saved username for an external service without decrypting password."""
        cursor = self.db.conn.cursor()
        row = cursor.execute(
            "SELECT username FROM external_credentials WHERE service_key = ?",
            (service_key,),
        ).fetchone()
        return row[0] if row else ""

    def clear_external_credentials(self, service_key: str) -> None:
        """Delete external credentials for a given service."""
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM external_credentials WHERE service_key = ?", (service_key,))
        self.db.conn.commit()
    
    def verify_master_password(self, master_password: str) -> bool:
        """Verify the master password and migrate legacy SHA-256 verifiers."""
        if not isinstance(master_password, str) or not master_password:
            return False
        cursor = self.db.conn.cursor()
        result = cursor.execute("""
            SELECT value FROM settings WHERE key = 'master_password_hash'
        """).fetchone()
        
        if not result:
            return False
        
        stored_value = str(result[0] or "")

        # Current format: a versioned JSON Scrypt verifier.
        if stored_value.startswith("{"):
            try:
                verifier = json.loads(stored_value)
                if verifier.get("version") != 2 or verifier.get("kdf") != "scrypt":
                    return False
                salt = base64.b64decode(verifier["salt"], validate=True)
                expected = base64.b64decode(verifier["hash"], validate=True)
                if len(salt) < 16 or len(expected) != self.SCRYPT_LENGTH:
                    return False
                actual = self._derive_key_scrypt_params(master_password, salt, verifier)
                return hmac.compare_digest(actual, expected)
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                return False

        # Legacy format: raw unsalted SHA-256 hex. Migrate immediately after a
        # successful comparison so existing installations remain compatible.
        provided_hash = hashlib.sha256(master_password.encode()).hexdigest()
        if not hmac.compare_digest(stored_value, provided_hash):
            return False
        try:
            self._store_master_password_verifier(master_password, cursor)
            self.db.conn.commit()
        except Exception:
            # A correct password should still unlock if migration cannot be
            # persisted; the next successful unlock will retry it.
            pass
        return True
    
    def get_credentials(self, master_password: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Get credentials using master password.

        Auto-migrates legacy SHA256-encrypted credentials to Scrypt on first use.

        Args:
            master_password: Master password for decryption

        Returns:
            Tuple of (email, password) or (None, None) if not found/invalid
        """
        if not self.verify_master_password(master_password):
            return None, None

        cursor = self.db.conn.cursor()
        result = cursor.execute("""
            SELECT email, encrypted_password, salt, kdf_params FROM credentials
            ORDER BY updated_at DESC LIMIT 1
        """).fetchone()

        if not result:
            return None, None

        email, encrypted_password, salt_b64, kdf_params_json = result

        # Decrypt password
        try:
            # Check if this is a legacy SHA256-encrypted credential (no kdf_params)
            if kdf_params_json is None:
                # Legacy decryption using SHA256
                encryption_key = self._derive_key_legacy_sha256(master_password, salt_b64)
                fernet_key = base64.urlsafe_b64encode(encryption_key)
                f = Fernet(fernet_key)
                password = f.decrypt(encrypted_password.encode()).decode()

                # Auto-migrate to Scrypt
                self.store_credentials(email, password, master_password)

                return email, password
            else:
                # Modern Scrypt decryption
                kdf_params = json.loads(kdf_params_json)

                if kdf_params.get("kdf") == "scrypt":
                    salt = base64.b64decode(salt_b64)
                    encryption_key = self._derive_key_scrypt_params(master_password, salt, kdf_params)
                    fernet_key = base64.urlsafe_b64encode(encryption_key)
                    f = Fernet(fernet_key)
                    password = f.decrypt(encrypted_password.encode()).decode()
                    return email, password
                else:
                    # Unknown KDF
                    return None, None

        except (ValueError, TypeError) as e:
            # Invalid encrypted data or key format
            return None, None
        except Exception as e:
            # Unexpected decryption error - log it
            self._log(f"Unexpected error in get_credentials: {e}", error=str(e))
            return None, None

    def create_session(self, email: str, password: str):
        """Create 24h session file"""
        session_data = {
            'email': email,
            'password': password,
            'expires': (datetime.now() + timedelta(hours=self.session_duration_hours)).isoformat()
        }
        
        # Encrypt session data
        encrypted_data = self._encrypt(json.dumps(session_data))
        
        # Write to file
        with open(self.session_file, 'w') as f:
            f.write(encrypted_data)
    
    def validate_session(self) -> bool:
        """Check if session file exists and is valid"""
        if not os.path.exists(self.session_file):
            return False

        try:
            with open(self.session_file, 'r') as f:
                encrypted_data = f.read()

            # Decrypt
            decrypted_data = self._decrypt(encrypted_data)
            if not decrypted_data:
                return False

            session_data = json.loads(decrypted_data)

            # Check expiration
            expires = datetime.fromisoformat(session_data['expires'])
            return datetime.now() < expires

        except (FileNotFoundError, PermissionError) as e:
            # Session file missing or inaccessible
            return False
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Corrupt session data
            return False
        except Exception as e:
            # Unexpected error
            self._log(f"Session validation error: {e}", error=str(e))
            return False
    
    def get_credentials_from_session(self) -> Tuple[Optional[str], Optional[str]]:
        """Get credentials from valid session"""
        if not self.validate_session():
            return None, None

        try:
            with open(self.session_file, 'r') as f:
                encrypted_data = f.read()

            decrypted_data = self._decrypt(encrypted_data)
            session_data = json.loads(decrypted_data)

            return session_data['email'], session_data['password']
        except (FileNotFoundError, PermissionError) as e:
            # Session file missing or inaccessible
            return None, None
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Corrupt or invalid session data
            return None, None
        except Exception as e:
            # Unexpected error
            self._log(f"Error reading session: {e}", error=str(e))
            return None, None
    
    def clear_session(self):
        """Delete session file"""
        if os.path.exists(self.session_file):
            os.remove(self.session_file)
