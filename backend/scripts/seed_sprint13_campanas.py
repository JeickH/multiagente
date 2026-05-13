"""Seed idempotente Sprint 13 — Campañas demo para `demo@gmail.com`.

Crea / actualiza para el team de demo@:
  - 50 contactos sintéticos (40 opt_in=True, 10 opt_in=False), nombres y
    atributos JSONB deterministas. Números E.164 `+57301XXXX...` con sufijo
    determinista derivado del índice (no aleatorio → idempotente).
  - 3 grupos: "Clientes Premium" (12 miembros segment=premium),
    "Recurrentes Bogotá" (15 miembros city=Bogotá AND opt_in=True),
    "Nuevos Trial" (8 miembros segment=trial).
  - 2 plantillas WhatsApp mock APPROVED: `promo_mayo` (es_MX) con header
    de texto + body con `{{1}}`/`{{2}}` + footer; `recordatorio_pedido`
    (es) con body solo.
  - 2 campañas completadas con métricas: "Promoción Mayo" (grupo Premium,
    12 destinatarios) y "Recordatorio carrito" (8 contactos individuales).
  - 1 campaña agendada futura: "Lanzamiento producto" (grupo Nuevos Trial).
  - `wamid` mock `wamid.seed-<idx>-<short_uuid>` para cada recipient
    enviado, y `campaign_events` coherentes (queued/sent/delivered/read/failed).

Idempotencia:
  - Contactos por `(team_id, phone_e164)`.
  - Grupos por `(team_id, name)` y membresías por PK (group_id, contact_id).
  - Plantillas por `(meta_account_id, name, language)`.
  - Campañas por `(team_id, name)`: si la campaña ya existe, se conserva
    (no se duplican filas hijas).
  - Si demo@ no tiene MetaAccount, se crea una mock sandbox
    (encrypted_access_token=NULL).

Uso:
    docker compose exec -T backend python scripts/seed_sprint13_campanas.py
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models  # type: ignore


DEMO_EMAIL = "demo@gmail.com"

# ─────────────────────────── Contactos ─────────────────────────────────
# 50 nombres distintos (ordenados). Los primeros 40 → opt_in=True; los 10
# últimos → opt_in=False (para probar S13-003).
DEMO_NAMES = [
    "María González", "Juan Pérez", "Carolina Ruiz", "Andrés Castro",
    "Laura Martínez", "Felipe Ramírez", "Valentina López", "Camilo Torres",
    "Daniela Herrera", "Santiago Vargas", "Isabella Romero", "Mateo Mejía",
    "Sofía Cárdenas", "Sebastián Ortiz", "Manuela Cifuentes", "Tomás Salazar",
    "Gabriela Pinilla", "Nicolás Bedoya", "Mariana Echeverri", "Esteban Quintero",
    "Catalina Álvarez", "Daniel Restrepo", "Paula Giraldo", "Alejandro Duque",
    "Juliana Henao", "Ricardo Cano", "Adriana Marín", "Pablo Hincapié",
    "Natalia Cardona", "Diego Posada", "Lucía Bermúdez", "Carlos Bustamante",
    "Verónica Tobón", "Esteban Zuluaga", "Carolina Múnera", "Andrea Rincón",
    "Jorge Saavedra", "Camila Trujillo", "Federico Arango", "Ximena Suárez",
    "Antonia Galindo", "Iván Sepúlveda", "Renata Villegas", "Bruno Aristizábal",
    "Inés Ochoa", "Óscar Patiño", "Luisa Acevedo", "Hugo Botero",
    "Elena Maya", "Tobías Calle",
]
assert len(DEMO_NAMES) == 50

CITIES = ["Bogotá", "Medellín", "Cali"]
SEGMENTS = ["premium", "standard", "trial"]


def _phone_for_index(i: int) -> str:
    """E.164 colombiano determinista: +57301 + 7 dígitos derivados de `i`.

    Hash MD5 truncado evita colisiones para i en [0,49], y al ser
    determinista garantiza idempotencia en re-ejecuciones.
    """
    h = hashlib.md5(f"seed-sprint13-contact-{i}".encode("utf-8")).hexdigest()
    # Tomar 7 dígitos del hash interpretado como entero
    digits = str(int(h[:10], 16))[-7:].zfill(7)
    return f"+57301{digits}"


def _contact_spec(i: int) -> dict:
    """Spec determinista para el contacto `i` (0-indexed).

    Distribución de ciudades pensada para garantizar ≥15 contactos
    `city=Bogotá AND opt_in=True` (requerido por el grupo "Recurrentes
    Bogotá", spec #169). Los primeros 15 índices (todos con opt_in=True
    porque i<40) van a Bogotá; el resto rota Medellín/Cali/Bogotá según
    i%3, manteniendo determinismo.
    """
    if i < 15:
        city = "Bogotá"
    else:
        # rotación entre Medellín / Cali / Bogotá para los i>=15
        city = ["Medellín", "Cali", "Bogotá"][(i - 15) % 3]
    return {
        "name": DEMO_NAMES[i],
        "phone_e164": _phone_for_index(i),
        "email": f"demo.contact{i:02d}@example.com",
        "opt_in": i < 40,  # primeros 40 opt_in=True, últimos 10 False
        "opt_in_source": "import_csv" if i < 40 else None,
        "attributes": {
            "city": city,
            "segment": SEGMENTS[i % 3],
        },
    }


# ─────────────────────────── Plantillas ────────────────────────────────
TEMPLATES = [
    {
        "name": "promo_mayo",
        "language": "es_MX",
        "category": "MARKETING",
        "components_json": [
            {"type": "HEADER", "format": "TEXT", "text": "¡Promo de Mayo en Gloma!"},
            {
                "type": "BODY",
                "text": (
                    "Hola {{1}}, tenemos un descuento del {{2}}% en toda la "
                    "colección de mayo. Aprovecha antes de que termine la "
                    "temporada."
                ),
                "example": {"body_text": [["María", "20"]]},
            },
            {"type": "FOOTER", "text": "Responde STOP para no recibir más"},
        ],
    },
    {
        "name": "recordatorio_pedido",
        "language": "es",
        "category": "UTILITY",
        "components_json": [
            {
                "type": "BODY",
                "text": (
                    "Hola, te recordamos que tienes un pedido pendiente en tu "
                    "carrito. ¿Te ayudamos a completarlo?"
                ),
            },
        ],
    },
]


# ─────────────────────────── Grupos ────────────────────────────────────
GROUPS_SPEC = [
    {
        "name": "Clientes Premium",
        "description": "Contactos con segment=premium",
        "filter": lambda c: c["attributes"].get("segment") == "premium",
        "limit": 12,
    },
    {
        "name": "Recurrentes Bogotá",
        "description": "Contactos en Bogotá con opt_in habilitado",
        "filter": lambda c: c["attributes"].get("city") == "Bogotá" and c["opt_in"],
        "limit": 15,
    },
    {
        "name": "Nuevos Trial",
        "description": "Contactos con segment=trial",
        "filter": lambda c: c["attributes"].get("segment") == "trial",
        "limit": 8,
    },
]


# ─────────────────────────── Helpers ───────────────────────────────────
def _ensure_meta_account(db, team_id: int) -> models.MetaAccount:
    """Devuelve MetaAccount de demo@; si no existe crea una sandbox mock."""
    meta = (
        db.query(models.MetaAccount)
        .filter(models.MetaAccount.team_id == team_id)
        .first()
    )
    if meta is not None:
        return meta

    # Para sandbox cifra un placeholder. La columna es NOT NULL, y el
    # campaign_sender entra en modo sandbox cuando META_SANDBOX=1 (env var),
    # independientemente del valor del token.
    try:
        from app.services.crypto import encrypt_secret  # type: ignore
        placeholder_ct = encrypt_secret("sandbox-placeholder")
    except Exception:
        placeholder_ct = "sandbox-placeholder"  # fallback: solo prod si crypto rompe
    meta = models.MetaAccount(
        team_id=team_id,
        phone_number_id="seed-phone",
        waba_id="seed-waba",
        display_phone="+57 301 999 9999",
        verified_name="Demo Gloma",
        encrypted_access_token=placeholder_ct,
        api_version="v22.0",
        is_active=True,
        status="active",
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


def _seed_contacts(db, team_id: int) -> tuple[list[models.Contact], int, int]:
    """Devuelve (lista_ordenada_por_indice, creados, actualizados)."""
    created = 0
    updated = 0
    contacts: list[models.Contact] = []
    for i in range(50):
        spec = _contact_spec(i)
        existing = (
            db.query(models.Contact)
            .filter(
                models.Contact.team_id == team_id,
                models.Contact.phone_e164 == spec["phone_e164"],
            )
            .first()
        )
        if existing is None:
            c = models.Contact(
                team_id=team_id,
                phone_e164=spec["phone_e164"],
                name=spec["name"],
                email=spec["email"],
                attributes=spec["attributes"],
                opt_in=spec["opt_in"],
                opt_in_source=spec["opt_in_source"],
            )
            db.add(c)
            db.flush()
            created += 1
            contacts.append(c)
        else:
            # Update determinista para mantener consistencia si cambió el spec
            changed = False
            if existing.name != spec["name"]:
                existing.name = spec["name"]; changed = True
            if existing.email != spec["email"]:
                existing.email = spec["email"]; changed = True
            if existing.attributes != spec["attributes"]:
                existing.attributes = spec["attributes"]; changed = True
            if existing.opt_in != spec["opt_in"]:
                existing.opt_in = spec["opt_in"]; changed = True
            if existing.opt_in_source != spec["opt_in_source"]:
                existing.opt_in_source = spec["opt_in_source"]; changed = True
            if changed:
                db.add(existing)
                updated += 1
            contacts.append(existing)
    db.commit()
    return contacts, created, updated


def _seed_groups(
    db, team_id: int, contacts: list[models.Contact]
) -> tuple[dict[str, models.ContactGroup], int, int]:
    """Devuelve ({name: group}, grupos_creados, miembros_creados)."""
    groups: dict[str, models.ContactGroup] = {}
    grp_created = 0
    mem_created = 0
    # Specs y contactos en sus index originales (para filter idéntico al spec)
    specs_by_idx = [_contact_spec(i) for i in range(50)]

    for g in GROUPS_SPEC:
        existing = (
            db.query(models.ContactGroup)
            .filter(
                models.ContactGroup.team_id == team_id,
                models.ContactGroup.name == g["name"],
            )
            .first()
        )
        if existing is None:
            existing = models.ContactGroup(
                team_id=team_id, name=g["name"], description=g["description"]
            )
            db.add(existing)
            db.flush()
            grp_created += 1
        else:
            if existing.description != g["description"]:
                existing.description = g["description"]
                db.add(existing)
        groups[g["name"]] = existing

        # Selección determinista: primer N índices que cumplan el filtro
        selected_indices = [
            i for i, s in enumerate(specs_by_idx) if g["filter"](s)
        ][: g["limit"]]
        selected_contact_ids = {contacts[i].id for i in selected_indices}

        # Reconciliar membresías: añadir las que faltan
        for idx in selected_indices:
            contact = contacts[idx]
            already = (
                db.query(models.ContactGroupMember)
                .filter(
                    models.ContactGroupMember.group_id == existing.id,
                    models.ContactGroupMember.contact_id == contact.id,
                )
                .first()
            )
            if already is None:
                db.add(
                    models.ContactGroupMember(
                        group_id=existing.id, contact_id=contact.id
                    )
                )
                mem_created += 1

        # ... y eliminar las que sobran (membresías de seeds previos que ya
        # no cumplen el filtro tras un ajuste del spec — mantiene idempotencia
        # convergente al spec actual).
        stale = (
            db.query(models.ContactGroupMember)
            .filter(
                models.ContactGroupMember.group_id == existing.id,
                ~models.ContactGroupMember.contact_id.in_(selected_contact_ids),
            )
            .all()
        )
        for m in stale:
            db.delete(m)
    db.commit()
    return groups, grp_created, mem_created


def _seed_templates(
    db, meta_account_id: int
) -> tuple[dict[str, models.WhatsappTemplate], int]:
    """Devuelve ({name: template}, creadas)."""
    out: dict[str, models.WhatsappTemplate] = {}
    created = 0
    now = datetime.utcnow()
    for t in TEMPLATES:
        existing = (
            db.query(models.WhatsappTemplate)
            .filter(
                models.WhatsappTemplate.meta_account_id == meta_account_id,
                models.WhatsappTemplate.name == t["name"],
                models.WhatsappTemplate.language == t["language"],
            )
            .first()
        )
        if existing is None:
            existing = models.WhatsappTemplate(
                meta_account_id=meta_account_id,
                meta_template_id=f"mock-tpl-{t['name']}",
                name=t["name"],
                category=t["category"],
                language=t["language"],
                status="APPROVED",
                components_json=t["components_json"],
                last_synced_at=now,
            )
            db.add(existing)
            db.flush()
            created += 1
        else:
            # Asegurar APPROVED y components al día (idempotente)
            existing.status = "APPROVED"
            existing.category = t["category"]
            existing.components_json = t["components_json"]
            existing.last_synced_at = now
            db.add(existing)
        out[t["name"]] = existing
    db.commit()
    return out, created


def _wamid(idx: int) -> str:
    short = uuid.uuid4().hex[:8]
    return f"wamid.seed-{idx}-{short}"


def _seed_campaign(
    db,
    *,
    team_id: int,
    meta_account_id: int,
    template: models.WhatsappTemplate,
    created_by_user_id: int,
    name: str,
    status: str,
    scheduled_at: datetime | None,
    started_at: datetime | None,
    completed_at: datetime | None,
    recipients_plan: list[dict],
    template_variables_json: dict | None = None,
) -> tuple[models.Campaign, str]:
    """Crea o reusa una campaña por (team_id, name). recipients_plan es
    lista de dicts {contact, status, error_code?, sent_offset_min?,
    delivered_offset_min?, read_offset_min?, failed_offset_min?}.
    """
    existing = (
        db.query(models.Campaign)
        .filter(models.Campaign.team_id == team_id, models.Campaign.name == name)
        .first()
    )
    if existing is not None:
        return existing, "skip"

    camp = models.Campaign(
        team_id=team_id,
        meta_account_id=meta_account_id,
        template_id=template.id,
        name=name,
        status=status,
        scheduled_at=scheduled_at,
        started_at=started_at,
        completed_at=completed_at,
        template_variables_json=template_variables_json or {},
        created_by_user_id=created_by_user_id,
    )
    db.add(camp)
    db.flush()

    # Evento "queued" a nivel campaña
    queued_count = sum(1 for r in recipients_plan if r["status"] != "skipped")
    skipped_count = sum(1 for r in recipients_plan if r["status"] == "skipped")
    db.add(
        models.CampaignEvent(
            campaign_id=camp.id,
            recipient_id=None,
            event_type="queued",
            payload_json={
                "queued": queued_count,
                "skipped_opt_out": skipped_count,
            },
            created_at=(started_at or scheduled_at or camp.created_at),
        )
    )

    base_time = started_at or scheduled_at or camp.created_at

    for idx, plan in enumerate(recipients_plan):
        contact: models.Contact = plan["contact"]
        r_status = plan["status"]
        wamid = None
        if r_status in ("sent", "delivered", "read", "failed"):
            wamid = _wamid(idx + camp.id * 1000)

        sent_at = None
        delivered_at = None
        read_at = None
        failed_at = None

        if r_status in ("sent", "delivered", "read", "failed"):
            sent_at = base_time + timedelta(minutes=plan.get("sent_offset_min", 1))
        if r_status in ("delivered", "read"):
            delivered_at = sent_at + timedelta(minutes=plan.get("delivered_offset_min", 1))
        if r_status == "read":
            read_at = delivered_at + timedelta(minutes=plan.get("read_offset_min", 2))
        if r_status == "failed":
            failed_at = sent_at + timedelta(minutes=plan.get("failed_offset_min", 1))

        rec = models.CampaignRecipient(
            campaign_id=camp.id,
            contact_id=contact.id,
            phone_e164=contact.phone_e164,
            meta_message_id=wamid,
            status=r_status,
            error_code=plan.get("error_code"),
            sent_at=sent_at,
            delivered_at=delivered_at,
            read_at=read_at,
            failed_at=failed_at,
        )
        db.add(rec)
        db.flush()

        # Eventos por recipient consistentes con el status final
        if r_status in ("sent", "delivered", "read", "failed"):
            db.add(
                models.CampaignEvent(
                    campaign_id=camp.id,
                    recipient_id=rec.id,
                    event_type="sent",
                    meta_message_id=wamid,
                    created_at=sent_at,
                    payload_json={"wamid": wamid},
                )
            )
        if r_status in ("delivered", "read"):
            db.add(
                models.CampaignEvent(
                    campaign_id=camp.id,
                    recipient_id=rec.id,
                    event_type="delivered",
                    meta_message_id=wamid,
                    created_at=delivered_at,
                    payload_json={"wamid": wamid},
                )
            )
        if r_status == "read":
            db.add(
                models.CampaignEvent(
                    campaign_id=camp.id,
                    recipient_id=rec.id,
                    event_type="read",
                    meta_message_id=wamid,
                    created_at=read_at,
                    payload_json={"wamid": wamid},
                )
            )
        if r_status == "failed":
            db.add(
                models.CampaignEvent(
                    campaign_id=camp.id,
                    recipient_id=rec.id,
                    event_type="failed",
                    meta_message_id=wamid,
                    created_at=failed_at,
                    payload_json={
                        "wamid": wamid,
                        "error_code": plan.get("error_code"),
                    },
                )
            )

    db.commit()
    db.refresh(camp)
    return camp, "nuevo"


# ─────────────────────────── Main ──────────────────────────────────────
def main() -> int:
    db = SessionLocal()
    try:
        owner = crud.get_user_by_email(db, DEMO_EMAIL)
        if owner is None:
            print(f"ERROR: usuario {DEMO_EMAIL} no existe.")
            return 1

        membership = crud.get_membership_for_user(db, owner)
        if membership is None:
            print(f"ERROR: {DEMO_EMAIL} no tiene team asociado.")
            return 1

        team_id = membership.team_id
        print(f"Owner={DEMO_EMAIL} team_id={team_id}")

        meta = _ensure_meta_account(db, team_id)
        print(f"MetaAccount id={meta.id} sandbox_placeholder={meta.encrypted_access_token is not None}")

        # 1) Contactos
        contacts, c_created, c_updated = _seed_contacts(db, team_id)
        print(
            f"Contactos: {len(contacts)} total "
            f"(creados={c_created} actualizados={c_updated})"
        )

        # 2) Grupos
        groups, g_created, m_created = _seed_groups(db, team_id, contacts)
        print(
            f"Grupos: {len(groups)} total (creados={g_created}) "
            f"membresías nuevas={m_created}"
        )

        # 3) Plantillas mock APPROVED
        templates, t_created = _seed_templates(db, meta.id)
        print(f"Plantillas: {len(templates)} total (creadas={t_created})")

        # 4) Campañas
        now = datetime.utcnow()
        specs_by_idx = [_contact_spec(i) for i in range(50)]
        idx_premium = [
            i for i, s in enumerate(specs_by_idx)
            if s["attributes"].get("segment") == "premium"
        ][:12]
        idx_trial_group = [
            i for i, s in enumerate(specs_by_idx)
            if s["attributes"].get("segment") == "trial"
        ][:8]

        # Campaña A: "Promoción Mayo" — 12 destinatarios (grupo Premium)
        # 10 delivered+read, 1 delivered (no read), 1 failed (error_code 80007)
        plan_a = []
        for i, idx in enumerate(idx_premium):
            contact = contacts[idx]
            if i < 10:
                plan_a.append({
                    "contact": contact, "status": "read",
                    "sent_offset_min": 1, "delivered_offset_min": 1,
                    "read_offset_min": 3,
                })
            elif i == 10:
                plan_a.append({
                    "contact": contact, "status": "delivered",
                    "sent_offset_min": 1, "delivered_offset_min": 2,
                })
            else:  # i == 11
                plan_a.append({
                    "contact": contact, "status": "failed",
                    "error_code": "80007", "sent_offset_min": 1,
                    "failed_offset_min": 1,
                })
        started_a = now - timedelta(days=3)
        camp_a, action_a = _seed_campaign(
            db,
            team_id=team_id,
            meta_account_id=meta.id,
            template=templates["promo_mayo"],
            created_by_user_id=owner.id,
            name="Promoción Mayo",
            status="completed",
            scheduled_at=None,
            started_at=started_a,
            completed_at=started_a + timedelta(minutes=30),
            recipients_plan=plan_a,
            template_variables_json={
                "body": [
                    {"index": 1, "value": "{{contact.name}}"},
                    {"index": 2, "value": "20"},
                ]
            },
        )
        print(f"Campaña A 'Promoción Mayo': {action_a} (id={camp_a.id})")

        # Campaña B: "Recordatorio carrito" — 8 contactos individuales
        # 5 read, 2 delivered, 1 skipped (opt_out_at_enqueue)
        # Tomar los 7 primeros opt_in=True que NO son premium + 1 con opt_in=False
        non_premium_optin_idx = [
            i for i, s in enumerate(specs_by_idx)
            if s["opt_in"] and s["attributes"].get("segment") != "premium"
        ][:7]
        optout_idx = [
            i for i, s in enumerate(specs_by_idx) if not s["opt_in"]
        ][:1]
        idx_b = non_premium_optin_idx + optout_idx  # 8 total
        plan_b = []
        for i, idx in enumerate(idx_b):
            contact = contacts[idx]
            if i < 5:
                plan_b.append({
                    "contact": contact, "status": "read",
                    "sent_offset_min": 1, "delivered_offset_min": 1,
                    "read_offset_min": 2,
                })
            elif i < 7:
                plan_b.append({
                    "contact": contact, "status": "delivered",
                    "sent_offset_min": 1, "delivered_offset_min": 2,
                })
            else:  # i == 7 → contacto con opt_in=False
                plan_b.append({
                    "contact": contact, "status": "skipped",
                    "error_code": "opt_out_at_enqueue",
                })
        started_b = now - timedelta(days=1)
        camp_b, action_b = _seed_campaign(
            db,
            team_id=team_id,
            meta_account_id=meta.id,
            template=templates["recordatorio_pedido"],
            created_by_user_id=owner.id,
            name="Recordatorio carrito",
            status="completed",
            scheduled_at=None,
            started_at=started_b,
            completed_at=started_b + timedelta(minutes=15),
            recipients_plan=plan_b,
        )
        print(f"Campaña B 'Recordatorio carrito': {action_b} (id={camp_b.id})")

        # Campaña C: "Lanzamiento producto" — agendada futura, grupo Nuevos Trial
        # 0 enviados, todos queued
        plan_c = []
        for idx in idx_trial_group:
            plan_c.append({"contact": contacts[idx], "status": "queued"})
        scheduled_c = now + timedelta(days=2)
        camp_c, action_c = _seed_campaign(
            db,
            team_id=team_id,
            meta_account_id=meta.id,
            template=templates["promo_mayo"],
            created_by_user_id=owner.id,
            name="Lanzamiento producto",
            status="scheduled",
            scheduled_at=scheduled_c,
            started_at=None,
            completed_at=None,
            recipients_plan=plan_c,
            template_variables_json={
                "body": [
                    {"index": 1, "value": "{{contact.name}}"},
                    {"index": 2, "value": "15"},
                ]
            },
        )
        print(f"Campaña C 'Lanzamiento producto': {action_c} (id={camp_c.id})")

        print("\nOK seed Sprint 13 #169.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
