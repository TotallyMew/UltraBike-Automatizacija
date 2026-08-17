import unittest

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager


class _UnserializableValue:
    def __str__(self):
        raise ValueError("cannot serialize")


class SettingsManagerTest(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.settings = SettingsManager(self.db)

    def tearDown(self):
        self.db.close()

    def test_set_many_rolls_back_the_whole_group_on_failure(self):
        original = self.settings.get("theme")

        with self.assertRaises(ValueError):
            self.settings.set_many({
                "theme": "dark" if original != "dark" else "light",
                "invalid_test_value": _UnserializableValue(),
            })

        self.assertEqual(self.settings.get("theme"), original)
        self.assertIsNone(self.settings.get("invalid_test_value"))


if __name__ == "__main__":
    unittest.main()
