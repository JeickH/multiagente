"""Genera la documentación de la base leyendo la base de verdad.

Produce `esquema.sql`, `diccionario_datos.md` e `index.html` a partir del
`information_schema` de la BD local, más las descripciones de este archivo (el
significado de un campo no está en el catálogo de Postgres; hay que escribirlo).

Se genera en vez de escribirse a mano para que no se desactualice en silencio:
si alguien agrega una columna y no la documenta, aparece igual en las tablas
con la descripción vacía, y se nota.

    source /opt/anaconda3/etc/profile.d/conda.sh && conda activate multiagente
    python documentacion_bd/generar.py

Lee la base local por `docker compose exec` porque el Postgres del host tapa al
del contenedor (gotcha conocido del proyecto).
"""
from __future__ import annotations

import html
import os
import subprocess
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
TABLAS = ("mascotas", "mascota_fotos", "mascota_coincidencias")

# Qué significa cada campo. Lo que el catálogo de Postgres no puede saber.
# (grupo, descripción). El grupo ordena las tablas del diccionario.
DESCRIPCIONES = {
    "mascotas": {
        "id": ("Identidad", "Clave primaria."),
        "codigo": ("Identidad", "Identificador legible que ve el ciudadano (`MC-00042`) y que nombra la carpeta de fotos en el storage. Se deriva del `id` al crear."),
        "tipo_registro": ("Identidad", "`perdida` (una familia la busca) o `encontrada` (alguien la tiene o la vio). El cruce siempre compara una contra la otra."),
        "estado": ("Identidad", "`activo` · `reconocida` (alguien dijo en el chat que es suya, falta confirmar) · `reunida` · `cerrado`."),
        "source": ("Identidad", "De dónde salió el reporte. `web` es nuestro bot; el resto son fuentes externas. Permite deshacer un lote entero."),
        "bot_id": ("Identidad", "Bot que creó el reporte, si entró por chat."),
        "especie": ("Animal", "`perro`, `gato` u `otra`. **Es el único filtro duro del cruce**: nada más descarta un candidato."),
        "especie_otra": ("Animal", "Qué animal es cuando `especie = otra`."),
        "raza": ("Animal", "Peso 5 en el cruce. Los sinónimos se colapsan antes de comparar (criollo = mestizo = callejero)."),
        "color": ("Animal", "Peso 5 en el cruce, empatado con la raza: es lo que de verdad identifica a un animal en la calle."),
        "nombre": ("Animal", "**Peso 1, el más bajo.** Quien encuentra un animal en la calle no sabe cómo se llama."),
        "sexo": ("Animal", "`macho`, `hembra` o `desconocido`. `desconocido` **no puntúa** en el cruce."),
        "edad": ("Animal", "Texto libre: «2 años», «cachorro»."),
        "tamano": ("Animal", "`pequeño`, `mediano` o `grande`. Peso 3."),
        "senas": ("Animal", "Señas particulares: «collar azul», «mancha en la pata». Aporta hasta 5 puntos. **Nunca puede contener un teléfono** (ver la nota de guardarraíl)."),
        "ubicacion": ("Dónde", "**Obligatoria.** Dónde se perdió, o dónde está ahora la encontrada. El link de Maps es opcional a propósito: mucha gente sabe dar la dirección pero no compartir una ubicación."),
        "barrio": ("Dónde", "La zona fina, que es la que puntúa en el cruce (peso 2). **No descarta**: el animal camina, y quien lo encuentra reporta dónde está, no dónde se perdió."),
        "ciudad": ("Dónde", "Municipio. Las zonas genéricas (`Cali`, `Valle`) **no puntúan** en el cruce: las trae casi todo reporte importado e inflaban cualquier par."),
        "departamento": ("Dónde", "Departamento. Hoy solo lo publican PetSearch y Protección Animal."),
        "maps_url": ("Dónde", "Enlace de Google Maps, cuando la persona lo compartió."),
        "contacto_nombre": ("Contacto (PII)", "A nombre de quién está el teléfono. Puede llevar dos, separados por `/`, cuando el animal está en hogar de paso."),
        "contacto_telefono": ("Contacto (PII)", "**Solo se entrega cuando la persona confirma que reconoce a la mascota.** Admite uno o dos números separados por `/`: la fundación y la casa donde duerme el animal."),
        "rescatado_por": ("Contacto (PII)", "Quién llevó el animal al refugio. Es una tercera persona: quien lo recogió de la calle no siempre es quien lo cuida."),
        "rescatado_por_telefono": ("Contacto (PII)", "Teléfono de esa persona. No lo entrega el bot."),
        "esterilizado": ("Salud", "Tri-estado: NULL = la fuente no lo dice, que no es lo mismo que `false`."),
        "vacunado": ("Salud", "Tri-estado. Hoy solo lo publica Protección Animal."),
        "desparasitado": ("Salud", "Tri-estado. Hoy solo lo publica Protección Animal."),
        "peso_kg": ("Salud", "En kilos. Se descarta el 0 al importar: varias fuentes lo usan como «sin dato» y un animal de 0 kg no existe."),
        "salud": ("Salud", "Lesiones o estado reportado, en texto corto."),
        "resguardo": ("Salud", "Dónde está durmiendo hoy: `hospital` · `hogar_de_paso` · `albergue` · `con_quien_la_encontro` · `en_la_calle` · `con_su_familia`. **Sin CHECK a propósito**: lo alimentan fuentes externas y una restricción rompería un importador cada vez que aparezca un valor nuevo."),
        "resguardo_nombre": ("Salud", "Nombre del hogar de paso o del albergue."),
        "recompensa": ("Salud", "Si la familia ofrece recompensa. Lo publica Mascotas por Colombia."),
        "origen_url": ("Origen", "Ficha original en la plataforma de donde vino. **Es la vía de contacto** cuando la fuente no publica teléfono."),
        "origen_id": ("Origen", "Identificador en el sitio de origen. Junto con `source` forma la clave única que hace idempotentes a los importadores."),
        "estado_origen": ("Origen", "El estado tal como lo escribe la fuente («DISPONIBLE (ADAPTACIÓN)», «stray», «Perdido»). No se traduce: sirve para auditar de dónde salió nuestro `tipo_registro` cuando hubo que deducirlo."),
        "publicado_origen_at": ("Origen", "Cuándo lo publicó la fuente. Distinto de `created_at`, que es cuándo lo trajimos nosotros."),
        "sincronizado_at": ("Origen", "Última vez que vimos este reporte en su fuente."),
        "fecha_evento": ("Ciclo de vida", "Cuándo se perdió o se encontró."),
        "notas": ("Ciclo de vida", "Contexto que no tiene columna propia. **Nunca puede contener un teléfono.**"),
        "reconocida_at": ("Ciclo de vida", "Cuándo alguien dijo en el chat que reconocía a esta mascota (el momento en que el bot entregó el contacto). Sirve para saber a quién llamar."),
        "reconocida_chat": ("Ciclo de vida", "Desde qué conversación se reconoció."),
        "created_at": ("Ciclo de vida", "Cuándo entró a nuestra base."),
        "updated_at": ("Ciclo de vida", "Última modificación."),
    },
    "mascota_fotos": {
        "id": ("", "Clave primaria."),
        "mascota_id": ("", "NULL mientras la foto está en el limbo: el ciudadano suele mandar las fotos ANTES de que el bot termine de recoger los datos."),
        "upload_session": ("", "uuid efímero del chat contra el que se subió la foto, hasta que el reporte se crea y la adopta."),
        "storage_key": ("", "Ruta en el storage: `mascotas/<codigo>/<uuid>.jpg`. **El mismo layout en S3 y en `media_local/`**, para que las claves de la BD sirvan en los dos entornos."),
        "content_type": ("", "Tipo MIME. Se acepta jpeg, png, webp y heic."),
        "bytes_size": ("", "Peso actual, ya comprimido."),
        "optimizada": ("", "Si ya pasó por la compresión. Evita reprocesarla."),
        "optimizada_at": ("", "Cuándo se comprimió."),
        "bytes_original": ("", "Lo que pesaba antes de comprimir."),
        "created_at": ("", "Cuándo se subió."),
    },
    "mascota_coincidencias": {
        "id": ("", "Clave primaria."),
        "perdida_id": ("", "El reporte de la familia que busca."),
        "encontrada_id": ("", "El reporte de quien la tiene o la vio."),
        "score": ("", "Suma del scoring campo a campo. Umbral 12 en el cruce diario; 3 en la búsqueda en vivo."),
        "detalle": ("", "JSONB con qué campos coincidieron y cuánto aportó cada uno, para que el panel lo muestre."),
        "estado": ("", "`nueva` · `revisada` · `confirmada` · `descartada`. Las descartadas quedan **archivadas** (ocultas con un botón para verlas), no se borran."),
        "notas": ("", "Lo que anota el equipo al revisar el par."),
        "created_at": ("", "Cuándo la detectó el cruce."),
        "updated_at": ("", "Última vez que alguien la tocó desde el panel."),
    },
}

