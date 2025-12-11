import sqlite3
import os
from datetime import datetime

class DatabaseManager:
    """Manages SQLite database connection and schema"""
    
    def __init__(self, db_path="ultrabike.db"):
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._initialize_schema()
    
    def _connect(self):
        """Connect to SQLite database"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        print(f"✓ Connected to database: {self.db_path}")
    
    def _initialize_schema(self):
        """Initialize database schema (silently if already exists)"""
        cursor = self.conn.cursor()
    
        # Check if schema already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='settings'
        """)
    
        schema_exists = cursor.fetchone() is not None
    
        if not schema_exists:
            print("Creating database schema...")
    
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
        if not schema_exists:
            print("  ✓ credentials table")
    
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
                processed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if not schema_exists:
            print("  ✓ processing_history table")
    
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
        if not schema_exists:
            print("  ✓ recent_products table")
    
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
        if not schema_exists:
            print("  ✓ translations table")
    
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
        if not schema_exists:
            print("  ✓ settings table")
    
        if not schema_exists:
            print("Creating indexes...")
    
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_brand ON processing_history(brand)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_status ON processing_history(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_date ON processing_history(processed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_translations_lookup ON translations(source_lang, target_lang, source_term)")
    
        self.conn.commit()
    
        if not schema_exists:
            print("✓ Database schema initialized")
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("✓ Database connection closed")