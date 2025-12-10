import os
import json
import hashlib
import uuid
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import base64

class SessionManager:
    """
    Manages master password, credential encryption, and 24-hour sessions
    """
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.session_file = "session.dat"
        self.master_key = None  # Derived from master password
        self.credentials_cache = {}  # Decrypted credentials in memory
    
    # ==================== MASTER PASSWORD ====================
    
    def _derive_key_from_password(self, password: str) -> bytes:
        """
        Convert password to encryption key using SHA256
        """
        password_bytes = password.encode('utf-8')
        key_bytes = hashlib.sha256(password_bytes).digest()
        return base64.urlsafe_b64encode(key_bytes)
    
    def set_master_password(self, password: str) -> bool:
        """
        Set master password (first-time setup)
        """
        if len(password) < 6:
            print("❌ Password must be at least 6 characters")
            return False
        
        self.master_key = self._derive_key_from_password(password)
        print("✓ Master password set")
        return True
    
    def unlock_with_password(self, password: str) -> bool:
        """
        Unlock session with master password
        """
        test_key = self._derive_key_from_password(password)
        
        # Test if password is correct by trying to decrypt a credential
        cursor = self.db.conn.cursor()
        test_cred = cursor.execute(
            "SELECT password_encrypted FROM credentials LIMIT 1"
        ).fetchone()
        
        if test_cred:
            try:
                cipher = Fernet(test_key)
                cipher.decrypt(test_cred['password_encrypted'])
                self.master_key = test_key
                print("✓ Master password correct")
                return True
            except:
                print("❌ Incorrect master password")
                return False
        else:
            # No credentials yet, accept password
            self.master_key = test_key
            print("✓ Master password accepted (first credential)")
            return True
    
    # ==================== CREDENTIAL ENCRYPTION ====================
    
    def save_credential(self, service: str, username: str, password: str):
        """
        Save encrypted credential to database
        """
        if not self.master_key:
            raise Exception("Master key not set")
        
        cipher = Fernet(self.master_key)
        encrypted_password = cipher.encrypt(password.encode('utf-8'))
        
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO credentials 
            (service, username, password_encrypted, updated_at)
            VALUES (?, ?, ?, ?)
        """, (service, username, encrypted_password, datetime.now()))
        
        self.db.conn.commit()
        
        # Cache in memory
        self.credentials_cache[service] = {
            'username': username,
            'password': password
        }
        
        print(f"✓ Saved credentials for {service}")
    
    def get_credential(self, service: str) -> dict:
        """
        Get decrypted credential from database
        """
        # Check cache first
        if service in self.credentials_cache:
            return self.credentials_cache[service]
        
        if not self.master_key:
            raise Exception("Master key not set")
        
        cursor = self.db.conn.cursor()
        result = cursor.execute("""
            SELECT username, password_encrypted 
            FROM credentials 
            WHERE service = ?
        """, (service,)).fetchone()
        
        if not result:
            return None
        
        cipher = Fernet(self.master_key)
        decrypted_password = cipher.decrypt(result['password_encrypted']).decode('utf-8')
        
        credential = {
            'username': result['username'],
            'password': decrypted_password
        }
        
        # Cache it
        self.credentials_cache[service] = credential
        
        return credential
    
    # ==================== SESSION FILE (24-HOUR AUTO-LOGIN) ====================
    
    def _get_machine_key(self) -> bytes:
        """
        Generate machine-specific encryption key
        Uses MAC address UUID for uniqueness
        """
        machine_id = str(uuid.getnode())  # MAC address as unique ID
        key_bytes = hashlib.sha256(machine_id.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(key_bytes)
    
    def create_session(self):
        """
        Create 24-hour session file with encrypted credentials
        """
        if not self.master_key:
            raise Exception("Master key not set")
        
        # Get all credentials
        cursor = self.db.conn.cursor()
        all_creds = cursor.execute("SELECT service FROM credentials").fetchall()
        
        session_data = {
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(hours=24)).isoformat(),
            'credentials': {}
        }
        
        # Decrypt and store all credentials
        for cred_row in all_creds:
            service = cred_row['service']
            cred = self.get_credential(service)
            if cred:
                session_data['credentials'][service] = cred
        
        # Encrypt session data with machine-specific key
        machine_key = self._get_machine_key()
        cipher = Fernet(machine_key)
        
        session_json = json.dumps(session_data)
        encrypted_session = cipher.encrypt(session_json.encode('utf-8'))
        
        # Write to file
        with open(self.session_file, 'wb') as f:
            f.write(encrypted_session)
        
        print(f"✓ Session created (expires in 24 hours)")
    
    def load_session(self) -> bool:
        """
        Load session from file (auto-login if valid)
        Returns True if session loaded successfully
        """
        if not os.path.exists(self.session_file):
            return False
        
        try:
            # Read encrypted session
            with open(self.session_file, 'rb') as f:
                encrypted_session = f.read()
            
            # Decrypt with machine key
            machine_key = self._get_machine_key()
            cipher = Fernet(machine_key)
            decrypted_json = cipher.decrypt(encrypted_session).decode('utf-8')
            
            session_data = json.loads(decrypted_json)
            
            # Check if expired
            expires_at = datetime.fromisoformat(session_data['expires_at'])
            if datetime.now() > expires_at:
                print("⚠ Session expired (>24 hours old)")
                os.remove(self.session_file)
                return False
            
            # Load credentials into cache
            self.credentials_cache = session_data['credentials']
            
            # Reconstruct master key (we can't store it, but we have decrypted creds)
            # This is a workaround - session is valid, credentials are decrypted
            
            print(f"✓ Session loaded (expires in {(expires_at - datetime.now()).seconds // 3600}h)")
            return True
            
        except Exception as e:
            print(f"⚠ Session file corrupted: {e}")
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            return False
    
    def destroy_session(self):
        """
        Delete session file (logout)
        """
        if os.path.exists(self.session_file):
            os.remove(self.session_file)
            print("✓ Session destroyed")
        
        self.credentials_cache = {}
        self.master_key = None