NOTAS_TABLA = {
    "mascotas": [
        ("Un teléfono en `senas` o `notas` deja mudo al bot",
         "El guardarraíl <code>llm_engine._viola_contacto</code> descarta el turno completo si el bot "
         "escribe un número que no vino de <code>entregar_contacto</code>. Es lo que impide que un "
         "modelo pequeño «recuerde» un teléfono plausible y mande a una familia angustiada a marcar "
         "un número equivocado. Por eso todo importador borra los números del texto libre."),
        ("Teléfono <b>u</b> <code>origen_url</code>, uno de los dos",
         "Se valida en <code>services/mascotas</code>, no en la base: el motivo es de negocio, no de "
         "integridad referencial. Un reporte sin ninguna vía de contacto no sirve para reunir a nadie."),
        ("<code>UNIQUE (source, origen_id)</code> es lo que hace idempotentes a los importadores",
         "Re-correr una fuente no duplica nada: en la revisión solo aparece lo que todavía no está."),
    ],
    "mascota_fotos": [
        ("El bucket no tiene versionado",
         "Lo que se borra, se pierde. Ya costó fotos irrecuperables una vez. Antes de cualquier "
         "borrado: preguntar y sacar respaldo."),
    ],
    "mascota_coincidencias": [
        ("El cruce automático está pausado",
         "EventBridge <code>mascotas-cruce-diario</code> en DISABLED, por decisión del CEO. "
         "El botón «🔗 Buscar coincidencias» del panel sí funciona."),
    ],
}


