"""Importa los reportes de patitasacasa.com a nuestra tabla `mascotas`.

"Patitas a Casa" es otra plataforma solidaria del terremoto. A diferencia de
`mascotasporcolombia`, aquí **sí traemos las fotos** a nuestro storage: su app
no publica una ficha por mascota (es una SPA sin URL propia por reporte), así
que si no copiáramos la imagen no habría nada que mostrarle a la persona.

Qué hace
--------
1. Consulta su **API pública** `GET /prod/pets/<ciudad>?limit=…` — la misma que
   usa su propia web. Devuelve JSON estructurado, así que no hay que parsear
   HTML ni adivinar selectores: es mucho más estable que raspar la página.
2. Mapea cada reporte a nuestro esquema y deduplica por `pet_id`.
3. Descarga la foto (`photo_url`) y la guarda en nuestro storage bajo
   `mascotas/<codigo>/`, como cualquier foto que suba un ciudadano.

Decisiones que conviene conocer
-------------------------------
* **`report_type` manda el tipo**: `lost` → perdida, `found` → encontrada. NO se
  usa `status`, que en su modelo significa otra cosa (`found` = publicado y
  visible, `reunited` = ya volvió a casa). Importar una mascota perdida como
  encontrada llenaría el cruce de falsos positivos y mandaría a una familia a
  buscar donde no es.
* **`status='reunited'`** entra como `estado='reunida'`: ya no se ofrece como
  coincidencia, pero queda el registro.
* **El teléfono llega enmascarado** (`311****46`) y no sirve para llamar. Como
  en el otro importador, `contacto_telefono` queda NULL y el contacto se
  resuelve mandando a la plataforma de origen.
* **`origen_url` es la home** (o la ciudad): su SPA no expone una URL por
  mascota, así que no hay una ficha a la que enlazar. Va con el nombre del
  origen para que la persona sepa dónde buscar.
* **User-Agent identificable**: su CloudFront rechaza clientes sin UA de
  navegador (403). Se usa un UA que dice quiénes somos y cómo contactarnos, en
  formato compatible; no se finge ser un navegador anónimo. El sitio no publica
  `robots.txt` (devuelve 403 de S3: no existe), así que no hay directivas que
  respetar más allá de ir despacio y de a una petición.

Uso local:
    docker compose -p wati exec -T backend python \
        scripts/import_patitasacasa.py --dry-run
    docker compose -p wati exec -T backend python scripts/import_patitasacasa.py

ENV / flags:
    PAC_DESDE     (--desde)    solo reportes desde esta fecha    [2026-08-10]
    PAC_DRY_RUN=1 (--dry-run)  muestra el mapeo sin escribir
    PAC_CIUDADES  (--ciudades) lista separada por comas          [todas]
    PAC_PAUSA     (--pausa)    segundos entre requests           [1.0]
    PAC_SIN_FOTOS=1            no descarga imágenes
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

import requests

from .. import models
from ..database import SessionLocal
from . import mascotas as svc

logger = logging.getLogger(__name__)

BASE = "https://patitasacasa.com"
API = f"{BASE}/prod"
SOURCE = "patitasacasa"

# Su WAF bloquea clientes sin UA de navegador; este se identifica igual.
USER_AGENT = (
    "Mozilla/5.0 (compatible; GlomaMascotasBot/1.0; "
    "+https://mascotasperdidascolombia.com)"
)
TIMEOUT = 30
PAUSA_DEFAULT = 1.0
DESDE_DEFAULT = "2026-08-10"
LIMITE_POR_CIUDAD = 100

# Ciudades que su propio frontend declara (config.js). Si abren una nueva, se
# agrega aquí; pedir una que no existe simplemente devuelve una lista vacía.
CIUDADES = (
    "cali", "palmira", "buenaventura", "tulua", "roldanillo", "versalles",
    "medellin", "envigado", "itagui", "sabaneta", "manizales", "pereira",
    "armenia", "quibdo",
)

# Su `report_type` es el que define nuestro tipo de reporte.
TIPOS = {
    "lost": models.MASCOTA_TIPO_PERDIDA,
    "found": models.MASCOTA_TIPO_ENCONTRADA,
}

MAX_FOTO_BYTES = 8 * 1024 * 1024


def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def _texto(valor: Any, limite: int) -> Optional[str]:
    if valor is None:
        return None
    limpio = " ".join(str(valor).split()).strip()
    return limpio[:limite] or None


def _fecha(valor: Any) -> Optional[date]:
    texto = _texto(valor, 32)
    if not texto:
        return None
    return svc._parse_fecha(texto[:10])


def _ubicacion(pet: Dict[str, Any]) -> str:
    """Dónde se perdió o dónde fue vista. Es obligatoria en nuestro esquema."""
    zona = _texto(pet.get("zone"), 200)
    ciudad = _texto(pet.get("city"), 60)
    if ciudad:
        ciudad = ciudad.capitalize()
    partes = [p for p in (zona, ciudad) if p]
    return ", ".join(partes)[:255] or "Sin ubicación precisa"


def _senas(pet: Dict[str, Any]) -> Optional[str]:
    """Señas y comentarios: lo que más ayuda a reconocer al animal."""
    partes = [
        _texto(pet.get("distinctive_features"), 900),
        _texto(pet.get("description"), 900),
    ]
    return " · ".join(p for p in partes if p)[:2000] or None


def _notas(pet: Dict[str, Any]) -> str:
    """Rastro del origen. El teléfono viene enmascarado y se guarda como
    referencia (no sirve para llamar, pero ayuda a cruzar con la plataforma)."""
    lineas = [f"Importado de Patitas a Casa (id {pet.get('pet_id')})."]
    if pet.get("whatsapp_masked"):
        lineas.append(f"WhatsApp en el origen: {pet['whatsapp_masked']} (enmascarado).")
    if pet.get("status") == "reunited":
        lineas.append("En el origen figura como ya reunida con su familia.")
    return " ".join(lineas)[:2000]


def _mapear(pet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convierte un reporte del origen en nuestro dict de campos."""
    tipo = TIPOS.get((pet.get("report_type") or "").lower())
    if tipo is None:
        return None

    ciudad = _texto(pet.get("city"), 60)
    return {
        "tipo_registro": tipo,
        "especie": pet.get("animal_type"),
        "raza": _texto(pet.get("breed"), 80),
        "color": _texto(pet.get("color"), 80),
        "nombre": _texto(pet.get("pet_name"), 80),
        "sexo": pet.get("sex"),
        "tamano": _texto(pet.get("size"), 24),
        "senas": _senas(pet),
        "ubicacion": _ubicacion(pet),
        "barrio": _texto(pet.get("zone"), 120) or (ciudad.capitalize() if ciudad else None),
        "fecha_evento": (_fecha(pet.get("date_event")) or _fecha(pet.get("created_at"))),
        "notas": _notas(pet),
        "origen_id": _texto(pet.get("pet_id"), 120),
        # Su SPA no tiene URL por mascota: se enlaza la ciudad.
        "origen_url": f"{BASE}/?city={ciudad}" if ciudad else BASE,
    }


