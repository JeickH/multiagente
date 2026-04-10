"""Genera una clave Fernet nueva para APP_ENCRYPTION_KEY.

Uso:
    python backend/scripts/gen_encryption_key.py

IMPORTANTE:
- NO pegues esta clave en más de un ambiente (dev, staging, prod deben tener
  claves DISTINTAS).
- Guárdala en un password manager.
- Perder la clave significa perder acceso permanente a los datos cifrados.
"""

import sys
from cryptography.fernet import Fernet


def main() -> int:
    key = Fernet.generate_key().decode("utf-8")
    print()
    print("Nueva APP_ENCRYPTION_KEY generada:")
    print()
    print(f"APP_ENCRYPTION_KEY={key}")
    print()
    print("⚠️  IMPORTANTE:")
    print("   - NO pegues esta clave en más de un ambiente.")
    print("   - Guárdala en un password manager (1Password, Bitwarden, etc.).")
    print("   - Perder la clave = perder acceso permanente a los datos cifrados.")
    print("   - NUNCA commitees esta clave al repositorio.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
