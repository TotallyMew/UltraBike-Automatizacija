from Database.DatabaseManager import DatabaseManager
from Database.TranslationImporter import TranslationImporter

# Initialize database
db = DatabaseManager()

# Import translations
importer = TranslationImporter(db)
importer.import_all()

# Verify import
cursor = db.conn.cursor()
count = cursor.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
print(f"\nTotal translations in database: {count}")

db.close()