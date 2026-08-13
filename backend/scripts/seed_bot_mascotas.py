"""Seed idempotente sprint "Ayuda a Cali": cuenta de la iniciativa + bot Huella.

Crea/asegura:
  - Cuenta dueña `recuperatumascota@gmail.com` (+ su team "Recupera Tu Mascota").
  - Bot "Huella — Mascotas Perdidas Cali" con engine='llm':
      * contexto a priori `mascotas_cali` (backend/app/bot_contexts/) con los
        tres caminos: buscar, reportar y descargar el listado.
      * `llm_config.mascotas` habilita las herramientas del módulo
        (buscar_mascota, ver_ficha, entregar_contacto, registrar_reporte,
        completar_reporte, descargar_listado).

Canales del mismo bot:
  1. Chat web público  → POST /mascotas/chat (mascotasperdidascali.glomabeauty.com).
  2. Simulador de la app → POST /bots/{id}/simulate (con JWT).
  3. WhatsApp          → PENDIENTE (ver sprint "Ayuda a Cali" en BITACORA).

Un único bot por cuenta (convención #254): el seed elimina los bots previos del
owner y re-crea el bot con la config más reciente. Correr en local y en RDS
(convención #1 de paridad).

Uso:
    docker compose -p wati exec -T backend python scripts/seed_bot_mascotas.py

ENV opcionales:
    MASCOTAS_ACCOUNT_EMAIL  (default recuperatumascota@gmail.com)
    MASCOTAS_PWD            (default Mascotas2026*)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models, schemas  # type: ignore


OWNER_EMAIL = os.environ.get("MASCOTAS_ACCOUNT_EMAIL", "recuperatumascota@gmail.com")
OWNER_PWD = os.environ.get("MASCOTAS_PWD", "Mascotas2026*")
OWNER_NAME = "Recupera Tu Mascota"
BOT_NAME = "Huella — Mascotas Perdidas Cali"


def _llm_config() -> dict:
    return {
        "context_key": "mascotas_cali",
        "assignee": "coordinador",
        # Se probó subir este bot a Sonnet (encadena más reglas por turno que
        # los demás), pero Bedrock rechaza los modelos que exigen suscripción de
        # Marketplace en esta cuenta: INVALID_PAYMENT_INSTRUMENT, el mismo
        # blocker abierto desde el Sprint 19 (#253). Se queda en el modelo por
        # defecto (Haiku) y la disciplina del flujo se sostiene con los
        # recordatorios deterministas que el motor inyecta en cada turno
        # (`llm_engine._bloque_mascotas`). Cuando se resuelva el medio de pago,
        # basta poner aquí "global.anthropic.claude-sonnet-4-6" y re-sembrar.
        "model_id": os.environ.get("MASCOTAS_MODEL_ID") or None,
        # La sola presencia de esta clave habilita las herramientas del módulo
        # de mascotas en el motor LLM (`llm_engine._tools_mascotas`).
        "mascotas": {
            "ciudad": "Cali",
            "iniciativa": "Recupera Tu Mascota",
            "motivo": "damnificados del terremoto en Colombia",
        },
        # #255 observabilidad: clasificador por keywords cuando el turno no
        # llama tools (las tools SON la decisión y tienen prioridad).
        "caminos": {
            "buscar_mascota": ["busco", "buscar", "se me perdio", "se me perdió",
                                "perdi", "perdí", "se perdio", "se perdió",
                                "no aparece", "desaparecio", "desapareció",
                                "extravio", "extravió", "mi perro", "mi gato",
                                "mi mascota"],
            "reportar_encontrada": ["encontre", "encontré", "me encontre",
                                     "hallé", "halle", "esta en mi casa",
                                     "está en mi casa", "recogi", "recogí",
                                     "aparecio", "apareció", "vi un perro",
                                     "vi una perra", "vi un gato", "rescate",
                                     "rescaté"],
            "descarga_listado": ["listado", "lista", "excel", "archivo",
                                  "descargar", "base de datos", "todas las"],
            "terremoto": ["terremoto", "sismo", "temblor", "damnificado",
                           "emergencia", "desastre"],
            "agradecimiento": ["gracias", "mil gracias", "muchas gracias",
                                "bendiciones", "dios te"],
        },
    }


# ---------------------------------------------------------------------------
# Pasos VISUALES (#256): el motor es llm_engine (los pasos NO se ejecutan);
# el visualizador de /bots/{id} muestra el bloque LLM de entrada, los tres
# caminos del servicio y los cierres.
# ---------------------------------------------------------------------------
STEPS = [
    # 1 — bloque LLM de entrada
    {"step_type": "llm", "label": "🤖 LLM · Huella saluda y detecta qué necesita",
     "config": {"mode": "route", "intents": [], "default_step_id": None,
                "mensaje": "Saluda, se presenta como Huella de Recupera Tu "
                           "Mascota, aclara que el servicio es gratuito y nació "
                           "para ayudar tras el terremoto, y ofrece los tres "
                           "caminos: buscar, reportar o descargar el listado."}},
    # 2-5 — CAMINO 1: la persona busca a su mascota
    {"step_type": "llm", "label": "1️⃣ Buscar · recoge los datos de a poco", "config": {
        "mode": "accion", "accion": "info",
        "fuente": "mensajes sucesivos de la persona (se van acumulando)",
        "mensaje": "Pregunta de a uno: qué animal es, cómo es (color, raza, "
                   "tamaño), dónde y cuándo se perdió, nombre y señas. Nunca "
                   "exige un dato: si no lo sabe, sigue."}},
    {"step_type": "llm", "label": "1️⃣ Buscar · cruza contra las encontradas", "config": {
        "mode": "accion", "accion": "consulta",
        "fuente": "tool buscar_mascota (scoring por campos) → tabla mascotas",
        "mensaje": "Busca coincidencias entre las mascotas que otras personas "
                   "encontraron, con todos los datos reunidos."}},
    {"step_type": "llm", "label": "1️⃣ Hay coincidencia · ficha y foto", "config": {
        "mode": "accion", "accion": "media",
        "fuente": "tool ver_ficha → foto guardada en mascotas/<codigo>/",
        "mensaje": "Muestra la más parecida primero, con su foto, y pregunta "
                   "«¿es esta tu mascota?». Una a la vez."}},
    {"step_type": "llm", "label": "1️⃣ Es la suya · entrega el contacto", "config": {
        "mode": "accion", "accion": "registro",
        "fuente": "tool entregar_contacto (única salida de datos de contacto)",
        "mensaje": "Comparte ubicación, enlace de Maps y teléfono de quien la "
                   "encontró. Recomienda llevar fotos que acrediten la mascota."}},
    # 6 — sin coincidencias
    {"step_type": "llm", "label": "1️⃣ Sin coincidencias · registra y avisará", "config": {
        "mode": "accion", "accion": "registro",
        "fuente": "tool registrar_reporte (tipo_registro='perdida')",
        "mensaje": "Explica que aún no hay coincidencias, que la lista se "
                   "actualiza todos los días y que su caso queda en la base de "
                   "datos. Pide teléfono para avisarle apenas aparezca algo."}},
    # 7-9 — CAMINO 2: la persona encontró una mascota
    {"step_type": "llm", "label": "2️⃣ Reportar · datos, fotos y ubicación", "config": {
        "mode": "accion", "accion": "info",
        "fuente": "mensajes de la persona + fotos adjuntas por el clip 📎",
        "mensaje": "Agradece, y pide de a poco: especie, color y tamaño, dónde "
                   "la encontró (OBLIGATORIO), desde cuándo, señas, collar o "
                   "placa, fotos y teléfono de contacto (OBLIGATORIO)."}},
    {"step_type": "llm", "label": "2️⃣ Reportar · guarda en la base de datos", "config": {
        "mode": "accion", "accion": "registro",
        "fuente": "tool registrar_reporte (tipo_registro='encontrada')",
        "mensaje": "Registra el caso y confirma el código MC-xxxxx. Las fotos "
                   "que ya adjuntó se guardan solas en la carpeta del reporte."}},
    {"step_type": "llm", "label": "2️⃣ ¿Ya la están buscando?", "config": {
        "mode": "accion", "accion": "consulta",
        "fuente": "tool buscar_mascota (buscar_en='perdidas')",
        "mensaje": "Cruza el hallazgo contra los reportes de familias que "
                   "buscan. Si coincide, muestra la ficha y entrega el contacto."}},
    # 10 — CAMINO 3: descarga del listado
    {"step_type": "llm", "label": "3️⃣ Descargar listado en Excel", "config": {
        "mode": "accion", "accion": "archivo",
        "fuente": "tool descargar_listado → /mascotas/listado.xlsx (token firmado)",
        "mensaje": "Entrega el botón de descarga del listado actualizado y "
                   "aclara que el archivo cambia cada vez que alguien reporta."}},
    # 11 — post-acción
    {"step_type": "llm", "label": "🤖 LLM · ¿algo más o despedida?", "config": {
        "mode": "route", "intents": [],
        "mensaje": "Huella lee la respuesta: si trae un caso nuevo lo enruta; "
                   "si la persona se despide, cierra con calidez."}},
    # 12 — fin
    {"step_type": "end", "label": "Fin de la conversación", "config": {}},
]

ROUTER_INTENTS = [
    ("Busco a mi mascota", 2),
    ("Encontré una mascota", 7),
    ("Quiero el listado", 10),
    ("Despedida", 12),
]


def _wire(db, bot: models.Bot) -> None:
    """Cablea el diagrama: router LLM → 3 caminos → post-acción → fin."""
    import json as _j
    P = {s.position: s for s in bot.steps}

    def _route(pos: int, intents: list, default=None):
        cfg = _j.loads(P[pos].config or "{}")
        cfg.update({
            "mode": "route",
            "intents": [{"keywords": [k], "step_id": P[t].id} for k, t in intents],
            "default_step_id": P[default].id if default else None,
        })
        P[pos].config = _j.dumps(cfg, ensure_ascii=False)
        P[pos].next_step_id = None

    # Router principal. Default → camino de búsqueda (lo que más pide la gente).
    _route(1, ROUTER_INTENTS, default=2)

    # Camino 1: recoge datos → busca → (ficha → contacto) | sin coincidencias
    P[2].next_step_id = P[3].id
    P[3].next_step_id = P[4].id
    P[4].next_step_id = P[5].id
    P[5].next_step_id = P[11].id
    P[6].next_step_id = P[11].id
    # Camino 2: datos → registra → cruza contra las perdidas
    P[7].next_step_id = P[8].id
    P[8].next_step_id = P[9].id
    P[9].next_step_id = P[11].id
    # Camino 3
    P[10].next_step_id = P[11].id

    _route(11, [("Nuevo caso", 1), ("Buscar otra", 2), ("Reportar otra", 7),
                ("Listado", 10), ("Despedida", 12)])
    db.commit()


def _ensure_user(db, *, nombre, correo, documento, password) -> models.User:
    user = crud.get_user_by_email(db, correo)
    if user:
        return user
    return crud.create_user(db, schemas.UserCreate(
        nombre=nombre, tipo_documento="CC", documento=documento,
        correo=correo, password=password,
    ))


def main() -> int:
    db = SessionLocal()
    try:
        owner = _ensure_user(
            db, nombre=OWNER_NAME, correo=OWNER_EMAIL,
            documento="MASCOTAS001", password=OWNER_PWD,
        )
        team = crud.get_team_by_owner(db, owner)
        if team is None:
            team = crud.create_team(db, OWNER_NAME, owner)
        print(f"OK: owner={owner.correo} team_id={team.id}")

        # Un único bot por cuenta (#254): se eliminan los previos y se re-crea
        # con la config más reciente.
        previos = db.query(models.Bot).filter(models.Bot.user_id == owner.id).all()
        for b in previos:
            db.delete(b)
        if previos:
            db.commit()
            print(f"OK: {len(previos)} bot(s) previo(s) eliminado(s) para recrear")

        bot = crud.create_bot_with_steps(
            db, owner, name=BOT_NAME,
            description="Bot de la iniciativa Recupera Tu Mascota (Claude vía "
                        "Bedrock): ayuda a las familias afectadas por el "
                        "terremoto a encontrar a sus mascotas, registra las "
                        "mascotas halladas y entrega el listado en Excel.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=STEPS, engine="llm", llm_config=_llm_config(),
        )
        _wire(db, bot)
        print(f"OK: bot LLM creado id={bot.id} con {len(bot.steps)} bloques visuales")

        print()
        print("=== Cuenta de Recupera Tu Mascota lista ===")
        print(f"  login:   {OWNER_EMAIL}")
        print(f"  bot_id:  {bot.id}  (engine=llm, contexto 'mascotas_cali')")
        print("  canales: chat web público · simulador · WhatsApp (pendiente)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
