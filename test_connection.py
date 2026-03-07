import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("WATI_API_ENDPOINT_V1")
TOKEN = os.getenv("WATI_BEARER_TOKEN")

HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

ENDPOINTS = {
    "Contactos (1)":       f"{BASE}/api/v1/getContacts?pageSize=1",
    "Templates":           f"{BASE}/api/v1/getMessageTemplates",
}


def test():
    print(f"Base URL: {BASE}\n")

    for name, url in ENDPOINTS.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            status = r.status_code
            ok = "OK" if status == 200 else "FALLO"
            detail = ""
            if status == 200:
                data = r.json()
                if "contact_list" in data:
                    total = data.get("link", {}).get("total", "?")
                    detail = f" -> {total} contactos totales"
                elif "messageTemplates" in data:
                    detail = f" -> {len(data['messageTemplates'])} templates"
            else:
                detail = f" -> {r.text[:80]}"
            print(f"  [{ok}] {status} | {name}{detail}")
        except Exception as e:
            print(f"  [ERROR] {name} -> {e}")

    print("\nConexion verificada.")


if __name__ == "__main__":
    test()
