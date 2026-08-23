import sqlite3
from pathlib import Path
import threading
from datetime import datetime, timezone

class DatabaseManager:
    """Manages SQLite database connection and schema"""

    LATEST_SCHEMA_VERSION = 5
    
    def __init__(self, db_path=None):
        if db_path is None:
            from Utilities.AppPaths import get_default_db_path
            db_path = get_default_db_path()

        self.db_path = str(Path(db_path))
        self.write_lock = threading.RLock()
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

        # Earnings tracker.  Money is stored as integer cents and timestamps as
        # UTC ISO-8601 strings so calculations do not depend on the workstation
        # locale.  Custom brands are archived instead of deleted, preserving the
        # brand on old earning records.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earning_brands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL CHECK(mode IN ('stopwatch', 'countdown')),
                target_seconds INTEGER,
                status TEXT NOT NULL CHECK(status IN ('running', 'paused', 'completed')),
                allow_overtime INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                quest_kind TEXT CHECK(quest_kind IN ('sku', 'earnings', 'focus')),
                quest_target_value INTEGER CHECK(quest_target_value > 0),
                quest_completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY(session_id) REFERENCES work_sessions(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earning_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL,
                product_name TEXT,
                brand_id INTEGER,
                product_type TEXT NOT NULL CHECK(product_type IN ('bicycle', 'frameset', 'other')),
                payout_cents INTEGER NOT NULL CHECK(payout_cents >= 0),
                earned_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                session_id INTEGER,
                processing_history_id INTEGER UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(brand_id) REFERENCES earning_brands(id),
                FOREIGN KEY(session_id) REFERENCES work_sessions(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earning_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_cents INTEGER NOT NULL CHECK(target_cents > 0),
                started_at TEXT NOT NULL,
                deadline_date TEXT,
                status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'archived', 'cancelled')),
                completed_at TEXT,
                final_earned_cents INTEGER,
                final_product_count INTEGER,
                final_tracked_seconds REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
    
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_brand ON processing_history(brand)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_status ON processing_history(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_date ON processing_history(processed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_translations_lookup ON translations(source_lang, target_lang, source_term)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_earning_entries_date ON earning_entries(earned_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_earning_entries_sku ON earning_entries(sku)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_earning_entries_brand ON earning_entries(brand_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_earning_entries_session ON earning_entries(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_segments_session ON work_segments(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_segments_start ON work_segments(started_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_earning_goals_status ON earning_goals(status)")

        now_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        builtin_brands = (
            "KROSS", "Pinarello", "Basso", "Factor", "TREK",
            "Rondo", "Octane", "Rascal", "Lee Cougan",
        )
        for brand in builtin_brands:
            cursor.execute(
                """
                INSERT OR IGNORE INTO earning_brands
                    (name, is_builtin, is_active, created_at, updated_at)
                VALUES (?, 1, 1, ?, ?)
                """,
                (brand, now_utc, now_utc),
            )
    
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

        self._run_ordered_migrations()

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

    def _run_ordered_migrations(self) -> None:
        """Apply durable, ordered migrations to both existing and new databases."""

        current = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        migrations = {
            1: self._migration_remove_obsolete_integrations,
            2: self._migration_operation_runs,
            3: self._migration_goal_adjustments,
            4: self._migration_session_quests,
            5: self._migration_spotify,
        }
        if current > self.LATEST_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than this app supports "
                f"({self.LATEST_SCHEMA_VERSION})"
            )
        for version in range(current + 1, self.LATEST_SCHEMA_VERSION + 1):
            migration = migrations[version]
            with self.conn:
                migration()
                self.conn.execute(f"PRAGMA user_version = {version}")

    def _migration_remove_obsolete_integrations(self) -> None:
        # Compatibility cleanup only: remove secrets/settings from the retired
        # translation provider while retaining active brand portal credentials.
        self.conn.execute("DELETE FROM settings WHERE key = ?", ("deepl_api_key",))
        self.conn.execute(
            "DELETE FROM external_credentials WHERE lower(service_key) IN (?, ?)",
            ("deepl", "deepl_api"),
        )

    def _migration_operation_runs(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_runs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                source_route TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'running', 'stopping', 'succeeded', 'partial',
                    'failed', 'cancelled', 'interrupted'
                )),
                current INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                stage TEXT,
                message TEXT,
                summary_json TEXT,
                error_summary TEXT,
                output_path TEXT,
                resume_kind TEXT,
                resume_ref TEXT,
                batch_id TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operation_runs_updated "
            "ON operation_runs(updated_at DESC)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_operation_runs_status "
            "ON operation_runs(status)"
        )

    def _migration_goal_adjustments(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS earning_goal_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(goal_id) REFERENCES earning_goals(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_goal_adjustments_goal "
            "ON earning_goal_adjustments(goal_id, created_at)"
        )

    def _migration_session_quests(self) -> None:
        self._ensure_column(
            "work_sessions",
            "quest_kind",
            "TEXT",
        )
        self._ensure_column(
            "work_sessions",
            "quest_target_value",
            "INTEGER",
        )
        self._ensure_column("work_sessions", "quest_completed_at", "TEXT")

    def _migration_spotify(self) -> None:
        """Add protected Spotify authorization state and local play history."""

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spotify_auth (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                encrypted_refresh_token TEXT NOT NULL,
                spotify_user_id TEXT,
                display_name TEXT,
                image_url TEXT,
                connected_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spotify_plays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id TEXT NOT NULL,
                track_name TEXT NOT NULL,
                artist_display TEXT,
                album_name TEXT,
                duration_ms INTEGER NOT NULL DEFAULT 0 CHECK(duration_ms >= 0),
                played_at TEXT NOT NULL,
                session_id INTEGER,
                context_uri TEXT,
                context_type TEXT,
                recorded_at TEXT NOT NULL,
                UNIQUE(track_id, played_at),
                FOREIGN KEY(session_id) REFERENCES work_sessions(id) ON DELETE SET NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spotify_play_artists (
                play_id INTEGER NOT NULL,
                artist_id TEXT NOT NULL DEFAULT '',
                artist_name TEXT NOT NULL,
                artist_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(play_id, artist_id, artist_name),
                FOREIGN KEY(play_id) REFERENCES spotify_plays(id) ON DELETE CASCADE
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spotify_plays_date "
            "ON spotify_plays(played_at DESC)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spotify_plays_session "
            "ON spotify_plays(session_id, played_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spotify_play_artists_name "
            "ON spotify_play_artists(artist_name COLLATE NOCASE)"
        )
    
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
            'description_folders', 'earning_brands', 'earning_entries',
            'work_sessions', 'work_segments', 'earning_goals',
            'earning_goal_adjustments', 'operation_runs', 'spotify_auth',
            'spotify_plays', 'spotify_play_artists'
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
