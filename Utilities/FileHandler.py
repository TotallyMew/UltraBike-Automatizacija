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
            with open(file_path, "r", encoding="utf-8") as file:
                for line in file:
                    if line.strip() == "":
                        if table_data:
                            tables.append(table_data)
                            table_data = {}
                        continue
                    
                    try:
                        key, value = line.strip().split(": ", 1)
                        table_data[key] = value
                    except ValueError:
                        print(f"Warning: Line is not in 'key: value' format: {line.strip()}")
                
                if table_data:
                    tables.append(table_data)

        except FileNotFoundError:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as file:
                file.write("")
            return FileHandler.read_translated_file(file_path, "en")
        except Exception as e:
            print(f"An error occurred: {e}")

        return tables

    @staticmethod
    def sanitize_filename(name):
        return re.sub(r'[<>:"/\\|?*]', '', name)

    @staticmethod
    def generate_random_string(length=8):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