def _bajar_foto(sesion: requests.Session, ruta: str) -> Optional[tuple]:
    """Descarga una foto del origen. Devuelve (bytes, content_type) o None."""
    url = ruta if ruta.startswith("http") else f"{BASE}{ruta}"
    try:
        resp = sesion.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception:
        logger.warning("no se pudo bajar la foto %s", url)
        return None
    if len(resp.content) > MAX_FOTO_BYTES:
        logger.warning("foto demasiado grande, se omite: %s", url)
        return None
    tipo = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipo not in svc.ALLOWED_IMAGE_TYPES:
        tipo = "image/jpeg"
    return resp.content, tipo


def _existente(db, origen_id: str):
    return (
        db.query(models.Mascota)
        .filter(
            models.Mascota.source == SOURCE,
            models.Mascota.origen_id == origen_id,
        )
        .first()
    )


def sincronizar(
    db=None,
    desde: Optional[date] = None,
    dry_run: bool = False,
    progreso: Optional[Callable[[Dict[str, int]], None]] = None,
    ciudades: Optional[List[str]] = None,
    pausa: float = PAUSA_DEFAULT,
    sin_fotos: bool = False,
) -> Dict[str, int]:
    """Trae los reportes del origen. Mismo contrato que `mascotasporcolombia`.

    Claves del resultado: vistas, filtradas, creadas, actualizadas, sin_cambios,
    fallidas, perdidas, encontradas, fotos.
    """
    if desde is None:
        desde = svc._parse_fecha(os.getenv("PAC_DESDE") or DESDE_DEFAULT) or date(2026, 8, 10)
    if ciudades is None:
        crudas = os.getenv("PAC_CIUDADES") or ""
        ciudades = [c.strip() for c in crudas.split(",") if c.strip()] or list(CIUDADES)
    sin_fotos = sin_fotos or os.getenv("PAC_SIN_FOTOS") == "1"
    pausa = max(0.5, pausa)

    conteo = {
        "vistas": 0, "filtradas": 0, "creadas": 0, "actualizadas": 0,
        "sin_cambios": 0, "fallidas": 0, "perdidas": 0, "encontradas": 0,
        "fotos": 0,
    }

    sesion = _sesion()
    propia = db is None
    db = db or SessionLocal()
    try:
        for ciudad in ciudades:
            try:
                resp = sesion.get(
                    f"{API}/pets/{ciudad}", params={"limit": LIMITE_POR_CIUDAD},
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                pets = resp.json().get("pets") or []
            except Exception:
                logger.warning("no se pudo consultar la ciudad %r", ciudad)
                conteo["fallidas"] += 1
                continue
            finally:
                time.sleep(pausa)

            logger.info("patitasacasa: %s reportes en %s", len(pets), ciudad)
            for pet in pets:
                conteo["vistas"] += 1
                if progreso is not None and conteo["vistas"] % 5 == 0:
                    try:
                        progreso({k: conteo[k] for k in
                                  ("vistas", "creadas", "actualizadas", "fallidas")})
                    except Exception:
                        logger.debug("no se pudo reportar el avance", exc_info=True)

                creada = _fecha(pet.get("created_at"))
                if creada and creada < desde:
                    conteo["filtradas"] += 1
                    continue

                campos = _mapear(pet)
                if campos is None or not campos.get("origen_id"):
                    conteo["fallidas"] += 1
                    continue

                # `status='reunited'` en el origen = ya volvió a casa.
                estado = (
                    models.MASCOTA_ESTADO_REUNIDA
                    if (pet.get("status") or "").lower() == "reunited"
                    else models.MASCOTA_ESTADO_ACTIVO
                )

                existente = _existente(db, campos["origen_id"])
                if existente is not None:
                    cambios = []
                    for campo in ("raza", "color", "nombre", "tamano", "senas",
                                  "ubicacion", "barrio", "notas", "origen_url"):
                        valor = campos.get(campo)
                        if valor and getattr(existente, campo) != valor:
                            if not dry_run:
                                setattr(existente, campo, valor)
                            cambios.append(campo)
                    if existente.estado != estado and existente.estado != models.MASCOTA_ESTADO_CERRADO:
                        if not dry_run:
                            existente.estado = estado
                        cambios.append("estado")
                    if cambios:
                        if not dry_run:
                            existente.updated_at = datetime.utcnow()
                            db.commit()
                        conteo["actualizadas"] += 1
                    else:
                        conteo["sin_cambios"] += 1
                    continue

                if dry_run:
                    conteo["creadas"] += 1
                    conteo["perdidas" if campos["tipo_registro"] == "perdida"
                           else "encontradas"] += 1
                    logger.info(
                        "[CREARÍA] %s %s/%s color=%r zona=%r",
                        campos["tipo_registro"], campos["especie"],
                        campos.get("raza") or "-", campos.get("color"),
                        campos.get("barrio"),
                    )
                    continue

                mascota, problema = svc.crear_reporte(db, campos, source=SOURCE)
                if mascota is None:
                    logger.warning("rechazado %s: %s", campos["origen_id"], problema)
                    conteo["fallidas"] += 1
                    continue
                if estado != models.MASCOTA_ESTADO_ACTIVO:
                    mascota.estado = estado
                    db.commit()

                conteo["creadas"] += 1
                conteo["perdidas" if campos["tipo_registro"] == "perdida"
                       else "encontradas"] += 1

                # Las fotos sí se copian: sin ficha propia en el origen, esta es
                # la única forma de que la persona vea al animal.
                if not sin_fotos and pet.get("photo_url"):
                    time.sleep(pausa)
                    bajada = _bajar_foto(sesion, pet["photo_url"])
                    if bajada is not None:
                        datos, tipo_mime = bajada
                        try:
                            svc.guardar_foto(db, datos, tipo_mime, mascota=mascota)
                            conteo["fotos"] += 1
                        except Exception:
                            logger.exception("no se pudo guardar la foto de %s",
                                             mascota.codigo)
    finally:
        if propia:
            db.close()

    logger.info("patitasacasa: %s", conteo)
    return conteo
