import hashlib
import json
import os
import unittest

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

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_session_payload_uses_current_user_dpapi(self):
        encrypted = self.sessions._encrypt("session secret")
        self.assertTrue(encrypted.startswith("dpapi:"))
        self.assertNotIn("session secret", encrypted)
        self.assertEqual(self.sessions._decrypt(encrypted), "session secret")


if __name__ == "__main__":
    unittest.main()
