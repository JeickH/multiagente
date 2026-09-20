"""El motor del importador de productos: comparar, mostrar y recién ahí cargar.

Tres piezas, en ese orden, y ninguna se salta:

    leer(archivo) -> Catalogo      la receta del cliente (covenas.py, …)
    comparar(actual, deseado)      qué entra, qué cambia, qué se retira
    [un humano mira el HTML]
    aplicar(db, …)                 escribe, y deja el rastro en bot_producto_cargas

Reglas que vienen del proyecto y no se negocian
-----------------------------------------------
1. **Nada se borra.** Lo que desaparece del archivo se marca `activo = false`.
   Ya se perdieron fotos irrecuperables por un borrado hecho sobre una
   interpretación (MANUAL_RECUPERA_TU_MASCOTA.md §1): acá la interpretación
   —"esta fila ya no está"— se muestra antes, y aun así no borra.
2. **La idempotencia es de la base, no del script.** Cada fila viaja con su
   `externo_id` y se busca por `(producto_id, variante_id, externo_id)`, que es
   el UNIQUE de la tabla. Cargar el mismo archivo dos veces no duplica nada
   porque la segunda vez encuentra la fila y la actualiza; si el script se
   equivocara y hiciera INSERT, el UNIQUE lo tumba. El centinela `variante_id =
   0` existe para que eso también funcione en las filas sin variante (NULL no
   es igual a NULL en un UNIQUE de Postgres).
3. **Revisión obligatoria.** `--cargar` exige el `pendiente.json` que dejó
   `--revisar`, con el hash del archivo revisado y el diff aprobado. Si el
   archivo cambió, o si la base cambió desde la revisión, se niega.

Por qué el registro en `bot_producto_cargas` se escribe al cargar y no al
revisar: `producto_id` es NOT NULL y un catálogo nuevo todavía no tiene
producto. La revisión vive en disco (igual que el `pendientes.json` de las
fuentes de mascotas) y la fila de la bitácora se escribe una sola vez, ya con
el resultado y con quién aprobó.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app import models

#: Campos que se comparan de cada cosa. Lo que no está acá no genera «cambiada»
#: (los `created_at`, los ids internos).
CAMPOS_PRODUCTO = (
    "tipo", "nombre", "estado", "resumen", "instrucciones", "atributos",
    "vigencia_desde", "vigencia_hasta",
)
CAMPOS_VARIANTE = ("nombre", "instrucciones", "atributos", "orden", "precios_de", "activo")
CAMPOS_FILA = ("tipo", "etiqueta", "inicio", "fin", "valores", "nota", "orden", "activo")
CAMPOS_MEDIO = ("variante", "url", "tipo", "descripcion", "aplica")


# ---------------------------------------------------------------------------
# La forma normalizada
# ---------------------------------------------------------------------------

@dataclass
class Variante:
    slug: str
    nombre: str
    orden: int = 0
    atributos: Dict[str, Any] = field(default_factory=dict)
    instrucciones: Optional[str] = None
    #: Slug de la variante de la que toma los precios ("bohios cobra lo de
    #: amor_de_dios"). Se resuelve a id al aplicar.
    precios_de: Optional[str] = None
    activo: bool = True


@dataclass
class Fila:
    #: Id de la fila en el archivo de origen. **Obligatorio**: es el candado.
    externo_id: str
    variante: Optional[str] = None      # slug; None = aplica a todas
    tipo: str = models.FILA_TIPO_PRECIO
    etiqueta: Optional[str] = None
    inicio: Optional[date] = None
    fin: Optional[date] = None
    valores: Dict[str, Any] = field(default_factory=dict)
    nota: Optional[str] = None
    orden: int = 0
    activo: bool = True


@dataclass
class Medio:
    clave: str
    url: str
    variante: Optional[str] = None
    tipo: str = "image"
    descripcion: Optional[str] = None
    aplica: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alias:
    alias: str
    nivel: str = models.ALIAS_NIVEL_PRODUCTO
    #: Slug de la variante cuando `nivel == 'variante'`.
    variante: Optional[str] = None


@dataclass
class Catalogo:
    """Un producto entero, tal como quedaría en la base."""

    slug: str
    nombre: str
    tipo: str = models.PRODUCTO_TIPO_PRODUCTO
    estado: str = models.PRODUCTO_ESTADO_BORRADOR
    resumen: Optional[str] = None
    instrucciones: Optional[str] = None
    atributos: Dict[str, Any] = field(default_factory=dict)
    vigencia_desde: Optional[date] = None
    vigencia_hasta: Optional[date] = None
    variantes: List[Variante] = field(default_factory=list)
    filas: List[Fila] = field(default_factory=list)
    medios: List[Medio] = field(default_factory=list)
    alias: List[Alias] = field(default_factory=list)

    def validar(self) -> None:
        """Lo que la base no puede atrapar sola, o atrapa demasiado tarde."""
        vistos = set()
        slugs = {v.slug for v in self.variantes}
        for f in self.filas:
            if not (f.externo_id or "").strip():
                raise ValueError(
                    "hay una fila sin `externo_id`: sin él la carga no es "
                    f"idempotente (etiqueta={f.etiqueta!r})"
                )
            clave = (f.variante or "", f.externo_id)
            if clave in vistos:
                raise ValueError(
                    f"`externo_id` repetido dentro del archivo: {clave!r}. "
                    "El UNIQUE de la tabla lo rechazaría a mitad de la carga."
                )
            vistos.add(clave)
            if f.variante and f.variante not in slugs:
                raise ValueError(f"la fila {f.externo_id!r} apunta a una variante que no existe: {f.variante!r}")
        for v in self.variantes:
            if v.precios_de and v.precios_de not in slugs:
                raise ValueError(f"{v.slug!r} toma precios de {v.precios_de!r}, que no existe")
        for m in self.medios:
            if m.variante and m.variante not in slugs:
                raise ValueError(f"el medio {m.clave!r} apunta a una variante que no existe: {m.variante!r}")
        for a in self.alias:
            if a.nivel == models.ALIAS_NIVEL_VARIANTE and a.variante not in slugs:
                raise ValueError(f"el alias {a.alias!r} apunta a una variante que no existe: {a.variante!r}")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def hash_archivo(ruta: str) -> str:
    """SHA-256 del archivo tal como está en disco.

    Es lo que amarra la revisión con la carga: si el CEO aprueba un diff y
    alguien cambia el Excel antes de cargarlo, el hash no coincide y el
    importador se niega.
    """
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _jsonable(valor: Any) -> Any:
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _jsonable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(v) for v in valor]
    return valor


def _fecha(valor: Any) -> Optional[date]:
    if valor is None or isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def _dict_fila(f: Fila) -> Dict[str, Any]:
    return {c: getattr(f, c) for c in CAMPOS_FILA}


def _dict_variante(v: Variante) -> Dict[str, Any]:
    return {c: getattr(v, c) for c in CAMPOS_VARIANTE}


def _dict_medio(m: Medio) -> Dict[str, Any]:
    return {c: getattr(m, c) for c in CAMPOS_MEDIO}


def _cambios(antes: Dict[str, Any], despues: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Campo por campo, solo lo que difiere. `{campo: [antes, después]}`."""
    return {
        c: [_jsonable(antes.get(c)), _jsonable(despues.get(c))]
        for c in despues
        if antes.get(c) != despues.get(c)
    }


