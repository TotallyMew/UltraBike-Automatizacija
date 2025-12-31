import re
import os
import random
import string


class FileHandler:
    @staticmethod
    def read_translated_file(file_path):
        tables = []
        table_data = {}

        try:
            with open(file_path, "r", encoding="utf-8") as file:  # FIXED: Added encoding
                for line in file:
                    # Safe check: line is always str from file iteration, never None
                    if not line.strip():
                        if table_data:
                            tables.append(table_data)
                            table_data = {}
                        continue
                    
                    try:
                        key, value = line.strip().split(": ", 1)
                        table_data[key] = value
                    except ValueError:
                        from Utilities.ErrorManager import ErrorManager
                        ErrorManager.show_error("FILE_FORMAT_ERROR", line=line.strip())
                
                if table_data:
                    tables.append(table_data)

        except FileNotFoundError:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as file:  # FIXED: Added encoding
                file.write("")
            return FileHandler.read_translated_file(file_path)
        except Exception as e:
            from Utilities.ErrorManager import ErrorManager
            ErrorManager.show_error("UNEXPECTED_ERROR", error=str(e))

        return tables

    @staticmethod
    def sanitize_filename(name):
        return re.sub(r'[<>:"/\\|?*]', '', name)

    @staticmethod
    def generate_random_string(length=8):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))