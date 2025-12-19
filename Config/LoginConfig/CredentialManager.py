import json
import os
from Database.SessionManager import SessionManager
from Database.DatabaseManager import DatabaseManager

class CredentialManager:
    def __init__(self, db_manager=None):
        # Legacy JSON path (for migration)
        self.login_path = "Config/LoginConfig/loginInfo.json"
        
        # Database setup
        if db_manager:
            self.db = db_manager
        else:
            self.db = DatabaseManager()
        
        self.session_manager = SessionManager(self.db)
    
    def save_credentials(self, email: str, password: str, master_password: str = None) -> None:
        """
        Save credentials to database (encrypted)
        If master_password provided, encrypts with it
        Otherwise uses session key
        """
        if master_password:
            # Encrypt with master password
            self.session_manager.store_credentials(email, password, master_password)
        else:
            # Just update plaintext JSON for now (legacy)
            credentials = self.load_credentials_json()
            credentials[email] = password
            
            with open(self.login_path, 'w') as f:
                json.dump(credentials, f)
    
    def load_credentials_json(self) -> dict:
        """Load credentials from legacy JSON file"""
        try:
            with open(self.login_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def get_saved_credentials(self) -> tuple:
        """
        Get saved credentials
        Priority: 1) Session-based (encrypted), 2) JSON (legacy)
        """
        # Try session-based credentials first
        if self.session_manager.validate_session():
            email, password = self.session_manager.get_credentials_from_session()
            if email and password:
                return email, password
        
        # Fallback to legacy JSON
        credentials = self.load_credentials_json()
        
        if not credentials:
            return None, None
            
        if len(credentials) > 1:
            # Multiple accounts - GUI must choose which to use
            raise ValueError("Multiple saved accounts found; GUI must select which account to use.")
        else:
            # Single account
            email = next(iter(credentials))
            return email, credentials[email]
    
    def has_master_password(self) -> bool:
        """Check if master password is set"""
        return self.session_manager.has_master_password()
    
    def verify_master_password(self, master_password: str) -> bool:
        """Verify master password"""
        return self.session_manager.verify_master_password(master_password)
    
    def get_credentials_with_master(self, master_password: str) -> tuple:
        """Get credentials using master password"""
        return self.session_manager.get_credentials(master_password)
    
    def create_session(self, email: str, password: str) -> None:
        """Create 24h session after successful login"""
        self.session_manager.create_session(email, password)