"""
Managers/DescriptionManager.py
Handles description CRUD operations and PrestaShop upload
"""

import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

class DescriptionManager:
    def __init__(self, db_manager, logger=None):
        self.db = db_manager
        self.logger = logger
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("DescriptionManager", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("DescriptionManager", message, exception=exception, **context)
    
    def save_description(self, name: str, description_lt: str, description_en: str, description_lv: str) -> bool:
        """Save or update description in database"""
        self._log("Saving description", name=name)
        
        try:
            cursor = self.db.conn.cursor()
            
            # Check if exists
            existing = cursor.execute(
                "SELECT id FROM descriptions WHERE name = ?", (name,)
            ).fetchone()
            
            if existing:
                # Update
                cursor.execute("""
                    UPDATE descriptions 
                    SET description_lt = ?, description_en = ?, description_lv = ?, 
                        updated_at = ?
                    WHERE name = ?
                """, (description_lt, description_en, description_lv, 
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S'), name))
                self._log("Description updated", name=name)
            else:
                # Insert
                cursor.execute("""
                    INSERT INTO descriptions 
                    (name, description_lt, description_en, description_lv)
                    VALUES (?, ?, ?, ?)
                """, (name, description_lt, description_en, description_lv))
                self._log("Description created", name=name)
            
            self.db.conn.commit()
            return True
            
        except Exception as e:
            self._log_error("Failed to save description", exception=e, name=name)
            return False
    
    def load_description(self, name: str) -> dict:
        """Load description from database"""
        self._log("Loading description", name=name)
        
        try:
            cursor = self.db.conn.cursor()
            result = cursor.execute("""
                SELECT name, description_lt, description_en, description_lv, 
                       created_at, updated_at
                FROM descriptions 
                WHERE name = ?
            """, (name,)).fetchone()
            
            if result:
                return {
                    'name': result['name'],
                    'description_lt': result['description_lt'] or '',
                    'description_en': result['description_en'] or '',
                    'description_lv': result['description_lv'] or '',
                    'created_at': result['created_at'],
                    'updated_at': result['updated_at']
                }
            
            return None
            
        except Exception as e:
            self._log_error("Failed to load description", exception=e, name=name)
            return None
    
    def list_descriptions(self) -> list:
        """Get list of all description names"""
        try:
            cursor = self.db.conn.cursor()
            results = cursor.execute("""
                SELECT name, updated_at 
                FROM descriptions 
                ORDER BY updated_at DESC
            """).fetchall()
            
            return [{'name': r['name'], 'updated_at': r['updated_at']} for r in results]
            
        except Exception as e:
            self._log_error("Failed to list descriptions", exception=e)
            return []
    
    def delete_description(self, name: str) -> bool:
        """Delete description from database"""
        self._log("Deleting description", name=name)
        
        try:
            cursor = self.db.conn.cursor()
            cursor.execute("DELETE FROM descriptions WHERE name = ?", (name,))
            self.db.conn.commit()
            self._log("Description deleted", name=name)
            return True
            
        except Exception as e:
            self._log_error("Failed to delete description", exception=e, name=name)
            return False
    
    def upload_to_prestashop(self, driver, product_code: str, name: str) -> bool:
        """
        Upload description to PrestaShop product
        Reuses logic from DescriptionAdderBasso.py
        """
        print(f"DEBUG DescriptionManager: Starting upload, product_code={product_code}, name={name}")
        self._log("Uploading description to PrestaShop", product_code=product_code, name=name)
        
        # Load description
        desc = self.load_description(name)
        if not desc:
            print(f"DEBUG DescriptionManager: Description '{name}' not found in database")
            self._log_error("Description not found", name=name)
            return False
        
        print(f"DEBUG DescriptionManager: Description loaded, lt={len(desc['description_lt'])} chars, en={len(desc['description_en'])} chars, lv={len(desc['description_lv'])} chars")
        
        try:
            # Wait for page to load
            wait = WebDriverWait(driver, 10)
            
            # Navigate to description tab (tab-step1)
            try:
                # Check if we're already on the right tab
                current_url = driver.current_url
                if '#tab-step1' not in current_url:
                    self._log("Navigating to description tab")
                    driver.get(current_url.split('#')[0] + '#tab-step1')
                    time.sleep(1)
            except:
                pass
            
            # Language configurations (code, HTML content)
            languages = [
                ('lt', desc['description_lt']),  # Lithuanian
                ('en', desc['description_en']),  # English
                ('lv', desc['description_lv'])   # Latvian
            ]
            
            for lang_code, html_content in languages:
                print(f"DEBUG DescriptionManager: Processing language {lang_code}")
                self._log(f"Uploading {lang_code} language", lang_code=lang_code)
                
                # Switch language
                print(f"DEBUG DescriptionManager: Switching to language {lang_code}")
                language_dropdown = wait.until(
                    EC.element_to_be_clickable((By.ID, "form_switch_language"))
                )
                Select(language_dropdown).select_by_value(lang_code)
                time.sleep(1)
                
                # Determine iframe ID based on language code
                # Map: lt=2, en=1, lv=3
                lang_id_map = {'lt': '2', 'en': '1', 'lv': '3'}
                lang_id = lang_id_map[lang_code]
                
                # Wait for iframe to be available
                iframe_id = f"form_step1_description_{lang_id}_ifr"
                print(f"DEBUG DescriptionManager: Waiting for iframe {iframe_id}")
                wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, iframe_id)))
                print(f"DEBUG DescriptionManager: Switched to iframe {iframe_id}")
                
                # Find editor body and paste HTML
                editor_body = wait.until(
                    EC.presence_of_element_located((By.ID, "tinymce"))
                )
                print(f"DEBUG DescriptionManager: Found editor body, inserting {len(html_content)} chars")
                
                # Clear existing content
                driver.execute_script("arguments[0].innerHTML = '';", editor_body)
                
                # Insert new HTML
                driver.execute_script("arguments[0].innerHTML = arguments[1];", 
                                    editor_body, html_content)
                
                print(f"DEBUG DescriptionManager: HTML inserted for {lang_code}")
                
                # Switch back to main content
                driver.switch_to.default_content()
                print(f"DEBUG DescriptionManager: Switched back to main content")
                
                time.sleep(0.5)
            
            self._log("Description uploaded successfully", product_code=product_code)
            return True
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self._log_error("Failed to upload description", exception=e, 
                          product_code=product_code, name=name)
            print(f"UPLOAD ERROR: {error_details}")  # Print to console for debugging
            
            # Make sure we're back in default content
            try:
                driver.switch_to.default_content()
            except:
                pass
            return False