# ---------------------------------------------------------------------------
# Leer lo que ya está en la base
# ---------------------------------------------------------------------------

def producto_de(db, *, team_id: int, slug: str) -> Optional[models.BotProducto]:
    return (
        db.query(models.BotProducto)
        .filter(models.BotProducto.team_id == team_id, models.BotProducto.slug == slug)
        .first()
    )


def estado_actual(db, *, team_id: int, slug: str) -> Optional[Catalogo]:
    """El producto que ya está en la base, en la misma forma que la receta.

    Con las dos en la misma forma, comparar es restar. `None` = no existe
    todavía y todo el archivo es nuevo.
    """
    producto = producto_de(db, team_id=team_id, slug=slug)
    if producto is None:
        return None

    variantes = (
        db.query(models.BotProductoVariante)
        .filter(models.BotProductoVariante.producto_id == producto.id)
        .all()
    )
    por_id = {v.id: v.slug for v in variantes}

    cat = Catalogo(
        slug=producto.slug,
        nombre=producto.nombre,
        tipo=producto.tipo,
        estado=producto.estado,
        resumen=producto.resumen,
        instrucciones=producto.instrucciones,
        atributos=producto.atributos or {},
        vigencia_desde=producto.vigencia_desde,
        vigencia_hasta=producto.vigencia_hasta,
        variantes=[
            Variante(
                slug=v.slug,
                nombre=v.nombre,
                orden=v.orden,
                atributos=v.atributos or {},
                instrucciones=v.instrucciones,
                precios_de=por_id.get(v.precios_de_variante_id),
                activo=bool(v.activo),
            )
            for v in sorted(variantes, key=lambda v: (v.orden, v.slug))
        ],
    )

    filas = (
        db.query(models.BotProductoFila)
        .filter(models.BotProductoFila.producto_id == producto.id)
        .all()
    )
    cat.filas = [
        Fila(
            externo_id=f.externo_id,
            variante=por_id.get(f.variante_id),
            tipo=f.tipo,
            etiqueta=f.etiqueta,
            inicio=f.inicio,
            fin=f.fin,
            valores=f.valores or {},
            nota=f.nota,
            orden=f.orden,
            activo=bool(f.activo),
        )
        for f in sorted(filas, key=lambda f: (f.orden, f.externo_id))
    ]

    medios = (
        db.query(models.BotProductoMedio)
        .filter(models.BotProductoMedio.producto_id == producto.id)
        .all()
    )
    cat.medios = [
        Medio(
            clave=m.clave,
            url=m.url,
            variante=por_id.get(m.variante_id),
            tipo=m.tipo,
            descripcion=m.descripcion,
            aplica=m.aplica or {},
        )
        for m in sorted(medios, key=lambda m: m.clave)
    ]

    alias = (
        db.query(models.BotProductoAlias)
        .filter(models.BotProductoAlias.producto_id == producto.id)
        .all()
    )
    cat.alias = [
        Alias(
            alias=a.alias,
            nivel=a.nivel,
            variante=por_id.get(a.ref_id) if a.nivel == models.ALIAS_NIVEL_VARIANTE else None,
        )
        for a in sorted(alias, key=lambda a: (a.nivel, a.alias))
    ]
    return cat


