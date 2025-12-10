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
        """Create all tables if they don't exist"""
        cursor = self.conn.cursor()
        
        print("Creating database schema...")
        
        # 1. Credentials table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                service TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                password_encrypted BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✓ credentials table")
        
        # 2. Processing history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                product_code TEXT NOT NULL,
                url_or_code TEXT,
                status TEXT NOT NULL CHECK(status IN ('success', 'failed', 'partial')),
                error_message TEXT,
                duration_seconds INTEGER,
                features_uploaded INTEGER,
                images_uploaded INTEGER,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✓ processing_history table")
        
        # 3. Recent products
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                product_code TEXT NOT NULL,
                url_or_code TEXT,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                use_count INTEGER DEFAULT 1,
                UNIQUE(brand, product_code)
            )
        """)
        print("  ✓ recent_products table")
        
        # 4. Translations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_lang TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                category TEXT NOT NULL,
                source_term TEXT NOT NULL,
                target_term TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT DEFAULT 'system',
                UNIQUE(source_lang, target_lang, source_term)
            )
        """)
        print("  ✓ translations table")
        
        # 5. Settings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL CHECK(value_type IN ('bool', 'string', 'int', 'path')),
                category TEXT,
                description TEXT,
                default_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✓ settings table")
        
        # Create indexes
        print("Creating indexes...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_translations_lookup 
            ON translations(source_lang, target_lang, source_term)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_date 
            ON processing_history(processed_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_recent_used 
            ON recent_products(last_used DESC)
        """)
        
        self.conn.commit()
        print("✓ Database schema initialized\n")
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("✓ Database connection closed")
