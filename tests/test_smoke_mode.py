import unittest

from main import smoke_test


class SmokeModeTests(unittest.TestCase):
    def test_smoke_mode_is_offline_and_does_not_require_login(self):
        self.assertEqual(smoke_test(), 0)


if __name__ == "__main__":
    unittest.main()