# ---------------------------------------------------------------------------
# Comparar
# ---------------------------------------------------------------------------

def comparar(actual: Optional[Catalogo], deseado: Catalogo) -> Dict[str, Any]:
    """Qué entra, qué cambia y qué se retira. No toca la base ni el catálogo.

    El resultado es JSON puro a propósito: es lo que se muestra en el HTML, lo
    que se guarda en `pendiente.json` y lo que queda en `bot_producto_cargas.diff`.
    """
    deseado.validar()
    diff: Dict[str, Any] = {
        "slug": deseado.slug,
        "producto": {},
        "variantes": {"nuevas": [], "cambiadas": [], "retiradas": []},
        "filas": {
            "nuevas": [], "cambiadas": [], "retiradas": [],
            "reactivadas": [], "reordenadas": [],
        },
        "medios": {"nuevos": [], "cambiados": [], "huerfanos": []},
        "alias": {"nuevos": [], "huerfanos": []},
    }

    # ── el producto ────────────────────────────────────────────────────────
    campos_deseados = {c: getattr(deseado, c) for c in CAMPOS_PRODUCTO}
    if actual is None:
        diff["producto"] = {"nuevo": True, "valores": _jsonable(campos_deseados)}
    else:
        diff["producto"] = {
            "nuevo": False,
            "cambios": _cambios({c: getattr(actual, c) for c in CAMPOS_PRODUCTO}, campos_deseados),
        }

    act_var = {v.slug: v for v in (actual.variantes if actual else [])}
    for v in deseado.variantes:
        previo = act_var.pop(v.slug, None)
        if previo is None:
            diff["variantes"]["nuevas"].append(_jsonable(_dict_variante(v) | {"slug": v.slug}))
        else:
            cambios = _cambios(_dict_variante(previo), _dict_variante(v))
            if cambios:
                diff["variantes"]["cambiadas"].append({"slug": v.slug, "cambios": cambios})
    for slug, v in act_var.items():
        if v.activo:
            diff["variantes"]["retiradas"].append({"slug": slug, "nombre": v.nombre})

    # ── las filas: el grueso del archivo ───────────────────────────────────
    act_filas = {(f.variante or "", f.externo_id): f for f in (actual.filas if actual else [])}
    for f in deseado.filas:
        clave = (f.variante or "", f.externo_id)
        previo = act_filas.pop(clave, None)
        resumen = {
            "externo_id": f.externo_id,
            "variante": f.variante,
            "etiqueta": f.etiqueta,
            "inicio": _jsonable(f.inicio),
            "valores": _jsonable(f.valores),
        }
        if previo is None:
            diff["filas"]["nuevas"].append(resumen)
            continue
        cambios = _cambios(_dict_fila(previo), _dict_fila(f))
        if not cambios:
            continue
        entrada = dict(resumen, cambios=cambios)
        # Quitar una fila del medio del Excel le corre el `orden` a todas las
        # de abajo. Son cambios de verdad —se escriben— pero no son noticia, y
        # si entraran a «cambiadas» el precio que sí cambió quedaría enterrado
        # entre noventa filas idénticas. Van en su propio montón.
        if set(cambios) == {"orden"}:
            diff["filas"]["reordenadas"].append(entrada)
            continue
        # Una fila retirada que vuelve a aparecer en el archivo se reactiva. Es
        # un cambio, no un alta: conserva su historia y su id.
        if not previo.activo and f.activo:
            diff["filas"]["reactivadas"].append(entrada)
        diff["filas"]["cambiadas"].append(entrada)
    for (variante, externo_id), f in act_filas.items():
        if f.activo:
            diff["filas"]["retiradas"].append({
                "externo_id": externo_id,
                "variante": variante or None,
                "etiqueta": f.etiqueta,
                "inicio": _jsonable(f.inicio),
                "valores": _jsonable(f.valores),
            })

    # ── medios y alias ─────────────────────────────────────────────────────
    act_medios = {m.clave: m for m in (actual.medios if actual else [])}
    for m in deseado.medios:
        previo = act_medios.pop(m.clave, None)
        if previo is None:
            diff["medios"]["nuevos"].append(_jsonable(_dict_medio(m) | {"clave": m.clave}))
        else:
            cambios = _cambios(_dict_medio(previo), _dict_medio(m))
            if cambios:
                diff["medios"]["cambiados"].append({"clave": m.clave, "cambios": cambios})
    # Medios y alias no tienen columna `activo`, así que no hay forma de
    # retirarlos sin borrarlos — y acá no se borra nada. Se reportan y se
    # quitan a mano si sobran.
    diff["medios"]["huerfanos"] = [{"clave": k, "url": m.url} for k, m in act_medios.items()]

    act_alias = {(a.nivel, a.alias): a for a in (actual.alias if actual else [])}
    for a in deseado.alias:
        if act_alias.pop((a.nivel, a.alias), None) is None:
            diff["alias"]["nuevos"].append({"alias": a.alias, "nivel": a.nivel, "variante": a.variante})
    diff["alias"]["huerfanos"] = [
        {"alias": a.alias, "nivel": a.nivel} for a in act_alias.values()
    ]

    diff["totales"] = {
        "filas_nuevas": len(diff["filas"]["nuevas"]),
        "filas_cambiadas": len(diff["filas"]["cambiadas"]),
        "filas_retiradas": len(diff["filas"]["retiradas"]),
        "filas_reactivadas": len(diff["filas"]["reactivadas"]),
        "filas_reordenadas": len(diff["filas"]["reordenadas"]),
        "variantes_nuevas": len(diff["variantes"]["nuevas"]),
        "variantes_cambiadas": len(diff["variantes"]["cambiadas"]),
        "variantes_retiradas": len(diff["variantes"]["retiradas"]),
        "medios_nuevos": len(diff["medios"]["nuevos"]),
        "medios_cambiados": len(diff["medios"]["cambiados"]),
        "alias_nuevos": len(diff["alias"]["nuevos"]),
        "producto_nuevo": bool(diff["producto"].get("nuevo")),
        "producto_cambios": len(diff["producto"].get("cambios") or {}),
    }
    return diff


