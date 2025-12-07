import os
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from Config.Settings.SettingsManager import SettingsManager
from Utilities.ErrorManager import ErrorManager

class FolderCreator:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.settings_manager = SettingsManager()
        self.repository_path = self.settings_manager.get_repository_path()
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("FolderCreator", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("FolderCreator", message, exception=exception, **context)
    
    def navigate_to_products(self):
        """Navigate to products page in PrestaShop admin"""
        self._log("Navigating to products page")
        try:
            products_link = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "subtab-AdminProducts"))
            )
            products_link.click()
            self._log("Clicked products link")
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.table"))
            )
            self._log("Products page loaded")
            return True
        except Exception as e:
            self._log_error("Failed to navigate to products", exception=e)
            ErrorManager.show_error("BROWSER_ELEMENT_NOT_FOUND")
            return False
    
    def scrape_first_page(self):
        """Scrape products from first page only"""
        self._log("Starting product scrape from first page")
        products = []
        
        try:
            table = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.table"))
            )
            
            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr[data-product-id]")
            self._log("Found products on page", count=len(rows))
            
            for row in rows:
                try:
                    name = row.find_element(By.CSS_SELECTOR, "td:nth-child(4) a").text
                    reference = row.find_element(By.CSS_SELECTOR, "td:nth-child(5)").text
                    
                    products.append({
                        'name': name,
                        'reference': reference
                    })
                        
                except Exception as e:
                    self._log_error("Error processing product row", exception=e)
                    continue
            
            self._log("Product scraping completed", total=len(products))
        
        except Exception as e:
            self._log_error("Error scraping products", exception=e)
            ErrorManager.show_error("SCRAPER_NO_DATA")
            return []
        
        return products
    
    def extract_model(self, full_name):
        """Extract model name (everything before first '/')"""
        model_match = re.match(r"^(.*?)\s*\/", full_name)
        if model_match:
            return model_match.group(1).strip()
        return full_name.strip()
    
    def sanitize_folder_name(self, name):
        """Remove invalid characters for folder names"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '-')
        return name.strip('. ')
    
    def create_folder_structure(self, products):
        """Create parent (model) and child (full name) folder structure"""
        if not products:
            self._log("No products to process")
            ErrorManager.show_warning("Nerasta produktų apdorojimui")
            return
        
        self._log("Creating folder structure", product_count=len(products))
        
        # Group products by model
        model_groups = {}
        for product in products:
            full_name = product['name']
            model = self.extract_model(full_name)
            
            if model not in model_groups:
                model_groups[model] = []
            model_groups[model].append(full_name)
        
        # Create folders
        created_count = 0
        for model, full_names in model_groups.items():
            model_folder = self.sanitize_folder_name(model)
            model_path = os.path.join(self.repository_path, model_folder)
            
            try:
                os.makedirs(model_path, exist_ok=True)
                self._log("Created model folder", model=model_folder)
            except Exception as e:
                self._log_error("Failed to create model folder", exception=e, model=model_folder)
                ErrorManager.show_error("FOLDER_CREATE_ERROR", path=model_path)
                continue
            
            for full_name in full_names:
                child_folder = self.sanitize_folder_name(full_name)
                child_path = os.path.join(model_path, child_folder)
                
                try:
                    os.makedirs(child_path, exist_ok=True)
                    created_count += 1
                except Exception as e:
                    self._log_error("Failed to create product folder", exception=e, folder=child_folder)
                    continue
        
        self._log("Folder creation complete", models=len(model_groups), products=created_count)
        ErrorManager.show_success(f"Sukurta {len(model_groups)} modelių aplankų ir {created_count} produktų aplankų")
    
    def run(self):
        """Main execution flow"""
        self._log("Starting folder creator", repository=self.repository_path)
        
        if not self.navigate_to_products():
            return
        
        products = self.scrape_first_page()
        
        if not products:
            return
        
        self.create_folder_structure(products)