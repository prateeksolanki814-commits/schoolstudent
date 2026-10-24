"""Small standard-library tests for password handling."""
import unittest

from core.security import hash_password, validate_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        password = "SecureSchool123"
        encoded = hash_password(password)
        self.assertNotEqual(password, encoded)
        self.assertTrue(verify_password(password, encoded))
        self.assertFalse(verify_password("WrongPassword123", encoded))

    def test_password_validation(self):
        self.assertIsNone(validate_password("SecureSchool123"))
        self.assertIsNotNone(validate_password("short1"))
        self.assertIsNotNone(validate_password("onlyletterslong"))
        self.assertIsNotNone(validate_password(" endswithspace1 "))


if __name__ == "__main__":
    unittest.main()