def consultar(sql: str) -> list[list[str]]:
    salida = subprocess.run(
        ["docker", "compose", "-p", "wati", "exec", "-T", "db", "psql",
         "-U", os.getenv("POSTGRES_USER", "equipo"),
         "-d", os.getenv("POSTGRES_DB", "multiagente_db"), "-tAF|", "-c", sql],
        capture_output=True, text=True, timeout=60, check=True, cwd=os.path.dirname(BASE),
    ).stdout
    return [l.split("|") for l in salida.splitlines() if l.strip()]


def columnas(tabla: str):
    return consultar(f"""
        SELECT column_name, data_type,
               coalesce(character_maximum_length::text, numeric_precision::text, ''),
               is_nullable, coalesce(column_default, '')
        FROM information_schema.columns WHERE table_name = '{tabla}'
        ORDER BY ordinal_position;""")


def indices(tabla: str):
    return consultar(
        f"SELECT indexname, indexdef FROM pg_indexes WHERE tablename = '{tabla}' "
        f"ORDER BY indexname;")


def restricciones(tabla: str):
    return consultar(f"""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint WHERE conrelid = '{tabla}'::regclass ORDER BY conname;""")


def tipo_sql(fila) -> str:
    nombre, tipo, largo, _, _ = fila
    corto = {"character varying": "varchar", "timestamp without time zone": "timestamp",
             "double precision": "float"}.get(tipo, tipo)
    if largo and corto in ("varchar", "numeric"):
        return f"{corto}({largo})"
    return corto


# ---------------------------------------------------------------------------

