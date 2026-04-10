"""Tests unitarios del servicio de cifrado.

Aislados del backend real: usan env vars locales seteadas en setUp.
"""

import os
import unittest
from cryptography.fernet import Fernet


def _fresh_crypto_module():
    """Importa crypto fresh con @lru_cache limpio."""
    import importlib
    import sys
    # Descargar si ya está en sys.modules
    for mod in list(sys.modules.keys()):
        if mod.endswith("app.services.crypto") or mod == "app.services.crypto":
            del sys.modules[mod]
    import app.services.crypto as crypto_module
    importlib.reload(crypto_module)
    return crypto_module


class CryptoRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._key = Fernet.generate_key().decode()
        os.environ["APP_ENCRYPTION_KEY"] = cls._key
        os.environ.pop("APP_ENCRYPTION_KEY_OLD", None)
        cls.crypto = _fresh_crypto_module()

    def test_roundtrip_basic(self):
        ct = self.crypto.encrypt_secret("hola mundo")
        self.assertEqual(self.crypto.decrypt_secret(ct), "hola mundo")

    def test_ciphertext_is_different_from_plaintext(self):
        ct = self.crypto.encrypt_secret("EAAxFakeToken123")
        self.assertNotIn("EAAxFakeToken123", ct)

    def test_encrypt_twice_gives_different_ciphertexts(self):
        ct1 = self.crypto.encrypt_secret("same")
        ct2 = self.crypto.encrypt_secret("same")
        # Fernet embeds a timestamp + IV → ciphertexts should differ
        self.assertNotEqual(ct1, ct2)
        self.assertEqual(self.crypto.decrypt_secret(ct1), "same")
        self.assertEqual(self.crypto.decrypt_secret(ct2), "same")

    def test_decrypt_garbage_raises_crypto_error(self):
        with self.assertRaises(self.crypto.CryptoError):
            self.crypto.decrypt_secret("not-a-valid-ciphertext")

    def test_encrypt_empty_raises_crypto_error(self):
        with self.assertRaises(self.crypto.CryptoError):
            self.crypto.encrypt_secret("")

    def test_decrypt_empty_raises_crypto_error(self):
        with self.assertRaises(self.crypto.CryptoError):
            self.crypto.decrypt_secret("")


class CryptoKeyRotationTests(unittest.TestCase):
    def test_multifernet_decrypts_with_old_key(self):
        # 1. Generar clave vieja, cifrar con ella
        old_key = Fernet.generate_key().decode()
        os.environ["APP_ENCRYPTION_KEY"] = old_key
        os.environ.pop("APP_ENCRYPTION_KEY_OLD", None)
        crypto_old = _fresh_crypto_module()
        ct = crypto_old.encrypt_secret("mensaje original")

        # 2. Rotar: nueva clave primaria, vieja como fallback
        new_key = Fernet.generate_key().decode()
        os.environ["APP_ENCRYPTION_KEY"] = new_key
        os.environ["APP_ENCRYPTION_KEY_OLD"] = old_key
        crypto_new = _fresh_crypto_module()

        # 3. Debe poder descifrar el ciphertext viejo
        self.assertEqual(crypto_new.decrypt_secret(ct), "mensaje original")

        # 4. Y cifrar con la nueva
        ct_new = crypto_new.encrypt_secret("nuevo")
        self.assertEqual(crypto_new.decrypt_secret(ct_new), "nuevo")


class CryptoMissingKeyTests(unittest.TestCase):
    def setUp(self):
        # Guardar estado previo para poder restaurarlo en tearDown
        self._saved_primary = os.environ.get("APP_ENCRYPTION_KEY")
        self._saved_old = os.environ.get("APP_ENCRYPTION_KEY_OLD")

    def tearDown(self):
        # Restaurar SIEMPRE las env vars — otros tests dependen de ellas
        if self._saved_primary is not None:
            os.environ["APP_ENCRYPTION_KEY"] = self._saved_primary
        else:
            os.environ.pop("APP_ENCRYPTION_KEY", None)
        if self._saved_old is not None:
            os.environ["APP_ENCRYPTION_KEY_OLD"] = self._saved_old
        else:
            os.environ.pop("APP_ENCRYPTION_KEY_OLD", None)
        # Reload del módulo para que quede en estado cargado
        if self._saved_primary:
            _fresh_crypto_module()

    def test_missing_key_raises_at_import(self):
        os.environ.pop("APP_ENCRYPTION_KEY", None)
        os.environ.pop("APP_ENCRYPTION_KEY_OLD", None)
        with self.assertRaises(Exception):
            _fresh_crypto_module()


if __name__ == "__main__":
    unittest.main()
