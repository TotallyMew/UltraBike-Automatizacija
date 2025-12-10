import os
import re
from datetime import datetime

class TranslationImporter:
    """
    Import translation .txt files into database
    Consolidates 13 separate files into one table
    """
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.imported_count = 0
        self.skipped_count = 0
        self.duplicate_count = 0
    
    def _detect_category(self, source_term: str, target_term: str) -> str:
        """
        Auto-detect category based on term content
        """
        term = (source_term + " " + target_term).upper()
        
        # Color keywords
        color_keywords = [
            'BLACK', 'WHITE', 'RED', 'BLUE', 'GREEN', 'YELLOW',
            'JUODA', 'BALTA', 'RAUDONA', 'MĖLYNA', 'ŽALIA', 'GELTONA',
            'GREY', 'SILVER', 'GOLD', 'PINK', 'PURPLE',
            'PILKA', 'SIDABRINĖ', 'AUKSINĖ', 'ROŽINĖ', 'VIOLETINĖ',
            'COLOR', 'COLOUR', 'SPALVA'
        ]
        
        for keyword in color_keywords:
            if keyword in term:
                return 'color'
        
        # Material keywords
        material_keywords = [
            'ALUMINIUM', 'ALIUMINIS', 'CARBON', 'ANGLIES',
            'STEEL', 'PLIENINIS', 'PLASTIC', 'PLASTIKINIAI',
            'FOAM', 'PUTOS', 'POLYCARBONATE', 'POLIKARBONATAS'
        ]
        
        for keyword in material_keywords:
            if keyword in term:
                return 'material'
        
        # Property keywords (APPROX, GLOSS, MATT, etc.)
        property_keywords = [
            'APPROX', 'APIE', 'GLOSS', 'BLIZGUS',
            'MATT', 'MATINIS', 'MECHANICAL', 'MECHANINIS'
        ]
        
        for keyword in property_keywords:
            if keyword in term:
                return 'property'
        
        # Default to component
        return 'component'
    
    def _parse_translation_file(self, file_path: str) -> list:
        """
        Parse a translation file
        Returns list of (source, target) tuples
        """
        translations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig removes BOM
                for line in f:
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('//'):
                        continue
                    
                    # Parse "KEY:VALUE" or "KEY=VALUE"
                    if ':' in line:
                        parts = line.split(':', 1)
                    elif '=' in line:
                        parts = line.split('=', 1)
                    else:
                        continue
                    
                    if len(parts) == 2:
                        source = parts[0].strip()
                        target = parts[1].strip()
                        
                        if source and target:
                            translations.append((source, target))
        
        except Exception as e:
            print(f"  ⚠ Error reading {file_path}: {e}")
        
        return translations
    
    def _insert_translation(self, source_lang: str, target_lang: str, 
                           source_term: str, target_term: str, category: str):
        """
        Insert translation into database (skip if duplicate)
        """
        cursor = self.db.conn.cursor()
        
        # Check if already exists
        existing = cursor.execute("""
            SELECT id FROM translations 
            WHERE source_lang = ? AND target_lang = ? AND source_term = ?
        """, (source_lang, target_lang, source_term)).fetchone()
        
        if existing:
            self.duplicate_count += 1
            return False
        
        # Insert new translation
        cursor.execute("""
            INSERT INTO translations 
            (source_lang, target_lang, category, source_term, target_term, created_by)
            VALUES (?, ?, ?, ?, ?, 'system')
        """, (source_lang, target_lang, category, source_term, target_term))
        
        self.imported_count += 1
        return True
    
    def import_file(self, file_path: str, source_lang: str, target_lang: str):
        """
        Import a single translation file
        """
        if not os.path.exists(file_path):
            print(f"  ⚠ File not found: {file_path}")
            self.skipped_count += 1
            return
        
        filename = os.path.basename(file_path)
        print(f"  Importing {filename}...")
        
        translations = self._parse_translation_file(file_path)
        
        for source, target in translations:
            category = self._detect_category(source, target)
            self._insert_translation(source_lang, target_lang, source, target, category)
        
        print(f"    ✓ {len(translations)} translations parsed")
    
    def import_all(self):
        """
        Import all translation files from Assets/Translations/
        """
        print("\n" + "=" * 60)
        print("IMPORTING TRANSLATIONS")
        print("=" * 60)
        print()
        
        base_path = "Assets/Translations/"
        
        # List of all translation files
        files_to_import = [
            # Component translations (ENG → LT)
            (f"{base_path}vertimasDetalesENG-LT.txt", "EN", "LT"),
            
            # Property translations (ENG → LT)
            (f"{base_path}vertimasSavybesENG-LT.txt", "EN", "LT"),
            (f"{base_path}vertimasSavybesLT-ENG.txt", "LT", "EN"),
            
            # Property translations (PL → LT)
            (f"{base_path}vertimasDetalesPL-LT.txt", "PL", "LT"),
            (f"{base_path}vertimasSavybesPL-LT.txt", "PL", "LT"),
            
            # Brand-specific translations
            (f"{base_path}BassoENG-LT.txt", "EN", "LT"),
            (f"{base_path}FactorENG-LT.txt", "EN", "LT"),
            (f"{base_path}LeeCouganENG-LT.txt", "EN", "LT"),
            (f"{base_path}LookENG-LT.txt", "EN", "LT"),
            (f"{base_path}OctaneENG-LT.txt", "EN", "LT"),
            (f"{base_path}PinarelloENG-LT.txt", "EN", "LT"),
            (f"{base_path}RascalENG-LT.txt", "EN", "LT"),
            (f"{base_path}RondoENG-LT.txt", "EN", "LT"),
        ]
        
        for file_path, source_lang, target_lang in files_to_import:
            self.import_file(file_path, source_lang, target_lang)
        
        # Commit all changes
        self.db.conn.commit()
        
        print()
        print("=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"  Imported: {self.imported_count} translations")
        print(f"  Duplicates skipped: {self.duplicate_count}")
        print(f"  Files not found: {self.skipped_count}")
        print("=" * 60)
        print()
        
        # Show category breakdown
        cursor = self.db.conn.cursor()
        categories = cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM translations 
            GROUP BY category 
            ORDER BY count DESC
        """).fetchall()
        
        print("Category breakdown:")
        for cat in categories:
            print(f"  {cat['category']}: {cat['count']} translations")
        print()
