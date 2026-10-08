import re
import random
import string


class FileHandler:
    @staticmethod
    def read_translated_file(file_path):
        tables = []
        table_data = {}

        seen = {}
        with open(file_path, "r", encoding="utf-8") as file:
            for number, line in enumerate(file, 1):
                if not line.strip():
                    if table_data:
                        tables.append(table_data)
                        table_data = {}
                    continue
                key, separator, value = line.strip().partition(":")
                key, value = key.strip(), value.strip()
                if not separator or not key or not value:
                    raise ValueError(f"Invalid specification at {file_path}:{number}")
                canonical = key.casefold()
                if canonical in seen and seen[canonical] != value:
                    raise ValueError(f"Conflicting values for specification {key!r}; select the correct product variant")
                seen[canonical] = value
                table_data[key] = value
        if table_data:
            tables.append(table_data)
        if not tables:
            raise ValueError(f"No specifications were collected in {file_path}")
        return tables

    @staticmethod
    def sanitize_filename(name):
        return re.sub(r'[<>:"/\\|?*]', '', name)

    @staticmethod
    def generate_random_string(length=8):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
