#UNTESTED

import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Set, Tuple, Optional
from Utilities.TranslationHandler import TranslationHandler

def extract_size_specific_data(row_data: Dict[str, List[Tuple[str, str]]]) -> Dict[str, Dict[str, str]]:

    size_specific_data = {}
    
    # Find all available sizes from the data
    all_sizes = set()
    for variants in row_data.values():
        for size, _ in variants:
            if size:  # Only add non-empty size strings
                all_sizes.update(size.split(', '))
    
    # Initialize dictionaries for each size
    for size in all_sizes:
        size_specific_data[size] = {}
    
    # Fill in the data for each size
    for key, variants in row_data.items():
        # If there's only one variant with no size specified, apply to all sizes
        if len(variants) == 1 and not variants[0][0]:
            for size in all_sizes:
                size_specific_data[size][key] = variants[0][1]
        else:
            # For size-specific variants
            for size_str, value in variants:
                if size_str:
                    for size in size_str.split(', '):
                        size_specific_data[size][key] = value
    
    return size_specific_data

def scrapeAndTranslateToFileTREK(url: str, outputFile: str, preferred_size: Optional[str] = None):
    translation_handler = TranslationHandler()
    keyTranslations = translation_handler.load_translations("Assets/Translations\\vertimasDetalesEN-LT.txt")
    valueTranslations = translation_handler.load_value_translations("Assets/Translations\\vertimasSavybesEN-LT.txt")
    
    try:
        # Get HTML content from URL
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find all specification sections
        spec_sections = soup.find_all("div", class_="pdl-collapse-item is-active")
        if not spec_sections:
            raise ValueError("TREK bicycle page structure has changed, please update the script.")
        
        # Dictionary to store all data with size variants
        all_data_with_variants = {}  # Key -> List of (size, value) tuples
        
        # Process each specification section
        for section in spec_sections:
            # Get section header (e.g., "Frameset", "Wheels", etc.)
            header = section.find("div", class_="flex items-center grow")
            if not header:
                continue
                
            section_name = header.get_text(strip=True)
            
            # Find specification table
            spec_table = section.find("table", class_="sprocket__table spec")
            if not spec_table:
                continue
                
            # Process rows in the table
            rows = spec_table.find_all("tr")
            for row in rows:
                # Find header cell (component name)
                th = row.find("th")
                if not th:
                    continue
                    
                component_name = th.get_text(strip=True).strip("*")
                
                # Find data cell
                td = row.find("td")
                if not td:
                    continue
                
                # Check if this row has size-specific data
                size_spans = td.find_all("span")
                size_info = ""
                
                if size_spans and "Size:" in size_spans[0].get_text():
                    # Extract size information
                    size_info = size_spans[0].get_text().replace("Size:", "").strip()
                    
                    # Remove the size span from consideration
                    for span in size_spans:
                        span.extract()
                
                # Get component value (strip all HTML tags if needed)
                component_value = td.get_text(strip=True)
                
                # Add section name as prefix to component name for clarity
                full_component_name = f"{section_name} - {component_name}"
                
                # Translate component name
                translated_component = keyTranslations.get(full_component_name, 
                                      keyTranslations.get(component_name, component_name))
                
                # Translate component value 
                translated_value = translation_handler.translate_first_word(component_value, valueTranslations)
                
                # Add to data dictionary with size variants
                if translated_component not in all_data_with_variants:
                    all_data_with_variants[translated_component] = []
                
                all_data_with_variants[translated_component].append((size_info, translated_value))
        
        # Extract weight information
        weight_section = soup.find(lambda tag: tag.name == "th" and "Weight" in tag.text)
        if weight_section and weight_section.find_next("td"):
            weight_value = weight_section.find_next("td").get_text(strip=True)
            all_data_with_variants["Svoris"] = [("", weight_value)]
            
        # Extract weight limit information
        weight_limit_section = soup.find(lambda tag: tag.name == "th" and "Weight limit" in tag.text)
        if weight_limit_section and weight_limit_section.find_next("td"):
            weight_limit_value = weight_limit_section.find_next("td").get_text(strip=True)
            all_data_with_variants["Svorio limitas"] = [("", weight_limit_value)]
        
        # Organize data by size
        size_specific_data = extract_size_specific_data(all_data_with_variants)
        
        # Determine which size data to use
        available_sizes = list(size_specific_data.keys())
        selected_size = preferred_size if preferred_size in available_sizes else available_sizes[0] if available_sizes else None
        
        # Write to file
        with open(outputFile, "w", encoding="utf-8") as f:
            # If a specific size was selected, write only that size's data
            if selected_size:
                f.write(f"Dydis: {selected_size}\n\n")
                for key, value in size_specific_data[selected_size].items():
                    f.write(f"{key}: {value}\n")
            else:
                # Otherwise write all sizes
                for size, data in size_specific_data.items():
                    f.write(f"Dydis: {size}\n")
                    for key, value in data.items():
                        f.write(f"{key}: {value}\n")
                    f.write("\n")
        
        return f"Successfully scraped data. Available sizes: {', '.join(available_sizes)}"
    
    except Exception as e:
        return f"Error processing TREK data: {str(e)}"