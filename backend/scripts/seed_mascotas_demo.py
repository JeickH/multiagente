"""Datos de prueba del sprint "Ayuda a Cali": reportes de mascotas con fotos.

Carga un set realista de reportes de Cali (perdidas y encontradas) con fotos
descargadas de servicios públicos de imágenes de prueba (placedog.net y
cataas.com). Incluye **tres pares diseñados para coincidir** — así el cruce
diario y la búsqueda del bot se pueden verificar de verdad:

  1. Canela  → labrador café perdido en San Fernando / encontrado en San Fernando.
  2. Michi   → gato gris atigrado perdido en Ciudad Jardín / hallado ahí mismo.
  3. Rocky   → criollo negro con mancha blanca, Comuna 18.

Idempotente por `source='demo'`: cada corrida borra los reportes de demo
anteriores (y sus fotos) antes de crear los nuevos. Los reportes reales
(`source='web'`) NO se tocan nunca.

Uso:
    docker compose -p wati exec -T backend python scripts/seed_mascotas_demo.py

ENV opcionales:
    MASCOTAS_DEMO_SIN_FOTOS=1   → no descarga imágenes (útil sin salida a internet)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import models  # type: ignore
from app.services import mascotas as svc  # type: ignore


SOURCE = "demo"
SIN_FOTOS = os.getenv("MASCOTAS_DEMO_SIN_FOTOS") == "1"

# (datos del reporte, urls de fotos de prueba)
REPORTES = [
    # --- Par 1: Canela, labrador café -------------------------------------
    (
        {
            "tipo_registro": "perdida",
            "especie": "perro", "raza": "Labrador", "color": "café claro",
            "nombre": "Canela", "sexo": "hembra", "edad": "3 años",
            "tamano": "grande",
            "senas": "Collar rojo con placa, una mancha blanca en el pecho",
            "ubicacion": "Barrio San Fernando, cerca de la Calle 5 con Carrera 39",
            "barrio": "San Fernando",
            "maps_url": "https://maps.google.com/?q=3.4207,-76.5450",
            "contacto_nombre": "Marcela Ríos", "contacto_telefono": "+57 320 415 9087",
            "dias_atras": 6,
            "notas": "Se salió cuando abrieron el portón tras la réplica del sismo.",
        },
        ["https://placedog.net/500/400?id=90"],
    ),
    (
        {
            "tipo_registro": "encontrada",
            "especie": "perro", "raza": "Labrador", "color": "café",
            "sexo": "hembra", "edad": "adulta", "tamano": "grande",
            "senas": "Tenía collar rojo sin placa, mancha blanca en el pecho",
            "ubicacion": "Parque de San Fernando, frente a la panadería",
            "barrio": "San Fernando",
            "maps_url": "https://maps.google.com/?q=3.4198,-76.5462",
            "contacto_nombre": "Julián Ospina", "contacto_telefono": "+57 315 802 4471",
            "dias_atras": 4,
            "notas": "Está en mi casa, es muy mansa y sabe dar la pata.",
        },
        ["https://placedog.net/500/400?id=91"],
    ),
    # --- Par 2: Michi, gato gris ------------------------------------------
    (
        {
            "tipo_registro": "perdida",
            "especie": "gato", "raza": "criollo", "color": "gris atigrado",
            "nombre": "Michi", "sexo": "macho", "edad": "2 años",
            "tamano": "mediano",
            "senas": "Tiene la punta de la cola blanca y una oreja mordida",
            "ubicacion": "Ciudad Jardín, Calle 16 con Carrera 100",
            "barrio": "Ciudad Jardín",
            "contacto_nombre": "Andrés Valencia", "contacto_telefono": "+57 301 774 5512",
            "dias_atras": 9,
        },
        ["https://cataas.com/cat?width=500&height=400"],
    ),
    (
        {
            "tipo_registro": "encontrada",
            "especie": "gato", "color": "gris con rayas", "sexo": "macho",
            "tamano": "mediano",
            "senas": "La cola termina en blanco, una oreja partida",
            "ubicacion": "Conjunto residencial en Ciudad Jardín, Carrera 101",
            "barrio": "Ciudad Jardín",
            "contacto_nombre": "Portería Torre 3", "contacto_telefono": "+57 602 555 3311",
            "dias_atras": 3,
            "notas": "Lleva días en el parqueadero, los vecinos le dan comida.",
        },
        ["https://cataas.com/cat?width=500&height=401"],
    ),
    # --- Par 3: Rocky, criollo negro --------------------------------------
    (
        {
            "tipo_registro": "perdida",
            "especie": "perro", "raza": "criollo", "color": "negro",
            "nombre": "Rocky", "sexo": "macho", "edad": "5 años",
            "tamano": "mediano",
            "senas": "Mancha blanca en el pecho, cojea de la pata trasera izquierda",
            "ubicacion": "Comuna 18, sector Meléndez, subida a Los Chorros",
            "barrio": "Meléndez",
            "contacto_nombre": "Fabián Cortés", "contacto_telefono": "+57 312 660 2298",
            "dias_atras": 12,
        },
        ["https://placedog.net/500/400?id=120"],
    ),
    (
        {
            "tipo_registro": "encontrada",
            "especie": "perro", "color": "negro con blanco", "sexo": "macho",
            "tamano": "mediano",
            "senas": "Mancha blanca en el pecho, cojea de una pata de atrás",
            "ubicacion": "Meléndez, cerca de la iglesia de la Comuna 18",
            "barrio": "Meléndez",
            "contacto_nombre": "Luz Dary Muñoz", "contacto_telefono": "+57 318 209 7733",
            "dias_atras": 2,
        },
        ["https://placedog.net/500/400?id=121"],
    ),
    # --- Reportes sueltos (sin par): dan volumen realista al listado -------
    (
        {
            "tipo_registro": "encontrada",
            "especie": "perro", "raza": "Pincher", "color": "negro y café",
            "sexo": "macho", "tamano": "pequeño",
            "senas": "Muy nervioso, sin collar",
            "ubicacion": "Avenida Roosevelt con Carrera 44, frente al CAI",
            "barrio": "Tequendama",
            "contacto_nombre": "Sandra Loaiza", "contacto_telefono": "+57 316 445 1120",
            "dias_atras": 1,
        },
        ["https://placedog.net/500/400?id=55"],
    ),
    (
        {
            "tipo_registro": "perdida",
            "especie": "gato", "color": "blanco con naranja", "nombre": "Nube",
            "sexo": "hembra", "edad": "1 año", "tamano": "pequeño",
            "senas": "Ojos de distinto color",
            "ubicacion": "Barrio Granada, Calle 15 Norte",
            "barrio": "Granada",
            "contacto_nombre": "Paola Zapata", "contacto_telefono": "+57 314 998 0021",
            "dias_atras": 5,
        },
        ["https://cataas.com/cat?width=500&height=402"],
    ),
    (
        {
            "tipo_registro": "encontrada",
            "especie": "otra", "especie_otra": "conejo", "color": "blanco",
            "tamano": "pequeño",
            "senas": "Apareció en el antejardín después del temblor",
            "ubicacion": "Barrio El Refugio, Carrera 66 con Calle 13",
            "barrio": "El Refugio",
            "contacto_nombre": "Camilo Herrera", "contacto_telefono": "+57 300 118 4402",
            "dias_atras": 7,
        },
        [],
    ),
    (
        {
            "tipo_registro": "perdida",
            "especie": "perro", "raza": "Golden Retriever", "color": "dorado",
            "nombre": "Simba", "sexo": "macho", "edad": "7 años",
            "tamano": "grande",
            "senas": "Lleva pañoleta azul, es sordo de un oído",
            "ubicacion": "Pance, vía al río, cerca del parqueadero principal",
            "barrio": "Pance",
            "maps_url": "https://maps.google.com/?q=3.3315,-76.5407",
            "contacto_nombre": "Diana Bermúdez", "contacto_telefono": "+57 311 507 6689",
            "dias_atras": 3,
        },
        ["https://placedog.net/500/400?id=200"],
    ),
]


def _descargar(url: str) -> tuple[bytes, str] | None:
    import requests

    try:
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
    except Exception as exc:   # sin salida a internet el seed sigue sin fotos
        print(f"  !! no se pudo descargar {url}: {type(exc).__name__}")
        return None
    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
    if content_type not in svc.ALLOWED_IMAGE_TYPES:
        content_type = "image/jpeg"
    return resp.content, content_type


def _borrar_demo(db) -> int:
    previos = (
        db.query(models.Mascota).filter(models.Mascota.source == SOURCE).all()
    )
    for m in previos:
        db.delete(m)   # cascade borra sus fotos y coincidencias
    if previos:
        db.commit()
    return len(previos)


def main() -> int:
    db = SessionLocal()
    try:
        borrados = _borrar_demo(db)
        if borrados:
            print(f"OK: {borrados} reporte(s) de demo anteriores eliminados")

        bot = (
            db.query(models.Bot)
            .join(models.User, models.Bot.user_id == models.User.id)
            .filter(models.User.correo == "recuperatumascota@gmail.com")
            .order_by(models.Bot.id.desc())
            .first()
        )

        creados = 0
        for datos, urls in REPORTES:
            payload = dict(datos)
            dias = payload.pop("dias_atras", 0)
            payload["fecha_evento"] = (date.today() - timedelta(days=dias)).isoformat()

            mascota, problema = svc.crear_reporte(
                db, payload, bot_id=bot.id if bot else None, source=SOURCE,
            )
            if mascota is None:
                print(f"  !! reporte rechazado: {problema}")
                continue
            creados += 1

            fotos = 0
            if not SIN_FOTOS:
                for url in urls:
                    descargada = _descargar(url)
                    if descargada is None:
                        continue
                    data, content_type = descargada
                    svc.guardar_foto(db, data, content_type, mascota=mascota)
                    fotos += 1
            etiqueta = payload.get("nombre") or payload.get("raza") or payload["especie"]
            print(
                f"OK: {mascota.codigo} [{mascota.tipo_registro}] {etiqueta} "
                f"— {fotos} foto(s)"
            )

        print(f"\n{creados} reportes de demostración creados.")

        stats = svc.cruzar_reportes(db)
        print(
            f"Cruce ejecutado: {stats['nuevas']} coincidencia(s) nueva(s) sobre "
            f"{stats['pares_evaluados']} pares evaluados."
        )
        for c in svc.listar_coincidencias(db):
            print(
                f"  · {c.perdida.codigo} ({c.perdida.nombre or 's/n'}) ↔ "
                f"{c.encontrada.codigo}  score={c.score}  "
                f"campos={','.join((c.detalle or {}).keys())}"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
