import tempfile
import unittest
from pathlib import Path

from Database.DatabaseManager import DatabaseManager
from Database.SessionManager import SessionManager


class LegacyMigrationTests(unittest.TestCase):
    def test_cleanup_removes_only_retired_translation_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.db"
            database = DatabaseManager(path)
            sessions = SessionManager(database)
            sessions.store_credentials("admin@example.test", "admin-secret", "master-pass-123")
            sessions.store_external_credentials("basso", "basso-user", "basso-secret", "master-pass-123")
            sessions.store_external_credentials("lee_cougan", "lee-user", "lee-secret", "master-pass-123")
            database.conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                ("deep" + "l_api_key", "obsolete"),
            )
            database.conn.execute(
                "INSERT OR REPLACE INTO external_credentials "
                "(service_key, username, encrypted_password, salt) VALUES (?, ?, ?, ?)",
                ("deep" + "l", "obsolete", "obsolete", "obsolete"),
            )
            database.conn.execute("PRAGMA user_version = 0")
            database.conn.commit()
            database.close()

            migrated = DatabaseManager(path)
            self.assertEqual(migrated.conn.execute("PRAGMA user_version").fetchone()[0], 5)
            work_session_columns = {
                row["name"]
                for row in migrated.conn.execute("PRAGMA table_info(work_sessions)")
            }
            self.assertTrue(
                {"quest_kind", "quest_target_value", "quest_completed_at"}
                <= work_session_columns
            )
            self.assertIsNone(
                migrated.conn.execute(
                    "SELECT 1 FROM settings WHERE key=?", ("deep" + "l_api_key",)
                ).fetchone()
            )
            self.assertIsNone(
                migrated.conn.execute(
                    "SELECT 1 FROM external_credentials WHERE service_key=?", ("deep" + "l",)
                ).fetchone()
            )
            migrated_sessions = SessionManager(migrated)
            self.assertEqual(
                migrated_sessions.get_external_credentials("basso", "master-pass-123"),
                ("basso-user", "basso-secret"),
            )
            self.assertEqual(
                migrated_sessions.get_external_credentials("lee_cougan", "master-pass-123"),
                ("lee-user", "lee-secret"),
            )
            migrated.close()


if __name__ == "__main__":
    unittest.main()
