"""Barrido de secretos sobre TODO el historial de git.

No hay gitleaks en el equipo, así que esto recorre cada blob que exista en
cualquier rama (`git rev-list --objects --all`) y lo pasa por una lista de
patrones de alta señal.

Los hallazgos se imprimen **enmascarados**: nombre del patrón, archivo y los
primeros caracteres. El objetivo es saber *qué hay que rotar y dónde*, no
volver a exponer el secreto en otra pantalla.
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict

PATRONES = [
    ("AWS access key",      re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("Clave privada",       re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Twilio Account SID",  re.compile(rb"\bAC[0-9a-f]{32}\b")),
    ("Twilio API Key SID",  re.compile(rb"\bSK[0-9a-f]{32}\b")),
    ("Slack token",         re.compile(rb"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("Google API key",      re.compile(rb"AIza[0-9A-Za-z\-_]{35}")),
    ("OpenAI/Anthropic key", re.compile(rb"sk-(ant-)?[A-Za-z0-9_\-]{20,}")),
    ("GitHub token",        re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("URL con contraseña",  re.compile(rb"(?:postgres(?:ql)?|mysql|mongodb)(?:\+\w+)?://[^\s:/@]+:[^\s@]{3,}@")),
    ("Asignación de secreto",
     re.compile(rb"(?i)\b(password|passwd|contrase\xc3\xb1a|secret_key|api_key|auth_token|access_token)\b\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']")),
]

# Ruido conocido: dependencias, lock files y artefactos de build.
IGNORAR = re.compile(
    r"(^|/)(node_modules|\.next|dist|build)/"
    r"|package-lock\.json$|yarn\.lock$|poetry\.lock$|tsbuildinfo$"
    r"|\.(png|jpe?g|gif|webp|pdf|ico|woff2?|ttf|mp4|zip)$",
    re.IGNORECASE,
)

# Valores de ejemplo/plantilla que no son secretos de verdad.
FALSOS = re.compile(
    rb"(?i)^(x+|your[_-].*|change[_-]?me|placeholder|example|tu[_-].*|"
    rb"\.\.\.|<.*>|\$\{.*\}|test|password|secret|clave-de-prueba-1|"
    rb"[a-z]*hashed[a-z]*)$"
)


def blobs():
    salida = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        capture_output=True, check=True,
    ).stdout.decode("utf-8", "replace")
    for linea in salida.splitlines():
        partes = linea.split(" ", 1)
        if len(partes) == 2 and partes[1].strip():
            yield partes[0], partes[1].strip()


def enmascarar(valor: bytes) -> str:
    txt = valor.decode("utf-8", "replace")
    if len(txt) <= 6:
        return "*" * len(txt)
    return f"{txt[:3]}…{'*' * 6} ({len(txt)} chars)"


def main() -> None:
    hallazgos = defaultdict(set)
    revisados = 0

    for sha, ruta in blobs():
        if IGNORAR.search(ruta):
            continue
        try:
            datos = subprocess.run(
                ["git", "cat-file", "blob", sha],
                capture_output=True, check=True,
            ).stdout
        except subprocess.CalledProcessError:
            continue
        if b"\x00" in datos[:1024] or len(datos) > 2_000_000:
            continue  # binario o gigante
        revisados += 1

        for nombre, patron in PATRONES:
            for m in patron.finditer(datos):
                valor = m.group(2) if patron.groups >= 2 and m.lastindex and m.lastindex >= 2 else m.group(0)
                if FALSOS.match(valor.strip()):
                    continue
                hallazgos[(nombre, ruta)].add(enmascarar(valor))

    print(f"blobs de texto revisados: {revisados}\n")
    if not hallazgos:
        print("Sin hallazgos.")
        return

    print(f"{len(hallazgos)} combinaciones patrón×archivo con posible secreto:\n")
    for (nombre, ruta), valores in sorted(hallazgos.items()):
        print(f"  [{nombre}] {ruta}")
        for v in sorted(valores)[:4]:
            print(f"      → {v}")


if __name__ == "__main__":
    main()
