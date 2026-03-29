from Database.SessionManager import SessionManager
from Database.DatabaseManager import DatabaseManager


class CredentialManager:
    def __init__(self, db_manager=None):
        # Database setup
        self.db = db_manager if db_manager else DatabaseManager()
        self.session_manager = SessionManager(self.db)

    # --- Admin credentials (encrypted with master password) ---

    def save_credentials(self, email: str, password: str, master_password: str) -> None:
        """Store admin credentials encrypted with master password."""
        if not master_password:
            raise ValueError("Master password is required to store credentials.")
        self.session_manager.store_credentials(email, password, master_password)

    def get_credentials_with_master(self, master_password: str) -> tuple:
        """Decrypt and return (email, password) using master password."""
        return self.session_manager.get_credentials(master_password)

    def get_last_saved_email(self) -> str:
        """Get last stored admin email without decrypting password."""
        try:
            cursor = self.db.conn.cursor()
            row = cursor.execute(
                "SELECT email FROM credentials ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            return row[0] if row and row[0] else ""
        except Exception:
            return ""

    # --- Master password ---

    def create_master_password(self, master_password: str) -> None:
        self.session_manager.set_master_password(master_password)

    def has_master_password(self) -> bool:
        return self.session_manager.has_master_password()

    def verify_master_password(self, master_password: str) -> bool:
        return self.session_manager.verify_master_password(master_password)

    # --- 24h auto-login session (machine-encrypted) ---

    def create_session(self, email: str, password: str) -> None:
        self.session_manager.create_session(email, password)

    def get_saved_credentials(self) -> tuple:
        """Session-only retrieval (database requires master password)."""
        if self.session_manager.validate_session():
            email, password = self.session_manager.get_credentials_from_session()
            if email and password:
                return email, password
        return None, None

    # --- External brand credentials (encrypted with master password) ---

    def has_external_credentials(self, service_key: str) -> bool:
        return self.session_manager.has_external_credentials(service_key)

    def save_external_credentials(self, service_key: str, username: str, password: str, master_password: str) -> None:
        if not master_password:
            raise ValueError("Master password is required to store external credentials.")
        self.session_manager.store_external_credentials(service_key, username, password, master_password)

    def get_external_credentials_with_master(self, service_key: str, master_password: str) -> tuple:
        return self.session_manager.get_external_credentials(service_key, master_password)

    def get_external_username(self, service_key: str) -> str:
        return self.session_manager.get_external_username(service_key)

    def clear_external_credentials(self, service_key: str) -> None:
        self.session_manager.clear_external_credentials(service_key)