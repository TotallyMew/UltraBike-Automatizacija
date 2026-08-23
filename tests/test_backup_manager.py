import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Database.DatabaseManager import DatabaseManager
from Database.SessionManager import SessionManager
from Utilities.BackupManager import BackupManager


class BackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "app.db"
        self.database = DatabaseManager(self.db_path)
        self.sessions = SessionManager(self.database)
        self.sessions.store_credentials(
            "admin@example.test", "admin-secret", "portable-pass-123"
        )
        self.sessions.store_external_credentials(
            "basso", "portal-user", "portal-secret", "portable-pass-123"
        )
        self.database.conn.execute(
            "INSERT INTO descriptions(name, description_lt, description_en, description_lv) "
            "VALUES ('Template', 'LT', 'EN', 'LV')"
        )
        self.database.conn.commit()
        self.manager = BackupManager(self.database)

    def tearDown(self):
        if self.database.conn is not None:
            self.database.close()
        self.temp.cleanup()

    def test_round_trip_wrong_password_and_tampering(self):
        backup_path = self.root / "portable.ubbackup"
        created = self.manager.create(backup_path, "portable-pass-123")
        inspected = self.manager.inspect(backup_path, "portable-pass-123")
        self.assertEqual(inspected.schema_version, created.schema_version)
        self.assertGreater(inspected.database_size, 0)
        with self.assertRaisesRegex(ValueError, "incorrect|modified"):
            self.manager.inspect(backup_path, "wrong-password")

        tampered = self.root / "tampered.ubbackup"
        data = bytearray(backup_path.read_bytes())
        data[-1] ^= 1
        tampered.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "incorrect|modified"):
            self.manager.inspect(tampered, "portable-pass-123")

        self.database.conn.execute("DELETE FROM descriptions")
        self.database.conn.commit()
        self.manager.restore(backup_path, "portable-pass-123")
        restored = DatabaseManager(self.db_path)
        try:
            row = restored.conn.execute(
                "SELECT description_lt, description_en, description_lv FROM descriptions"
            ).fetchone()
            self.assertEqual(tuple(row), ("LT", "EN", "LV"))
            sessions = SessionManager(restored)
            self.assertEqual(
                sessions.get_external_credentials("basso", "portable-pass-123"),
                ("portal-user", "portal-secret"),
            )
        finally:
            restored.close()

    def test_failed_replace_leaves_live_database_and_reconnects(self):
        backup_path = self.root / "portable.ubbackup"
        self.manager.create(backup_path, "portable-pass-123")
        with patch("Utilities.BackupManager.os.replace", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(OSError, "blocked"):
                self.manager.restore(backup_path, "portable-pass-123")
        self.assertIsNotNone(self.database.conn)
        self.assertEqual(
            self.database.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok"
        )


if __name__ == "__main__":
    unittest.main()
