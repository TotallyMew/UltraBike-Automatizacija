"""
Session Manager - Handles 24h auto-login sessions
Uses machine-specific encryption for security
"""

import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import base64

class SessionManager:
    def __init__(self, db_manager):
        self.db = db_manager
        from Utilities.AppPaths import get_default_session_path
        self.session_file = str(get_default_session_path())
        self.session_duration_hours = 24
    
    def _get_machine_id(self):
        """Get unique machine identifier"""
        # Use computer name + username as machine ID
        import platform
        import getpass
        machine_string = f"{platform.node()}-{getpass.getuser()}"
        return hashlib.sha256(machine_string.encode()).hexdigest()
    
    def _get_encryption_key(self):
        """Generate encryption key from machine ID"""
        machine_id = self._get_machine_id()
        # Derive a valid Fernet key from machine ID
        key_material = hashlib.sha256(machine_id.encode()).digest()
        return base64.urlsafe_b64encode(key_material)
    
    def _encrypt(self, data: str) -> str:
        """Encrypt data with machine-specific key"""
        key = self._get_encryption_key()
        f = Fernet(key)
        return f.encrypt(data.encode()).decode()
    
    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt data with machine-specific key"""
        try:
            key = self._get_encryption_key()
            f = Fernet(key)
            return f.decrypt(encrypted_data.encode()).decode()
        except:
            return None
    
    def has_master_password(self) -> bool:
        """Check if master password is set in database"""
        cursor = self.db.conn.cursor()
    
        # Check if master password hash exists in settings
        result = cursor.execute("""
            SELECT value FROM settings WHERE key = 'master_password_hash'
        """).fetchone()
    
        return result is not None

    def set_master_password(self, master_password: str) -> None:
        """Persist master password hash in settings (no credentials stored)."""
        master_hash = hashlib.sha256(master_password.encode()).hexdigest()
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES ('master_password_hash', ?, ?)
            """,
            (master_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        )
        self.db.conn.commit()
    
    def store_credentials(self, email: str, password: str, master_password: str):
        """Store encrypted credentials in database"""
        # Hash master password for verification
        master_hash = hashlib.sha256(master_password.encode()).hexdigest()
        
        # Generate salt
        salt = secrets.token_hex(16)
        
        # Encrypt password with master password + salt
        combined_key = hashlib.sha256(f"{master_password}{salt}".encode()).digest()
        fernet_key = base64.urlsafe_b64encode(combined_key)
        f = Fernet(fernet_key)
        encrypted_password = f.encrypt(password.encode()).decode()
        
        # Store in database
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO credentials 
            (email, encrypted_password, salt, updated_at)
            VALUES (?, ?, ?, ?)
        """, (email, encrypted_password, salt, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        # Also store master password hash in settings
        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES ('master_password_hash', ?, ?)
        """, (master_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
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
        """Store encrypted external-service credentials in database."""
        salt = secrets.token_hex(16)
        combined_key = hashlib.sha256(f"{master_password}{salt}".encode()).digest()
        fernet_key = base64.urlsafe_b64encode(combined_key)
        f = Fernet(fernet_key)
        encrypted_password = f.encrypt(password.encode()).decode()

        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO external_credentials
            (service_key, username, encrypted_password, salt, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (service_key, username, encrypted_password, salt, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        )
        self.db.conn.commit()

    def get_external_credentials(self, service_key: str, master_password: str) -> tuple:
        """Decrypt and return (username, password) for external service."""
        if not self.verify_master_password(master_password):
            return None, None

        cursor = self.db.conn.cursor()
        row = cursor.execute(
            """
            SELECT username, encrypted_password, salt
            FROM external_credentials
            WHERE service_key = ?
            """,
            (service_key,),
        ).fetchone()

        if not row:
            return None, None

        username, encrypted_password, salt = row
        try:
            combined_key = hashlib.sha256(f"{master_password}{salt}".encode()).digest()
            fernet_key = base64.urlsafe_b64encode(combined_key)
            f = Fernet(fernet_key)
            password = f.decrypt(encrypted_password.encode()).decode()
            return username, password
        except Exception:
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
        """Verify master password against stored hash"""
        cursor = self.db.conn.cursor()
        result = cursor.execute("""
            SELECT value FROM settings WHERE key = 'master_password_hash'
        """).fetchone()
        
        if not result:
            return False
        
        stored_hash = result[0]
        provided_hash = hashlib.sha256(master_password.encode()).hexdigest()
        
        return stored_hash == provided_hash
    
    def get_credentials(self, master_password: str) -> tuple:
        """Get credentials using master password"""
        if not self.verify_master_password(master_password):
            return None, None
        
        cursor = self.db.conn.cursor()
        result = cursor.execute("""
            SELECT email, encrypted_password, salt FROM credentials
            ORDER BY updated_at DESC LIMIT 1
        """).fetchone()
        
        if not result:
            return None, None
        
        email, encrypted_password, salt = result
        
        # Decrypt password
        try:
            combined_key = hashlib.sha256(f"{master_password}{salt}".encode()).digest()
            fernet_key = base64.urlsafe_b64encode(combined_key)
            f = Fernet(fernet_key)
            password = f.decrypt(encrypted_password.encode()).decode()
            return email, password
        except:
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
        
        except:
            return False
    
    def get_credentials_from_session(self) -> tuple:
        """Get credentials from valid session"""
        if not self.validate_session():
            return None, None
        
        try:
            with open(self.session_file, 'r') as f:
                encrypted_data = f.read()
            
            decrypted_data = self._decrypt(encrypted_data)
            session_data = json.loads(decrypted_data)
            
            return session_data['email'], session_data['password']
        except:
            return None, None
    
    def clear_session(self):
        """Delete session file"""
        if os.path.exists(self.session_file):
            os.remove(self.session_file)