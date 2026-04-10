"""Test de integración del flujo MetaAccount cifrado.

Usa SQLite in-memory y mocks para get_phone_number_info (para no llamar a Meta real).
"""

import os
import unittest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# IMPORTANTE: setear APP_ENCRYPTION_KEY antes de importar los módulos que usan crypto.
# Usamos hard-set (no setdefault) porque otros tests (test_crypto.CryptoMissingKeyTests)
# pueden haberla borrado del entorno.
os.environ["APP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ.pop("APP_ENCRYPTION_KEY_OLD", None)
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Forzar reload del módulo crypto por si otro test lo descargó/rompió
import importlib  # noqa: E402
import sys  # noqa: E402
for _mod in [m for m in list(sys.modules.keys()) if m.endswith("app.services.crypto")]:
    del sys.modules[_mod]

from app import models  # noqa: E402
from app import crud  # noqa: E402
from app.database import Base  # noqa: E402
# Reimport crypto para que crud lo use con la nueva env var
from app.services import crypto as _crypto  # noqa: E402
importlib.reload(_crypto)


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session(), engine


class MetaAccountFlowTests(unittest.TestCase):
    def setUp(self):
        self.db, self.engine = _make_session()
        # Crear un usuario + team + owner membership
        from app.schemas import UserCreate
        user = crud.create_user(
            self.db,
            UserCreate(
                nombre="Test User",
                tipo_documento="CC",
                documento="123456",
                correo="owner@test.com",
                password="password123",
            ),
        )
        self.user = user
        self.team = crud.create_team(self.db, nombre="Test Team", owner=user)

    def tearDown(self):
        self.db.close()

    def test_register_stores_ciphertext_not_plaintext(self):
        plaintext = "EAAFakeTokenForTestingOnly123456"
        account = crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1057839004082880",
            waba_id="1272393681746114",
            access_token_plaintext=plaintext,
            display_phone="+57 300 318 7871",
            verified_name="Tienda Test",
        )
        # El campo en DB debe ser ciphertext, no el plaintext
        self.assertNotEqual(account.encrypted_access_token, plaintext)
        self.assertNotIn(plaintext, account.encrypted_access_token)
        # Chequeo laxo: ciphertext Fernet suele empezar con "gAAAAA" pero
        # fallamos de forma más tolerante si no es así.
        self.assertGreater(len(account.encrypted_access_token), 40)

    def test_register_roundtrip_decrypt(self):
        plaintext = "EAAFakeTokenABC123"
        account = crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1001",
            waba_id="2001",
            access_token_plaintext=plaintext,
            display_phone="+1 555 0100",
        )
        decrypted = crud.get_decrypted_access_token(account)
        self.assertEqual(decrypted, plaintext)

    def test_register_sets_status_active_and_timestamps(self):
        account = crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1002",
            waba_id="2002",
            access_token_plaintext="EAAxyz",
            display_phone="+1 555 0200",
        )
        self.assertEqual(account.status, "active")
        self.assertIsNotNone(account.last_validated_at)
        self.assertEqual(account.registered_by_user_id, self.user.id)
        self.assertIsNone(account.validation_error)

    def test_is_meta_account_usable(self):
        self.assertFalse(crud.is_meta_account_usable(None))

        account = crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1003",
            waba_id="2003",
            access_token_plaintext="EAAtoken",
            display_phone="+1 555 0300",
        )
        self.assertTrue(crud.is_meta_account_usable(account))

        account.status = "pending"
        self.assertFalse(crud.is_meta_account_usable(account))

        account.status = "active"
        account.is_active = False
        self.assertFalse(crud.is_meta_account_usable(account))

    def test_repr_redacts_token(self):
        account = crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1004",
            waba_id="2004",
            access_token_plaintext="EAAsecretTokenABCDEF",
            display_phone="+1 555 0400",
        )
        r = repr(account)
        self.assertIn("REDACTED", r)
        self.assertNotIn("EAAsecretTokenABCDEF", r)
        self.assertNotIn(account.encrypted_access_token, r)

    def test_disconnect_removes_row(self):
        crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1005",
            waba_id="2005",
            access_token_plaintext="EAAdel",
            display_phone="+1 555 0500",
        )
        removed = crud.disconnect_meta_account(self.db, self.team)
        self.assertTrue(removed)
        self.assertIsNone(crud.get_meta_account_for_team(self.db, self.team.id))

        # Second call returns False
        removed_again = crud.disconnect_meta_account(self.db, self.team)
        self.assertFalse(removed_again)

    def test_reregister_updates_existing(self):
        crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1006",
            waba_id="2006",
            access_token_plaintext="EAAfirst",
            display_phone="+1 555 0600",
        )
        # Re-registrar con credenciales nuevas
        account2 = crud.register_meta_account(
            db=self.db,
            team=self.team,
            registered_by=self.user,
            phone_number_id="1006-new",
            waba_id="2006-new",
            access_token_plaintext="EAAsecond",
            display_phone="+1 555 0601",
        )
        self.assertEqual(
            crud.get_decrypted_access_token(account2), "EAAsecond"
        )
        self.assertEqual(account2.phone_number_id, "1006-new")


class SchemaLockdownTests(unittest.TestCase):
    def test_meta_account_out_forbids_encrypted_token(self):
        from app import schemas
        fields = (
            schemas.MetaAccountOut.model_fields
            if hasattr(schemas.MetaAccountOut, "model_fields")
            else schemas.MetaAccountOut.__fields__
        )
        self.assertNotIn("encrypted_access_token", fields)
        self.assertNotIn("access_token", fields)

    def test_meta_account_register_in_has_expected_fields(self):
        from app import schemas
        fields = (
            schemas.MetaAccountRegisterIn.model_fields
            if hasattr(schemas.MetaAccountRegisterIn, "model_fields")
            else schemas.MetaAccountRegisterIn.__fields__
        )
        self.assertIn("phone_number_id", fields)
        self.assertIn("waba_id", fields)
        self.assertIn("access_token", fields)


if __name__ == "__main__":
    unittest.main()
