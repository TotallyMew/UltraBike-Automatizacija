import os
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from Config.Settings.SettingsManager import SettingsManager

class FolderCreator:
    def __init__(self, driver):
        self.driver = driver
        self.settings_manager = SettingsManager()
        self.repository_path = self.settings_manager.get_repository_path()
    
    def navigate_to_products(self):
        """Navigate to products page in PrestaShop admin"""
        try:
            products_link = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "subtab-AdminProducts"))
            )
            products_link.click()
            print("Navigated to products page")
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.table"))
            )
        except Exception as e:
            print(f"Failed to navigate to products: {str(e)}")
            return False
        return True
    
    def scrape_first_page(self):
        """Scrape products from first page only"""
        products = []
        
        try:
            table = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.table"))
            )
            
            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr[data-product-id]")
            print(f"Found {len(rows)} products on first page")
            
            for row in rows:
                try:
                    name = row.find_element(By.CSS_SELECTOR, "td:nth-child(4) a").text
                    reference = row.find_element(By.CSS_SELECTOR, "td:nth-child(5)").text
                    
                    products.append({
                        'name': name,
                        'reference': reference
                    })
                        
                except Exception as e:
                    print(f"Error processing product: {str(e)}")
                    continue
        
        except Exception as e:
            print(f"Error scraping products: {str(e)}")
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
        # Replace invalid Windows folder characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '-')
        # Remove trailing dots and spaces
        return name.strip('. ')
    
    def create_folder_structure(self, products):
        """Create parent (model) and child (full name) folder structure"""
        if not products:
            print("No products to process")
            return
        
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
            # Create parent folder (model)
            model_folder = self.sanitize_folder_name(model)
            model_path = os.path.join(self.repository_path, model_folder)
            
            try:
                os.makedirs(model_path, exist_ok=True)
                print(f"Created model folder: {model_folder}")
            except Exception as e:
                print(f"Error creating model folder '{model_folder}': {str(e)}")
                continue
            
            # Create child folders (full names)
            for full_name in full_names:
                child_folder = self.sanitize_folder_name(full_name)
                child_path = os.path.join(model_path, child_folder)
                
                try:
                    os.makedirs(child_path, exist_ok=True)
                    created_count += 1
                except Exception as e:
                    print(f"Error creating child folder '{child_folder}': {str(e)}")
                    continue
        
        print(f"\nFolder creation complete!")
        print(f"Created {len(model_groups)} model folders")
        print(f"Created {created_count} product folders")
        print(f"Repository path: {self.repository_path}")
    
    def run(self):
        """Main execution flow"""
        print("\n=== Folder Creator Mode ===")
        print(f"Repository path: {self.repository_path}\n")
        
        if not self.navigate_to_products():
            print("Failed to navigate to products page")
            return
        
        products = self.scrape_first_page()
        
        if not products:
            print("No products found")
            return
        
        print(f"\nProcessing {len(products)} products...")
        self.create_folder_structure(products)
