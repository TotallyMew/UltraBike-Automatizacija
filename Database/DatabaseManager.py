import sqlite3
from pathlib import Path

class DatabaseManager:
    """Manages SQLite database connection and schema"""
    
    def __init__(self, db_path=None):
        if db_path is None:
            from Utilities.AppPaths import get_default_db_path
            db_path = get_default_db_path()

        self.db_path = str(Path(db_path))
        self.conn = None
        self._connect()
        self._initialize_schema()
    
    def _connect(self):
        """Connect to SQLite database"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
    
    def _initialize_schema(self):
        """Initialize database schema (silently if already exists)"""
        cursor = self.conn.cursor()
    
        # Check if schema already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='settings'
        """)
    
        schema_exists = cursor.fetchone() is not None

    
        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                encrypted_password TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS external_credentials (
                service_key TEXT PRIMARY KEY,
                username TEXT,
                encrypted_password TEXT NOT NULL,
                salt TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                product_code TEXT NOT NULL,
                url_or_code TEXT,
                status TEXT NOT NULL,
                duration_seconds REAL,
                features_uploaded INTEGER,
                images_uploaded INTEGER,
                error_message TEXT,
                failed_stage TEXT,
                batch_id TEXT,
                details_json TEXT,
                processed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                product_code TEXT NOT NULL,
                url_or_code TEXT,
                use_count INTEGER DEFAULT 1,
                last_used TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(brand, product_code)
            )
        """)
    
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_lang TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                source_term TEXT NOT NULL,
                target_term TEXT NOT NULL,
                category TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_lang, target_lang, source_term)
            )
        """)
    
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                value_type TEXT DEFAULT 'string',
                category TEXT,
                description TEXT,
                default_value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


        cursor.execute("""
            CREATE TABLE IF NOT EXISTS descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description_lt TEXT,
                description_en TEXT,
                description_lv TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_brand ON processing_history(brand)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_status ON processing_history(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_date ON processing_history(processed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_translations_lookup ON translations(source_lang, target_lang, source_term)")
    
        self.conn.commit()

        # Lightweight migrations for existing DBs
        try:
            self._ensure_column("processing_history", "details_json", "TEXT")
        except Exception:
            pass

        # Seed translations on first run (from bundled Assets/Translations)
        try:
            row = cursor.execute("SELECT COUNT(1) AS c FROM translations").fetchone()
            existing_count = int(row[0] if row else 0)
            if existing_count == 0:
                from Database.TranslationImporter import TranslationImporter
                TranslationImporter(self).import_all()
        except Exception:
            # Never block startup if translation seeding fails; app can still run.
            pass
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def _ensure_column(self, table_name: str, column_name: str, column_type: str) -> None:
        """Add a missing column if needed.

        SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN, so we
        check pragma_table_info first.
        """
        cur = self.conn.cursor()
        cols = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {c[1] for c in cols}  # name is index 1
        if column_name in existing:
            return
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        self.conn.commit()