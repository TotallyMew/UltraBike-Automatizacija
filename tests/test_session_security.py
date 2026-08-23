import hashlib
import json
import os
import unittest
from unittest.mock import patch

from Database.DatabaseManager import DatabaseManager
from Database.SessionManager import SessionManager


class SessionSecurityTest(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.sessions = SessionManager(self.db)

    def tearDown(self):
        self.db.close()

    def _stored_verifier(self) -> str:
        row = self.db.conn.execute(
            "SELECT value FROM settings WHERE key = 'master_password_hash'"
        ).fetchone()
        self.assertIsNotNone(row)
        return str(row[0])

    def test_new_master_password_uses_salted_scrypt_verifier(self):
        password = "a long unique passphrase"
        self.sessions.set_master_password(password)

        stored = self._stored_verifier()
        verifier = json.loads(stored)
        self.assertEqual(verifier["version"], 2)
        self.assertEqual(verifier["kdf"], "scrypt")
        self.assertNotEqual(stored, hashlib.sha256(password.encode()).hexdigest())
        self.assertNotIn(password, stored)
        self.assertTrue(self.sessions.verify_master_password(password))
        self.assertFalse(self.sessions.verify_master_password(password + "!"))

    def test_legacy_sha256_verifier_migrates_after_successful_unlock(self):
        password = "legacy master password"
        legacy = hashlib.sha256(password.encode()).hexdigest()
        self.db.conn.execute(
            "INSERT INTO settings (key, value) VALUES ('master_password_hash', ?)",
            (legacy,),
        )
        self.db.conn.commit()

        self.assertTrue(self.sessions.verify_master_password(password))
        migrated = self._stored_verifier()
        self.assertNotEqual(migrated, legacy)
        self.assertEqual(json.loads(migrated)["kdf"], "scrypt")
        self.assertTrue(self.sessions.verify_master_password(password))

    def test_master_password_change_reencrypts_every_credential(self):
        old_password = "old-master-123"
        new_password = "new-master-456"
        self.sessions.store_credentials("admin@example.test", "admin-secret", old_password)
        self.sessions.store_external_credentials("basso", "basso-user", "basso-secret", old_password)
        self.sessions.store_external_credentials("lee_cougan", "lee-user", "lee-secret", old_password)

        self.sessions.change_master_password(old_password, new_password)

        self.assertFalse(self.sessions.verify_master_password(old_password))
        self.assertEqual(
            self.sessions.get_credentials(new_password),
            ("admin@example.test", "admin-secret"),
        )
        self.assertEqual(
            self.sessions.get_external_credentials("basso", new_password),
            ("basso-user", "basso-secret"),
        )
        self.assertEqual(
            self.sessions.get_external_credentials("lee_cougan", new_password),
            ("lee-user", "lee-secret"),
        )

    def test_password_change_rolls_back_on_reencryption_failure(self):
        old_password = "old-master-123"
        self.sessions.store_credentials("admin@example.test", "admin-secret", old_password)
        self.sessions.store_external_credentials("basso", "user", "secret", old_password)
        original = self.sessions._encrypt_stored_secret
        calls = 0

        def fail_second(secret, password):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated failure")
            return original(secret, password)

        with patch.object(self.sessions, "_encrypt_stored_secret", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                self.sessions.change_master_password(old_password, "new-master-456")

        self.assertTrue(self.sessions.verify_master_password(old_password))
        self.assertEqual(
            self.sessions.get_credentials(old_password),
            ("admin@example.test", "admin-secret"),
        )
        self.assertEqual(
            self.sessions.get_external_credentials("basso", old_password),
            ("user", "secret"),
        )

    def test_forgotten_password_reset_preserves_non_secret_data(self):
        old_password = "old-master-123"
        new_password = "new-master-456"
        self.sessions.store_credentials("admin@example.test", "admin-secret", old_password)
        self.sessions.store_external_credentials("basso", "user", "secret", old_password)
        self.db.conn.execute(
            "INSERT INTO descriptions(name, description_lt) VALUES ('Keep me', 'Tekstas')"
        )
        self.db.conn.commit()

        self.sessions.reset_master_password(new_password)

        self.assertTrue(self.sessions.verify_master_password(new_password))
        self.assertEqual(self.sessions.get_credentials(new_password), (None, None))
        self.assertFalse(self.sessions.has_external_credentials("basso"))
        self.assertEqual(
            self.db.conn.execute("SELECT description_lt FROM descriptions").fetchone()[0],
            "Tekstas",
        )
    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_session_payload_uses_current_user_dpapi(self):
        encrypted = self.sessions._encrypt("session secret")
        self.assertTrue(encrypted.startswith("dpapi:"))
        self.assertNotIn("session secret", encrypted)
        self.assertEqual(self.sessions._decrypt(encrypted), "session secret")


if __name__ == "__main__":
    unittest.main()