def escribir_sql() -> None:
    partes = [
        "-- Esquema de referencia del módulo Recupera Tu Mascota.",
        f"-- Generado por documentacion_bd/generar.py el {datetime.now():%Y-%m-%d %H:%M}.",
        "-- NO es la fuente de verdad: eso es backend/app/models.py. Sirve para montar",
        "-- un entorno nuevo o comparar dos entornos a ojo.",
        "",
    ]
    for tabla in TABLAS:
        partes.append(f"CREATE TABLE {tabla} (")
        campos = []
        for fila in columnas(tabla):
            nombre, _, _, nullable, default = fila
            linea = f"    {nombre} {tipo_sql(fila)}"
            if nullable == "NO":
                linea += " NOT NULL"
            if default and "nextval" not in default:
                linea += f" DEFAULT {default}"
            campos.append(linea)
        partes.append(",\n".join(campos))
        partes.append(");")
        for nombre, definicion in restricciones(tabla):
            if not nombre.endswith("_pkey"):
                partes.append(f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} {definicion};")
        for nombre, definicion in indices(tabla):
            if not nombre.endswith("_pkey"):
                partes.append(f"{definicion};")
        partes.append("")
    with open(os.path.join(BASE, "esquema.sql"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(partes))


def escribir_diccionario() -> None:
    partes = [
        "# Diccionario de datos",
        "",
        "> Generado por `documentacion_bd/generar.py` leyendo la base local el "
        f"{datetime.now():%Y-%m-%d}. La fuente de verdad del esquema es "
        "`backend/app/models.py`.",
        "",
        "Qué fuente llena cada campo está en [`mapeo_fuentes.md`](mapeo_fuentes.md).",
        "",
    ]
    for tabla in TABLAS:
        partes += [f"## `{tabla}`", ""]
        for titulo, cuerpo in NOTAS_TABLA.get(tabla, []):
            texto = cuerpo.replace("<code>", "`").replace("</code>", "`")
            texto = texto.replace("<b>", "**").replace("</b>", "**")
            partes += [f"> **{titulo}**  ", f"> {texto}", ""]
        partes += ["| Columna | Tipo | Nulo | Qué es |", "|---|---|:--:|---|"]
        for fila in columnas(tabla):
            nombre, _, _, nullable, _ = fila
            _, desc = DESCRIPCIONES.get(tabla, {}).get(nombre, ("", "—"))
            partes.append(
                f"| `{nombre}` | {tipo_sql(fila)} | {'sí' if nullable == 'YES' else 'no'} | {desc} |")
        partes.append("")
        idx = [(n, d) for n, d in indices(tabla) if not n.endswith("_pkey")]
        if idx:
            partes += ["**Índices**", ""]
            partes += [f"- `{n}` — `{d.split('USING')[-1].strip()}`" for n, d in idx]
            partes.append("")
    with open(os.path.join(BASE, "diccionario_datos.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(partes))


def escribir_html() -> None:
    from plantilla_html import render          # noqa: E402

    datos = {}
    for tabla in TABLAS:
        cols = []
        for fila in columnas(tabla):
            nombre, _, _, nullable, _ = fila
            grupo, desc = DESCRIPCIONES.get(tabla, {}).get(nombre, ("", ""))
            cols.append({"nombre": nombre, "tipo": tipo_sql(fila),
                         "nulo": nullable == "YES", "grupo": grupo, "desc": desc})
        datos[tabla] = {
            "columnas": cols,
            "indices": [(n, d) for n, d in indices(tabla) if not n.endswith("_pkey")],
            "restricciones": [(n, d) for n, d in restricciones(tabla)
                              if not n.endswith("_pkey")],
            "notas": NOTAS_TABLA.get(tabla, []),
        }
    filas = consultar(
        "SELECT source, tipo_registro, count(*) FROM mascotas GROUP BY 1,2 ORDER BY 1,2;")
    with open(os.path.join(BASE, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(render(datos, filas, html.escape))


def main() -> None:
    import sys
    sys.path.insert(0, BASE)
    escribir_sql()
    print("esquema.sql")
    escribir_diccionario()
    print("diccionario_datos.md")
    escribir_html()
    print("index.html")
    total = sum(len(columnas(t)) for t in TABLAS)
    print(f"\n{len(TABLAS)} tablas, {total} columnas documentadas")
    sin_desc = [
        f"{t}.{c[0]}" for t in TABLAS for c in columnas(t)
        if c[0] not in DESCRIPCIONES.get(t, {})
    ]
    if sin_desc:
        print(f"⚠ columnas sin descripción ({len(sin_desc)}): {', '.join(sin_desc)}")
        print("  agrégalas a DESCRIPCIONES en este archivo.")


if __name__ == "__main__":
    main()
