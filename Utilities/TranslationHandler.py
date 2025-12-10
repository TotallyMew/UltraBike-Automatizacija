class TranslationHandler:
    """
    Handle translations using database instead of text files
    """
    
    def __init__(self, db_manager=None):
        """
        Initialize with database connection
        If no db_manager provided, creates one (for backward compatibility)
        """
        if db_manager:
            self.db = db_manager
            self.own_db = False  # We don't own this connection
        else:
            # Fallback: create own database connection
            from Database.DatabaseManager import DatabaseManager
            self.db = DatabaseManager()
            self.own_db = True
        
        self._cache = {}  # Cache translations in memory for speed
    
    def get_translation(self, source_term: str, source_lang: str = "EN", 
                       target_lang: str = "LT") -> str:
        """
        Get single translation from database
        
        Args:
            source_term: Term to translate (e.g., "Frame")
            source_lang: Source language code (e.g., "EN", "PL")
            target_lang: Target language code (e.g., "LT")
        
        Returns:
            Translated term, or original if not found
        """
        # Check cache first
        cache_key = f"{source_lang}:{target_lang}:{source_term}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Query database
        cursor = self.db.conn.cursor()
        result = cursor.execute("""
            SELECT target_term 
            FROM translations 
            WHERE source_lang = ? 
            AND target_lang = ? 
            AND source_term = ?
            LIMIT 1
        """, (source_lang, target_lang, source_term)).fetchone()
        
        if result:
            translation = result['target_term']
            self._cache[cache_key] = translation  # Cache it
            return translation
        
        # Not found - return original
        return source_term
    
    def get_all_translations(self, source_lang: str = "EN", 
                           target_lang: str = "LT") -> dict:
        """
        Get all translations for a language pair
        Returns dict of {source_term: target_term}
        
        This replaces the old load_translations() method
        """
        cursor = self.db.conn.cursor()
        results = cursor.execute("""
            SELECT source_term, target_term 
            FROM translations 
            WHERE source_lang = ? AND target_lang = ?
        """, (source_lang, target_lang)).fetchall()
        
        return {row['source_term']: row['target_term'] for row in results}
    
    def translate_first_word(self, value: str, value_translations: dict = None) -> str:
        """
        Translate only the first word of a value
        Used for colors/materials that appear at start of string
        
        Example: "ALUMINIUM 7005" → "ALIUMINIS 7005"
        
        This method kept for backward compatibility with existing scrapers
        """
        if not value:
            return value
        
        value_parts = value.split()
        if not value_parts:
            return value
        
        first_word = value_parts[0].upper()
        
        # If value_translations dict provided (old style), use it
        if value_translations and first_word in value_translations:
            value_parts[0] = value_translations[first_word]
            return " ".join(value_parts)
        
        # Otherwise query database
        translation = self.get_translation(first_word, "EN", "LT")
        
        # Also try Polish if English didn't work
        if translation == first_word:
            translation = self.get_translation(first_word, "PL", "LT")
        
        if translation != first_word:
            value_parts[0] = translation
        
        return " ".join(value_parts)
    
    def translate_to_english(self, input_file: str, output_file: str, 
                           translation_dict: dict = None):
        """
        Translate a file from Lithuanian to English
        Used by translationManager.translateAll()
        
        Kept for backward compatibility
        """
        # If translation_dict provided, use old method
        if translation_dict:
            self._translate_file_with_dict(input_file, output_file, translation_dict)
            return
        
        # Otherwise use database
        with open(input_file, "r", encoding="utf-8") as infile, \
             open(output_file, "w", encoding="utf-8") as outfile:
            
            for line in infile:
                if line.strip():
                    try:
                        key, lithuanian_value = line.strip().split(": ", 1)
                        
                        # Try to translate value
                        english_value = self.get_translation(
                            lithuanian_value.upper(), "LT", "EN"
                        )
                        
                        # If not found, keep original
                        if english_value == lithuanian_value.upper():
                            english_value = lithuanian_value
                        
                        # Also translate first word if it's a material/color
                        english_value = self.translate_first_word(english_value)
                        
                        outfile.write(f"{key}: {english_value}\n")
                    except:
                        outfile.write(line)
                else:
                    outfile.write("\n")
    
    def _translate_file_with_dict(self, input_file: str, output_file: str, 
                                  translation_dict: dict):
        """
        Old method using dictionary (kept for backward compatibility)
        """
        with open(input_file, "r", encoding="utf-8") as infile, \
             open(output_file, "w", encoding="utf-8") as outfile:
            
            for line in infile:
                if line.strip():
                    try:
                        key, lithuanian_value = line.strip().split(": ", 1)
                        english_value = translation_dict.get(
                            lithuanian_value.upper(), lithuanian_value
                        )
                        english_value = self.translate_first_word(
                            english_value, translation_dict
                        )
                        outfile.write(f"{key}: {english_value}\n")
                    except:
                        outfile.write(line)
                else:
                    outfile.write("\n")
    
    def __del__(self):
        """
        Cleanup: close database if we own it
        """
        if hasattr(self, 'own_db') and self.own_db and hasattr(self, 'db'):
            self.db.close()


# ==================== BACKWARD COMPATIBILITY ====================
# Old static methods kept for existing scrapers
# These will be gradually phased out

def load_translations(translation_file: str) -> dict:
    """
    DEPRECATED: Use TranslationHandler.get_all_translations() instead
    Kept for backward compatibility with existing scrapers
    """
    translations = {}
    try:
        with open(translation_file, "r", encoding="utf-8") as file:
            for line in file:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    key = parts[0].strip().title()
                    value = parts[1].strip()
                    translations[key] = value
    except:
        pass
    return translations

def load_value_translations(translation_file: str) -> dict:
    """
    DEPRECATED: Use TranslationHandler.get_all_translations() instead
    Kept for backward compatibility
    """
    value_translations = {}
    try:
        with open(translation_file, "r", encoding="utf-8") as file:
            for line in file:
                parts = line.strip().split(":", 1)
                if len(parts) == 2:
                    original_value = parts[0].strip().upper()
                    translated_value = parts[1].strip()
                    value_translations[original_value] = translated_value
    except:
        pass
    return value_translations