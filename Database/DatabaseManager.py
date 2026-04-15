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
        # Use a timeout to reduce transient "database is locked" errors.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Better concurrent behavior for background workers (best-effort).
        try:
            self.conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        try:
            # WAL is safe for file-backed DBs; ignore if unsupported.
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            pass
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
                folder TEXT DEFAULT '',
                description_lt TEXT,
                description_en TEXT,
                description_lv TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS description_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
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

        try:
            self._ensure_column("descriptions", "folder", "TEXT DEFAULT ''")
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

    def _validate_identifier(self, identifier: str, identifier_type: str = "identifier") -> None:
        """Validate SQL identifier to prevent SQL injection.

        This method ensures identifiers (table/column names) are safe to use in SQL queries.
        Only allows alphanumeric characters and underscores.

        Args:
            identifier: The table or column name to validate
            identifier_type: Type of identifier for error messages (e.g., "table", "column")

        Raises:
            ValueError: If identifier contains unsafe characters
        """
        # Whitelist of allowed tables for extra safety
        ALLOWED_TABLES = {
            'credentials', 'external_credentials', 'processing_history',
            'recent_products', 'translations', 'settings', 'descriptions',
            'description_folders'
        }

        # Check for empty identifier
        if not identifier or not identifier.strip():
            raise ValueError(f"Invalid {identifier_type} name: cannot be empty")

        # Check for SQL injection patterns (only allow alphanumeric and underscore)
        if not all(c.isalnum() or c == '_' for c in identifier):
            raise ValueError(
                f"Invalid {identifier_type} name '{identifier}': "
                f"only alphanumeric characters and underscores are allowed"
            )

        # Additional safety: if it's a table name, check against whitelist
        if identifier_type == "table" and identifier not in ALLOWED_TABLES:
            raise ValueError(
                f"Invalid table name '{identifier}': not in allowed tables list. "
                f"Allowed tables: {', '.join(sorted(ALLOWED_TABLES))}"
            )

        # Check for SQL keywords that could be dangerous
        SQL_KEYWORDS = {
            'select', 'insert', 'update', 'delete', 'drop', 'create',
            'alter', 'table', 'from', 'where', 'union', 'exec', 'execute'
        }
        if identifier.lower() in SQL_KEYWORDS:
            raise ValueError(
                f"Invalid {identifier_type} name '{identifier}': cannot use SQL keywords"
            )

    def _ensure_column(self, table_name: str, column_name: str, column_type: str) -> None:
        """Add a missing column if needed.

        SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN, so we
        check pragma_table_info first.

        Security: This method validates all identifiers to prevent SQL injection.
        Only accepts hardcoded table names from the allowed whitelist.

        Args:
            table_name: Name of the table (must be in ALLOWED_TABLES whitelist)
            column_name: Name of the column to add (must be alphanumeric + underscore)
            column_type: SQL type for the column (must be alphanumeric + underscore + spaces)

        Raises:
            ValueError: If any identifier contains unsafe characters
        """
        # Validate all identifiers to prevent SQL injection
        self._validate_identifier(table_name, "table")
        self._validate_identifier(column_name, "column")

        # Validate column_type (allows spaces for types like "TEXT DEFAULT ''" or "INTEGER NOT NULL")
        # More permissive than identifiers but still safe
        if not all(c.isalnum() or c in ('_', ' ', "'", '"') for c in column_type):
            raise ValueError(
                f"Invalid column type '{column_type}': "
                f"only alphanumeric characters, underscores, spaces, and quotes are allowed"
            )

        cur = self.conn.cursor()
        # Safe to use f-strings now that we've validated the identifiers
        cols = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {c[1] for c in cols}  # name is index 1
        if column_name in existing:
            return
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        self.conn.commit()