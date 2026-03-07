"""
WATI Chatbot Structure -> PlantUML Diagram

Dos modos de uso:
  1) VIA API (requiere plan Pro):
     python fetch_chatbots.py

  2) VIA JSON EXPORTADO (desde la UI de WATI):
     python fetch_chatbots.py --file chatbot_export.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("WATI_API_ENDPOINT_V1")
TOKEN = os.getenv("WATI_BEARER_TOKEN")
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

OUTPUT_DIR = Path(__file__).parent / "output"


# ── API helpers ──────────────────────────────────────────────────────────

def api_get(path):
    url = f"{BASE}{path}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code == 403:
        print(f"  [403] {path} -> Plan superior requerido")
        return None
    if r.status_code == 404:
        print(f"  [404] {path} -> Endpoint no encontrado")
        return None
    r.raise_for_status()
    return r.json()


def fetch_chatbots_list():
    """GET /api/v1/chatbots -> lista basica de chatbots."""
    print("Consultando lista de chatbots...")
    data = api_get("/api/v1/chatbots")
    if data is None:
        return []
    # La respuesta puede ser un array directo o {chatbot_list: [...]}
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("chatbot_list", data.get("result", []))
    return []


def fetch_chatbot_detail(bot_id):
    """Intenta obtener detalle de un chatbot por ID (endpoint no documentado)."""
    for path in [
        f"/api/v1/chatbots/{bot_id}",
        f"/api/v1/chatbots/{bot_id}/detail",
        f"/api/v1/chatbots/{bot_id}/flow",
        f"/api/ext/v3/chatbots/{bot_id}",
    ]:
        data = api_get(path)
        if data is not None:
            return data
    return None


# ── JSON parsing ─────────────────────────────────────────────────────────

def extract_nodes_from_export(data):
    """
    Extrae nodos y conexiones de un JSON exportado desde la UI de WATI.
    Se adapta a distintas formas posibles del JSON.
    """
    nodes = []
    edges = []

    # Buscar nodos en las claves mas comunes
    raw_nodes = (
        data.get("nodes")
        or data.get("Nodes")
        or data.get("steps")
        or data.get("Steps")
        or data.get("actions")
        or []
    )

    raw_edges = (
        data.get("edges")
        or data.get("Edges")
        or data.get("connections")
        or data.get("Connections")
        or data.get("links")
        or []
    )

    for n in raw_nodes:
        node = {
            "id": n.get("id") or n.get("Id") or n.get("nodeId") or str(len(nodes)),
            "type": n.get("type") or n.get("Type") or n.get("nodeType") or "unknown",
            "name": (
                n.get("name")
                or n.get("Name")
                or n.get("label")
                or n.get("title")
                or n.get("type", "Node")
            ),
        }
        # Detectar conexiones embebidas en el nodo
        next_ids = n.get("nextNodes") or n.get("next") or n.get("children") or []
        if isinstance(next_ids, str):
            next_ids = [next_ids]
        for nxt in next_ids:
            target = nxt if isinstance(nxt, str) else nxt.get("id", nxt.get("nodeId"))
            if target:
                edges.append({"from": node["id"], "to": target, "label": ""})
        nodes.append(node)

    for e in raw_edges:
        edges.append({
            "from": e.get("source") or e.get("from") or e.get("sourceId", ""),
            "to": e.get("target") or e.get("to") or e.get("targetId", ""),
            "label": e.get("label") or e.get("condition") or "",
        })

    return nodes, edges


def extract_structure_from_api_detail(data):
    """Intenta extraer estructura de una respuesta de detalle de la API."""
    if isinstance(data, dict):
        return extract_nodes_from_export(data)
    return [], []


# ── PUML generation ──────────────────────────────────────────────────────

NODE_SHAPES = {
    "sendmessage":    ("rectangle",  "#A8D5BA"),
    "send_message":   ("rectangle",  "#A8D5BA"),
    "send a message": ("rectangle",  "#A8D5BA"),
    "askquestion":    ("hexagon",    "#FFD699"),
    "ask_question":   ("hexagon",    "#FFD699"),
    "ask a question": ("hexagon",    "#FFD699"),
    "question":       ("hexagon",    "#FFD699"),
    "condition":      ("diamond",    "#FFB3B3"),
    "set_condition":  ("diamond",    "#FFB3B3"),
    "setcondition":   ("diamond",    "#FFB3B3"),
    "webhook":        ("cloud",      "#B3D4FF"),
    "template":       ("rectangle",  "#D5A8E8"),
    "assignteam":     ("actor",      "#C2C2C2"),
    "assign_team":    ("actor",      "#C2C2C2"),
    "assignuser":     ("actor",      "#C2C2C2"),
    "trigger":        ("rectangle",  "#FFFFB3"),
}


def sanitize_id(raw_id):
    clean = "".join(c if c.isalnum() else "_" for c in str(raw_id))
    if clean and clean[0].isdigit():
        clean = "n" + clean
    return clean or "node"


def node_type_key(node_type):
    return node_type.lower().replace(" ", "").replace("_", "").replace("-", "")


def generate_puml_from_nodes(bot_name, nodes, edges):
    lines = [
        "@startuml",
        f"title {bot_name}",
        "skinparam backgroundColor #FAFAFA",
        "skinparam defaultFontSize 12",
        "skinparam roundCorner 10",
        "",
    ]

    id_map = {}
    for n in nodes:
        sid = sanitize_id(n["id"])
        id_map[n["id"]] = sid
        key = node_type_key(n["type"])
        _, color = NODE_SHAPES.get(key, ("rectangle", "#E0E0E0"))
        label = n["name"][:40]
        ntype = n["type"]
        lines.append(f'rectangle "{label}\\n<size:9>[{ntype}]</size>" as {sid} {color}')

    lines.append("")

    for e in edges:
        src = id_map.get(e["from"], sanitize_id(e["from"]))
        tgt = id_map.get(e["to"], sanitize_id(e["to"]))
        lbl = f" : {e['label']}" if e.get("label") else ""
        lines.append(f"{src} --> {tgt}{lbl}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines)


def generate_puml_list_only(bots):
    """Genera un PUML simple cuando solo tenemos la lista de chatbots (sin detalle)."""
    lines = [
        "@startuml",
        "title WATI Chatbots - Vista General",
        "skinparam backgroundColor #FAFAFA",
        "skinparam defaultFontSize 12",
        "skinparam roundCorner 10",
        "",
        'rectangle "WATI\\nWhatsApp Business" as wati #A8D5BA',
        "",
    ]
    for i, bot in enumerate(bots):
        sid = sanitize_id(bot.get("id", f"bot{i}"))
        name = bot.get("name", f"Bot {i}")
        created = bot.get("created", "")[:10]
        lines.append(
            f'rectangle "{name}\\n<size:9>{created}</size>" as {sid} #B3D4FF'
        )
        lines.append(f"wati --> {sid}")
        lines.append("")

    lines.append("@enduml")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def process_export_file(filepath):
    """Procesa un archivo JSON exportado desde la UI de WATI."""
    print(f"Leyendo archivo: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Guardar JSON crudo para referencia
    OUTPUT_DIR.mkdir(exist_ok=True)
    raw_path = OUTPUT_DIR / "chatbot_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  JSON crudo guardado en: {raw_path}")

    # Determinar nombre del bot
    bot_name = (
        data.get("name")
        or data.get("Name")
        or data.get("botName")
        or Path(filepath).stem
    )

    nodes, edges = extract_nodes_from_export(data)

    if not nodes:
        print("  AVISO: No se encontraron nodos en el JSON.")
        print("  Estructura del JSON (claves de nivel 1):")
        if isinstance(data, dict):
            for k, v in data.items():
                vtype = type(v).__name__
                vlen = f" ({len(v)} items)" if isinstance(v, (list, dict)) else ""
                print(f"    - {k}: {vtype}{vlen}")
        print()
        print("  Guardando JSON completo para inspeccion manual.")
        print(f"  Revisa: {raw_path}")
        print("  Luego ajustaremos el parser a la estructura real.")
        return

    print(f"  Bot: {bot_name}")
    print(f"  Nodos: {len(nodes)}, Conexiones: {len(edges)}")

    puml = generate_puml_from_nodes(bot_name, nodes, edges)
    puml_path = OUTPUT_DIR / f"{sanitize_id(bot_name)}.puml"
    with open(puml_path, "w", encoding="utf-8") as f:
        f.write(puml)
    print(f"  Diagrama PUML guardado en: {puml_path}")


def process_via_api():
    """Consulta la API de WATI para obtener chatbots."""
    bots = fetch_chatbots_list()

    if not bots:
        print("No se encontraron chatbots o el endpoint no esta disponible.")
        print("Opciones:")
        print("  1. Actualiza tu plan a Pro en WATI")
        print("  2. Exporta tus chatbots como JSON desde la UI de WATI:")
        print("     Automation -> Chatbots -> boton Export")
        print("  3. Corre este script con: python fetch_chatbots.py --file <archivo.json>")
        return

    print(f"\nSe encontraron {len(bots)} chatbot(s):\n")
    for b in bots:
        print(f"  - {b.get('name', '?')} (id: {b.get('id', '?')})")

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Guardar lista cruda
    with open(OUTPUT_DIR / "chatbots_list.json", "w", encoding="utf-8") as f:
        json.dump(bots, f, indent=2, ensure_ascii=False)

    # Intentar obtener detalle de cada chatbot
    detailed = []
    print("\nIntentando obtener detalle de cada chatbot...")
    for bot in bots:
        bid = bot.get("id", "")
        detail = fetch_chatbot_detail(bid)
        if detail:
            print(f"  [OK] Detalle obtenido para: {bot.get('name')}")
            detailed.append({"bot": bot, "detail": detail})

            # Guardar JSON individual
            with open(OUTPUT_DIR / f"{sanitize_id(bid)}.json", "w", encoding="utf-8") as f:
                json.dump(detail, f, indent=2, ensure_ascii=False)

            nodes, edges = extract_structure_from_api_detail(detail)
            if nodes:
                puml = generate_puml_from_nodes(bot.get("name", bid), nodes, edges)
                puml_path = OUTPUT_DIR / f"{sanitize_id(bid)}.puml"
                with open(puml_path, "w", encoding="utf-8") as f:
                    f.write(puml)
                print(f"  Diagrama guardado: {puml_path}")

    if not detailed:
        print("\n  No se pudo obtener detalle de ningun chatbot via API.")
        print("  Generando diagrama de vista general (solo lista)...\n")
        puml = generate_puml_list_only(bots)
        puml_path = OUTPUT_DIR / "chatbots_overview.puml"
        with open(puml_path, "w", encoding="utf-8") as f:
            f.write(puml)
        print(f"  Diagrama guardado: {puml_path}")
        print()
        print("  Para obtener la estructura interna de cada chatbot:")
        print("  1. Ve a WATI -> Automation -> Chatbots")
        print("  2. Haz clic en Export en cada chatbot")
        print("  3. Corre: python fetch_chatbots.py --file <archivo.json>")


def main():
    parser = argparse.ArgumentParser(description="WATI Chatbots -> PlantUML")
    parser.add_argument(
        "--file", "-f",
        help="Archivo JSON exportado desde la UI de WATI (en vez de usar la API)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("  WATI Chatbot -> PlantUML")
    print("=" * 50)
    print()

    if args.file:
        process_export_file(args.file)
    else:
        process_via_api()

    print("\nListo.")


if __name__ == "__main__":
    main()