def hay_algo_que_hacer(diff: Dict[str, Any]) -> bool:
    t = diff["totales"]
    return bool(
        t["producto_nuevo"] or t["producto_cambios"]
        or t["filas_nuevas"] or t["filas_cambiadas"] or t["filas_retiradas"]
        or t["filas_reordenadas"]
        or t["variantes_nuevas"] or t["variantes_cambiadas"] or t["variantes_retiradas"]
        or t["medios_nuevos"] or t["medios_cambiados"] or t["alias_nuevos"]
    )


def firma(diff: Dict[str, Any]) -> str:
    """Huella del diff, para exigir que lo que se carga sea lo que se aprobó."""
    return hashlib.sha256(
        json.dumps(diff, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# La ventana de observación del fallback
# ---------------------------------------------------------------------------

def _config(bot) -> Dict[str, Any]:
    try:
        cfg = json.loads(bot.llm_config or "{}")
    except (TypeError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def bots_en_ventana(db, *, team_id: int, hoy: Optional[date] = None) -> List[Dict[str, Any]]:
    """Bots de la cuenta que leen de `productos` con la ventana todavía abierta.

    Mientras los dos motores están vivos, un turno puede caer al motor viejo y
    responder con los precios del JSON que va en la imagen. Si en ese momento
    la base ya tiene el tarifario nuevo, el cliente recibe precios viejos y
    nadie se entera hasta que reclama — peor que fallar. Por eso, durante la
    ventana, los datos se congelan.

    Cómo se sabe si sigue abierta: `llm_config.productos_ventana_hasta` (ISO).
    **Si no está, se asume abierta**: la ventana se cierra cuando alguien lo
    decide y lo escribe (los cuatro criterios de salida del plan), no porque
    falte un campo.
    """
    hoy = hoy or date.today()
    abiertas = []
    bots = db.query(models.Bot).filter(models.Bot.team_id == team_id).all()
    for bot in bots:
        cfg = _config(bot)
        if str(cfg.get("fuente_datos") or "").strip().lower() != "productos":
            continue
        crudo = cfg.get("productos_ventana_hasta")
        hasta = None
        if crudo:
            try:
                hasta = _fecha(crudo)
            except ValueError:
                hasta = None            # ilegible = no se puede dar por cerrada
        if hasta is not None and hasta < hoy:
            continue
        abiertas.append({"bot_id": bot.id, "nombre": bot.name, "hasta": hasta.isoformat() if hasta else None})
    return abiertas


# ---------------------------------------------------------------------------
# Aplicar
# ---------------------------------------------------------------------------

def aplicar(
    db,
    *,
    team_id: int,
    deseado: Catalogo,
    diff: Dict[str, Any],
    archivo: str,
    hash_sha256: str,
    aprobado_por_user_id: Optional[int],
) -> Tuple[models.BotProducto, models.BotProductoCarga]:
    """Escribe el catálogo y deja el rastro. Idempotente por construcción.

    No sigue el diff paso a paso: **vuelve a buscar cada cosa por su clave
    natural** y la crea o la actualiza. El diff es lo que se le mostró al
    humano; si por lo que sea no coincidiera con la base, el resultado sigue
    siendo el archivo, no una suma de deltas aplicados dos veces.
    """
    deseado.validar()

    producto = producto_de(db, team_id=team_id, slug=deseado.slug)
    if producto is None:
        producto = models.BotProducto(team_id=team_id, slug=deseado.slug, nombre=deseado.nombre)
        db.add(producto)
    for campo in CAMPOS_PRODUCTO:
        setattr(producto, campo, getattr(deseado, campo))
    db.flush()

    # ── variantes ──────────────────────────────────────────────────────────
    existentes = {
        v.slug: v
        for v in db.query(models.BotProductoVariante)
        .filter(models.BotProductoVariante.producto_id == producto.id)
        .all()
    }
    for v in deseado.variantes:
        fila = existentes.get(v.slug)
        if fila is None:
            fila = models.BotProductoVariante(producto_id=producto.id, slug=v.slug, nombre=v.nombre)
            db.add(fila)
            existentes[v.slug] = fila
        fila.nombre = v.nombre
        fila.instrucciones = v.instrucciones
        fila.atributos = v.atributos
        fila.orden = v.orden
        fila.activo = v.activo
    db.flush()
    en_archivo = {v.slug for v in deseado.variantes}
    for v in deseado.variantes:
        existentes[v.slug].precios_de_variante_id = (
            existentes[v.precios_de].id if v.precios_de else None
        )
    for slug, fila in existentes.items():
        if slug not in en_archivo and fila.activo:
            fila.activo = False          # se retira, no se borra
    db.flush()

    ids = {slug: fila.id for slug, fila in existentes.items()}

    def _ref(slug: Optional[str]) -> int:
        return ids[slug] if slug else models.REF_TODAS

    # ── filas ──────────────────────────────────────────────────────────────
    # La clave es exactamente el UNIQUE de la tabla: acá se juega la
    # idempotencia de todo el importador.
    filas_db = {
        (f.variante_id, f.externo_id): f
        for f in db.query(models.BotProductoFila)
        .filter(models.BotProductoFila.producto_id == producto.id)
        .all()
    }
    vistas = set()
    for f in deseado.filas:
        clave = (_ref(f.variante), f.externo_id)
        vistas.add(clave)
        fila = filas_db.get(clave)
        if fila is None:
            fila = models.BotProductoFila(
                producto_id=producto.id, variante_id=clave[0], externo_id=f.externo_id
            )
            db.add(fila)
            filas_db[clave] = fila
        fila.tipo = f.tipo
        fila.etiqueta = f.etiqueta
        fila.inicio = f.inicio
        fila.fin = f.fin
        fila.valores = f.valores
        fila.nota = f.nota
        fila.orden = f.orden
        fila.activo = f.activo
    for clave, fila in filas_db.items():
        if clave not in vistas and fila.activo:
            fila.activo = False          # se retira, no se borra

    # ── medios ─────────────────────────────────────────────────────────────
    medios_db = {
        m.clave: m
        for m in db.query(models.BotProductoMedio)
        .filter(models.BotProductoMedio.producto_id == producto.id)
        .all()
    }
    for m in deseado.medios:
        medio = medios_db.get(m.clave)
        if medio is None:
            medio = models.BotProductoMedio(producto_id=producto.id, clave=m.clave, url=m.url)
            db.add(medio)
            medios_db[m.clave] = medio
        medio.variante_id = _ref(m.variante)
        medio.url = m.url
        medio.tipo = m.tipo
        medio.descripcion = m.descripcion
        medio.aplica = m.aplica

    # ── alias ──────────────────────────────────────────────────────────────
    alias_db = {
        (a.nivel, a.alias)
        for a in db.query(models.BotProductoAlias)
        .filter(models.BotProductoAlias.producto_id == producto.id)
        .all()
    }
    for a in deseado.alias:
        if (a.nivel, a.alias) in alias_db:
            continue
        db.add(
            models.BotProductoAlias(
                producto_id=producto.id,
                nivel=a.nivel,
                ref_id=_ref(a.variante) if a.nivel == models.ALIAS_NIVEL_VARIANTE else models.REF_TODAS,
                alias=a.alias,
            )
        )

    t = diff["totales"]
    carga = models.BotProductoCarga(
        producto_id=producto.id,
        # Solo el nombre del archivo: la ruta del equipo del CEO no aporta y
        # la columna es de 300.
        archivo=os.path.basename(archivo)[:300],
        hash_sha256=hash_sha256,
        filas_nuevas=t["filas_nuevas"],
        filas_cambiadas=t["filas_cambiadas"],
        filas_retiradas=t["filas_retiradas"],
        estado=models.CARGA_ESTADO_APLICADO,
        diff=_jsonable(diff),
        aprobado_por_user_id=aprobado_por_user_id,
    )
    db.add(carga)
    db.commit()
    return producto, carga


# ---------------------------------------------------------------------------
# El HTML de revisión
# ---------------------------------------------------------------------------

def _esc(v: Any) -> str:
    if v is None or v == "":
        return '<span class="nulo">—</span>'
    if isinstance(v, (dict, list)):
        return f"<code>{html.escape(json.dumps(_jsonable(v), ensure_ascii=False))}</code>"
    return html.escape(str(v))


def _tabla_filas(filas: Sequence[Dict[str, Any]], *, clase: str) -> str:
    if not filas:
        return '<p class="nada">Ninguna.</p>'
    cuerpo = []
    for f in filas:
        cambios = f.get("cambios") or {}
        detalle = "".join(
            f"<div class='cambio'><b>{html.escape(c)}</b>: "
            f"<span class='antes'>{_esc(a)}</span> → <span class='despues'>{_esc(d)}</span></div>"
            for c, (a, d) in sorted(cambios.items())
        )
        cuerpo.append(
            f"<tr class='{clase}'><td><code>{_esc(f.get('externo_id'))}</code></td>"
            f"<td>{_esc(f.get('variante'))}</td><td>{_esc(f.get('etiqueta'))}</td>"
            f"<td>{_esc(f.get('inicio'))}</td>"
            f"<td>{detalle or _esc(f.get('valores'))}</td></tr>"
        )
    return (
        "<table class='datos'><thead><tr><th>externo_id</th><th>variante</th>"
        "<th>etiqueta</th><th>inicio</th><th>valores / cambios</th></tr></thead>"
        f"<tbody>{''.join(cuerpo)}</tbody></table>"
    )


def escribir_revision(
    diff: Dict[str, Any],
    *,
    salida: str,
    titulo: str,
    archivo: str,
    hash_sha256: str,
    team_id: int,
    como_se_lleno: Sequence[str] = (),
    ventana: Sequence[Dict[str, Any]] = (),
    producto_existe: bool = False,
) -> None:
    """El diff en HTML. Es lo único que mira quien aprueba, así que dice todo."""
    t = diff["totales"]
    prod = diff["producto"]
    if prod.get("nuevo"):
        bloque_producto = (
            "<p>El producto <b>no existe todavía</b>: se crea con estos valores.</p>"
            + _esc(prod.get("valores"))
        )
    elif prod.get("cambios"):
        bloque_producto = "".join(
            f"<div class='cambio'><b>{html.escape(c)}</b>: "
            f"<span class='antes'>{_esc(a)}</span> → <span class='despues'>{_esc(d)}</span></div>"
            for c, (a, d) in sorted(prod["cambios"].items())
        )
    else:
        bloque_producto = '<p class="nada">La ficha del producto no cambia.</p>'

    def _lista(items: Sequence[Dict[str, Any]], campos: Sequence[str]) -> str:
        if not items:
            return '<p class="nada">Ninguno.</p>'
        filas = "".join(
            "<tr>" + "".join(f"<td>{_esc(i.get(c))}</td>" for c in campos) + "</tr>"
            for i in items
        )
        cabeza = "".join(f"<th>{html.escape(c)}</th>" for c in campos)
        return f"<table class='datos'><thead><tr>{cabeza}</tr></thead><tbody>{filas}</tbody></table>"

    aviso_ventana = ""
    if ventana:
        cuales = ", ".join(
            f"{html.escape(str(b['nombre']))} (#{b['bot_id']}"
            + (f", hasta {html.escape(b['hasta'])}" if b.get("hasta") else ", sin fecha anotada")
            + ")"
            for b in ventana
        )
        aviso_ventana = f"""
      <div class="peligro">
        <h3>La ventana de observación del fallback sigue abierta</h3>
        <p>Estos bots de la cuenta ya leen de <code>productos</code>: {cuales}.</p>
        <p>Mientras los dos motores están vivos, un turno puede caer al motor viejo y
           cotizar con los precios del JSON de la imagen. Si cargas esto ahora, la base
           y el JSON dejan de decir lo mismo y <b>nadie se entera hasta que un cliente
           reclame</b>. Lo normal es congelar el tarifario hasta que cierre la ventana;
           si el cambio no puede esperar, se hace en los dos lados y se anota.</p>
        <p><code>--cargar</code> va a pedir confirmación explícita
           (<code>--acepto-ventana-abierta</code>).</p>
      </div>"""

    with open(salida, "w", encoding="utf-8") as fh:
        fh.write(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)} · revisión previa</title>
<style>
  :root {{ --tinta:#12211c; --suave:#5d726a; --linea:#dfe7e3; --fondo:#f6f8f7;
           --acento:#0f5c46; --alerta:#b4530a; --alerta-bg:#fff6ec;
           --rojo:#a6301f; --rojo-bg:#fdeceb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--fondo); color:var(--tinta);
         font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  header {{ background:#fff; border-bottom:1px solid var(--linea); padding:32px 28px; }}
  .wrap {{ max-width:1120px; margin:0 auto; }}
  h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:-.3px; }}
  .sub {{ color:var(--suave); margin:0 0 22px; }}
  .kpis {{ display:flex; flex-wrap:wrap; gap:10px; }}
  .kpi {{ background:var(--fondo); border:1px solid var(--linea); border-radius:10px;
          padding:10px 16px; min-width:118px; }}
  .kpi b {{ display:block; font-size:24px; line-height:1.2; }}
  .kpi span {{ color:var(--suave); font-size:12.5px; }}
  .kpi.retira b {{ color:var(--rojo); }}
  main {{ padding:28px; }}
  section {{ background:#fff; border:1px solid var(--linea); border-radius:12px;
             padding:20px 22px; margin-bottom:18px; }}
  section > h2 {{ margin:0 0 14px; font-size:18px; }}
  .aviso {{ background:#fff; border:1px solid var(--linea); border-left:4px solid var(--acento);
            border-radius:10px; padding:18px 22px; margin-bottom:22px; }}
  .peligro {{ background:var(--alerta-bg); border:1px solid #f0d7b8;
              border-left:4px solid var(--alerta); border-radius:10px;
              padding:18px 22px; margin-bottom:22px; color:#6b3d09; }}
  .peligro h3 {{ margin:0 0 8px; font-size:16px; color:var(--alerta); }}
  table.datos {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
  table.datos th {{ text-align:left; color:var(--suave); font-size:12px; font-weight:600;
                    border-bottom:1px solid var(--linea); padding:6px 10px 6px 0;
                    font-family:ui-monospace,monospace; }}
  table.datos td {{ padding:6px 10px 6px 0; border-bottom:1px solid #f0f4f2;
                    vertical-align:top; }}
  tr.retirada td {{ background:var(--rojo-bg); }}
  code {{ font-family:ui-monospace,monospace; font-size:12.5px; }}
  .cambio {{ margin:2px 0; }}
  .antes {{ color:var(--rojo); text-decoration:line-through; }}
  .despues {{ color:var(--acento); }}
  .nulo {{ color:#b9c5c0; font-style:italic; }}
  .nada {{ color:var(--suave); font-style:italic; margin:0; }}
  details {{ margin-top:12px; }}
  summary {{ cursor:pointer; color:var(--acento); font-size:13px; }}
  pre {{ background:#f6f8f7; border:1px solid var(--linea); border-radius:8px;
         padding:12px; font-size:12px; overflow-x:auto; }}
  .hash {{ font-family:ui-monospace,monospace; font-size:12px; color:var(--suave);
           word-break:break-all; }}
</style></head><body>
<header><div class="wrap">
  <h1>{html.escape(titulo)}</h1>
  <p class="sub">Producto <code>{html.escape(diff['slug'])}</code> ·
     cuenta <code>team_id={team_id}</code> ·
     {'ya existe en la base' if producto_existe else 'se crearía ahora'} ·
     {datetime.now().strftime('%Y-%m-%d %H:%M')}.
     <b>Nada se ha escrito en la base todavía.</b></p>
  <div class="kpis">
    <div class="kpi"><b>{t['filas_nuevas']}</b><span>filas nuevas</span></div>
    <div class="kpi"><b>{t['filas_cambiadas']}</b><span>filas cambiadas</span></div>
    <div class="kpi retira"><b>{t['filas_retiradas']}</b><span>filas retiradas</span></div>
    <div class="kpi"><b>{t['variantes_nuevas']}+{t['variantes_cambiadas']}</b><span>variantes nuevas/cambiadas</span></div>
    <div class="kpi"><b>{t['medios_nuevos']}+{t['medios_cambiados']}</b><span>medios nuevos/cambiados</span></div>
    <div class="kpi"><b>{t['alias_nuevos']}</b><span>alias nuevos</span></div>
  </div>
</div></header>
<main><div class="wrap">
  {aviso_ventana}
  <div class="aviso">
    <h3>De dónde sale cada cosa</h3>
    <ul>{''.join(f'<li>{html.escape(c)}</li>' for c in como_se_lleno)}</ul>
    <p class="hash">archivo: <code>{html.escape(os.path.basename(archivo))}</code><br>
       sha256: {html.escape(hash_sha256)}</p>
    <p>Lo que se retira <b>no se borra</b>: queda con <code>activo = false</code> y se
       puede volver a activar cargando un archivo que la traiga de nuevo.</p>
  </div>

  <section><h2>Ficha del producto</h2>{bloque_producto}</section>

  <section><h2>Variantes</h2>
    <h3>Nuevas</h3>{_lista(diff['variantes']['nuevas'], ('slug', 'nombre', 'orden', 'precios_de', 'atributos'))}
    <h3>Cambiadas</h3>{_lista([
        {'slug': v['slug'], 'cambios': json.dumps(_jsonable(v['cambios']), ensure_ascii=False)}
        for v in diff['variantes']['cambiadas']
    ], ('slug', 'cambios'))}
    <h3>Retiradas (quedan <code>activo = false</code>)</h3>{_lista(diff['variantes']['retiradas'], ('slug', 'nombre'))}
  </section>

  <section><h2>Filas que se retiran ({t['filas_retiradas']})</h2>
    <p class="nada">Se marcan <code>activo = false</code>. No se borra ninguna.</p>
    {_tabla_filas(diff['filas']['retiradas'], clase='retirada')}
  </section>

  <section><h2>Filas que cambian ({t['filas_cambiadas']})</h2>
    {_tabla_filas(diff['filas']['cambiadas'], clase='cambiada')}
  </section>

  <section><h2>Filas nuevas ({t['filas_nuevas']})</h2>
    {_tabla_filas(diff['filas']['nuevas'], clase='nueva')}
  </section>

  <section><h2>Filas que solo se corrieron de lugar ({t['filas_reordenadas']})</h2>
    <p class="nada">Quitar una fila del medio del archivo le corre el <code>orden</code>
       a todas las de abajo. Se escriben igual, pero no cambió nada de lo que el bot
       dice: van aparte para no enterrar los cambios de verdad.</p>
    <details><summary>Ver las {t['filas_reordenadas']}</summary>
      {_tabla_filas(diff['filas']['reordenadas'], clase='reordenada')}
    </details>
  </section>

  <section><h2>Medios</h2>
    <h3>Nuevos</h3>{_lista(diff['medios']['nuevos'], ('clave', 'variante', 'tipo', 'url', 'aplica', 'descripcion'))}
    <h3>Cambiados</h3>{_lista([
        {'clave': m['clave'], 'cambios': json.dumps(_jsonable(m['cambios']), ensure_ascii=False)}
        for m in diff['medios']['cambiados']
    ], ('clave', 'cambios'))}
    <h3>En la base y no en el archivo</h3>
    <p class="nada">No se tocan (la tabla no tiene <code>activo</code>): si sobran, se quitan a mano.</p>
    {_lista(diff['medios']['huerfanos'], ('clave', 'url'))}
  </section>

  <section><h2>Alias</h2>
    <h3>Nuevos</h3>{_lista(diff['alias']['nuevos'], ('alias', 'nivel', 'variante'))}
    <h3>En la base y no en el archivo</h3>{_lista(diff['alias']['huerfanos'], ('alias', 'nivel'))}
  </section>

  <section><h2>El diff completo</h2>
    <details><summary>JSON tal como quedará en <code>bot_producto_cargas.diff</code></summary>
      <pre>{html.escape(json.dumps(_jsonable(diff), ensure_ascii=False, indent=1))}</pre>
    </details>
  </section>
</div></main></body></html>""")
