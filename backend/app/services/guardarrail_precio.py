"""Guardarraíl de precio del bot 2 de Arranquemos Pues (estrategia 18).

El caso que lo justifica es la conversación 636: la clienta pidió Amor de Dios,
del 16 al 19 de octubre, en doble. El bot le cotizó $549.000 por persona; el
tarifario dice $505.000. Y lo que hace difícil atraparlo es que **$549.000 sí
existe** en el tarifario: es la doble de Amor de Dios del 15 al 18 de enero. El
bot no inventó una cifra, tomó la fila equivocada. Un chequeo de «¿este número
existe?» lo deja pasar sin ruido.

Por eso este módulo compara cada monto del mensaje contra la **combinación**
que el propio mensaje nombra (hotel + salida + acomodación), leída del texto
que devolvió la herramienta de precios en el turno.

Es puro: no toca la base, no llama al modelo, no lee archivos. El motor le pasa
los resultados de `consultar_tarifario` / `consultar_precios` (mismo formato de
texto: `productos_fuentes/covenas.py PRESENTACION` calca
`tarifario._bloque_hotel`), los «desde» válidos de la vitrina, las cifras que
dijo el cliente y `tarifario.extras()`.

Reglas (plan del arquitecto §5), en el orden en que se evalúan para cada monto:

  0. Cifra que dijo el cliente (su presupuesto), o ese presupuesto dividido en
     2-15 personas → pasa. Repetirle al cliente su propio número es legítimo.
  1. Valor de `extras` (niños, canoa, bici-taxi) o suma de 1-4 niños → pasa.
  2. «desde X» → pasa si X es un «desde» válido o si es ≥ al mínimo consultado.
  3. Con hotel / salida / acomodación identificados en la misma frase (o la
     mención más cercana antes del monto): tiene que ser el precio de ESA fila
     o un derivado suyo. Si es de otra fila → viola (el caso 636).
  4. Sin atributos: tiene que estar en el conjunto directo (cualquier cifra de
     los resultados) o derivado de cualquier fila consultada.
  5. Sin ninguna consulta → todo lo que no sea extra / cliente / «desde» válido
     viola.

Derivados de un precio p (por persona): n·p con n de 1 a 15, más k niños (k de
0 a 4, con los valores de `extras`), mezcla de n₁ en múltiple y n₂ en doble de
la misma salida, la diferencia doble − múltiple (×n), y el anticipo (30 %) y el
saldo (70 %) de cualquiera de ellos con ±$1.000 de tolerancia por redondeo.

Se priorizan **cero falsos positivos** sobre atrapar todo: cuando una mención no
se puede casar con ninguna fila consultada (fecha mal leída, salida que no se
consultó en este turno) se cae a la regla 4, que es permisiva. El costo de un
falso positivo es un turno corregido de más con un cliente real esperando; el
de un falso negativo es el de hoy, sin guardarraíl.

Lo que NO es un monto: porcentajes («30 %»), plazos («8 a 10 días»), horas,
fechas («16 al 19»), teléfonos, cantidades de personas. Solo se leen
`$NNN.NNN`, `$NNNNNN`, «NNN mil», «NNN.NNN pesos» y «N millones» (y `$N'NNN.NNN`
a la colombiana). Montos por debajo de $10.000 se ignoran: ninguna tarifa del
plan cuesta eso y ahí viven las propinas del itinerario.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass
from itertools import combinations_with_replacement
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = ["viola_precio", "extraer_montos", "filas_de_resultados"]

#: Tolerancia del anticipo / saldo: el bot redondea «$151.500» a «$152.000».
_TOLERANCIA = 1_000
#: Personas por cotización (el plan es de grupo; más allá se escala).
_MAX_PERSONAS = 15
#: Niños por cotización.
_MAX_NINOS = 4
#: Debajo de esto no es una tarifa del plan.
_MINIMO = 10_000

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_NOMBRE_MES = {v: k for k, v in _MESES.items() if k != "setiembre"}
_MES_RE = "|".join(sorted(_MESES, key=len, reverse=True))

#: Bohíos cobra la tabla de Amor de Dios (`hoteles: ["amor_de_dios","bohios"]`
#: en todas sus filas del JSON; en productos lee las de Amor de Dios por
#: `precios_de_variante_id`). Para comparar precios son el mismo hotel.
_HOTEL_CANON = {"amor_de_dios": "amor_de_dios", "bohios": "amor_de_dios",
                "piedra_mar": "piedra_mar"}
_NOMBRE_HOTEL = {"amor_de_dios": "Amor de Dios", "piedra_mar": "Piedra Mar"}
_HOTEL_RE = re.compile(
    r"\b(?:(?P<amor>(?:el\s{1,3})?amor\s{1,3}de\s{1,3}dios|amordios)"
    r"|(?P<bohios>bohios)"
    r"|(?P<piedra>piedra\s{0,3}mar))\b"
)


_PLANO_CACHE: Dict[str, str] = {}


def _plano_char(c: str) -> str:
    plano = _PLANO_CACHE.get(c)
    if plano is None:
        base = "".join(
            ch for ch in unicodedata.normalize("NFD", c)
            if unicodedata.category(ch) != "Mn"
        )
        plano = base[:1].lower() if base else " "
        if len(plano) != 1:          # `lower()` de algunos caracteres crece
            plano = " "
        if len(_PLANO_CACHE) < 4096:
            _PLANO_CACHE[c] = plano
    return plano


def _plano(texto: str) -> str:
    """Minúsculas y sin tildes, **conservando las posiciones** carácter a
    carácter (para poder cruzar lo que se encuentra aquí con el texto
    original). Lineal: ASCII va directo y el resto pasa por una caché."""
    texto = texto or ""
    if texto.isascii():
        return texto.lower()
    return "".join(_plano_char(c) for c in texto)


# ---------------------------------------------------------------------------
# Montos
# ---------------------------------------------------------------------------

#: Hasta miles de millones. Con tope y sin solaparse con el número de al lado:
#: sin eso, «9» × 20.000 tardaba segundos (auditoría H1, ReDoS cuadrático).
#: Todas las regex que leen texto del bot llevan cuantificadores acotados.
_NUM_PUNTOS = r"\d{1,3}(?:[.'’]\d{3}){1,3}"
_FIN_NUM = r"(?!\d|[.,'’]\d)"
_MONTO_RE = re.compile(
    # 1,5 millones · $1.2 millones · 2 millones
    r"(?<![\d.,'’])(?P<mill>\$?\s?\d{1,4}(?:[.,]\d{1,3})?)\s?(?:millones|millon|palos?)\b"
    # $459 mil · 459 mil · 459k · 450 lucas
    r"|(?<![\d.,'’])(?P<mil>\$?\s?\d{1,3}(?:[.,]\d{1,3})?)\s?(?:mil|k|lucas)\b"
    # $459.000 · $1'010.000 · $ 459.000
    r"|\$\s?(?P<pts>" + _NUM_PUNTOS + r")" + _FIN_NUM +
    # 459.000 pesos · 459.000 COP
    r"|(?<![\d$.,'’])(?P<pesos>" + _NUM_PUNTOS + r")\s?(?:pesos|cop)\b"
    # $459000
    r"|\$\s?(?P<crudo>\d{4,9})\b",
)


def _a_int(texto: str) -> Optional[float]:
    texto = texto.replace("$", "").replace(" ", "")
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


@dataclass(frozen=True)
class _Monto:
    inicio: int
    fin: int
    valor: int


def _montos(plano: str) -> List[_Monto]:
    fuera: List[_Monto] = []
    for m in _MONTO_RE.finditer(plano):
        valor: Optional[float] = None
        if m.group("mill") is not None:
            base = _a_int(m.group("mill"))
            valor = base * 1_000_000 if base is not None else None
        elif m.group("mil") is not None:
            base = _a_int(m.group("mil"))
            valor = base * 1_000 if base is not None else None
        else:
            crudo = m.group("pts") or m.group("pesos") or m.group("crudo") or ""
            digitos = re.sub(r"\D", "", crudo)
            valor = float(digitos) if digitos else None
        if valor is None:
            continue
        entero = int(round(valor))
        if entero < _MINIMO:
            continue
        inicio = m.start()
        while inicio < m.end() and plano[inicio].isspace():
            inicio += 1          # la rama «mil» admite un espacio inicial
        fuera.append(_Monto(inicio, m.end(), entero))
    return fuera


def extraer_montos(texto: str) -> List[int]:
    """Los montos en pesos de un texto (para armar `cifras_cliente` con lo que
    escribió el cliente: «tengo 450 mil», «$900.000 para los dos»)."""
    return [m.valor for m in _montos(_plano(texto))]


# ---------------------------------------------------------------------------
# Filas del resultado de la herramienta
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fila:
    hotel: str          # canónico: amor_de_dios | piedra_mar
    mes: Optional[int]
    dia_ini: Optional[int]
    dia_fin: Optional[int]
    multiple: int
    doble: int
    etiqueta: str


_TITULO_RE = re.compile(
    r"^[ \t]{0,8}(?P<hotel>amor de dios|bohios|piedra mar) — (?P<mes>" + _MES_RE
    + r")\b[^\n]{0,80}\(\d{1,4} salidas?\):", re.MULTILINE,
)
#: Solo renglones que EMPIEZAN con «·»: un mensaje de error de la herramienta
#: repite la entrada del modelo («No reconozco el hotel '…'») y no puede
#: colar filas ni cifras (auditoría B1).
_FILA_RE = re.compile(
    r"^[ \t]{0,8}·[ \t]{0,3}(?:(?P<hotel>amor de dios|bohios|piedra mar) — )?"
    r"(?P<fecha>[^·\n—:]{1,120})(?:—|:)[ \t]{0,3}multiple[ \t]{1,3}\$(?P<m>"
    + _NUM_PUNTOS + r")[ \t]{0,3}·[ \t]{0,3}doble[ \t]{1,3}\$(?P<d>" + _NUM_PUNTOS + r")",
    re.MULTILINE,
)
#: Renglones del resultado cuyas cifras son precios publicados: los «desde»
#: (por hotel y de entre semana), el «hasta» de la lista recortada y el
#: «PERO en otros meses» de la búsqueda por presupuesto.
_LINEA_PRECIOS_RE = re.compile(
    r"^[ \t]{0,8}(?:(?:amor de dios|piedra mar|bohios)[^\n]{0,40} — «desde»"
    r"|entre semana \(lunes con jueves\)"
    r"|\(y \d{1,4} mas, hasta \$"
    r"|pero en otros meses si le alcanza)",
)
_FECHA_FILA_RE = re.compile(
    r"(?P<mes>" + _MES_RE + r")\s{1,3}(?P<ini>\d{1,2})\s{1,3}al\s{1,3}(?P<fin>\d{1,2})"
)
_PESOS_RE = re.compile(r"\$\s?(" + _NUM_PUNTOS + r")" + _FIN_NUM)


def _hotel_de(nombre: str) -> Optional[str]:
    n = (nombre or "").strip()
    if n.startswith("amor"):
        return "amor_de_dios"
    if n.startswith("bohios"):
        return "amor_de_dios"
    if n.startswith("piedra"):
        return "piedra_mar"
    return None


def _entero(pesos: str) -> int:
    return int(re.sub(r"\D", "", pesos))


#: Los errores de la herramienta repiten la entrada del modelo («No reconozco
#: el hotel '…'»), que puede traer saltos de línea y una fila falsa adentro.
#: Esos resultados se descartan completos (re-auditoría B1).
_ERROR_RE = re.compile(r"^\s{0,8}no\s(?:reconozco|entendi)\b")


def _resultados_validos(resultados: Iterable[str]) -> List[str]:
    return [r for r in (resultados or []) if r and not _ERROR_RE.match(_plano(r[:40]))]


def filas_de_resultados(resultados: Iterable[str]) -> List[Fila]:
    """Las salidas con precio que traen los resultados de la herramienta.

    Reconoce los dos renglones que produce `consultar_tarifario` (y
    `consultar_precios`, que es el mismo texto):

      ``  · OCTUBRE 16 AL 19 — múltiple $459.000 · doble $505.000 (...)``
      (bajo el título ``Amor de Dios — Octubre (5 salidas):``)

      ``  · Amor de Dios — DICIEMBRE 08 AL 11: múltiple $369.000 · doble ...``
      (búsqueda por presupuesto, el hotel va en el renglón)
    """
    filas: List[Fila] = []
    for resultado in _resultados_validos(resultados):
        original = resultado or ""
        plano = _plano(original)
        titulos = [(m.start(), _hotel_de(m.group("hotel")))
                   for m in _TITULO_RE.finditer(plano)]
        for m in _FILA_RE.finditer(plano):
            hotel = _hotel_de(m.group("hotel") or "")
            if hotel is None:
                previos = [h for pos, h in titulos if pos < m.start()]
                hotel = previos[-1] if previos else None
            if hotel is None:
                continue
            fecha = m.group("fecha").strip(" \t")
            etiqueta = original[m.start("fecha"):m.end("fecha")].strip()
            f = _FECHA_FILA_RE.search(fecha)
            mes = _MESES[f.group("mes")] if f else None
            ini = int(f.group("ini")) if f else None
            fin = int(f.group("fin")) if f else None
            filas.append(Fila(
                hotel=hotel, mes=mes, dia_ini=ini, dia_fin=fin,
                multiple=_entero(m.group("m")), doble=_entero(m.group("d")),
                etiqueta=etiqueta,
            ))
    return filas


def _directos(resultados: Iterable[str]) -> Set[int]:
    """Cifras en pesos de los renglones de precios del resultado: filas de
    salidas, «desde», entre semana, «hasta» y «otros meses». NO las de
    cualquier renglón: los mensajes de error repiten lo que escribió el modelo
    (auditoría B1)."""
    fuera: Set[int] = set()
    for r in _resultados_validos(resultados):
        for linea in _plano(r).split("\n"):
            if _FILA_RE.match(linea) or _LINEA_PRECIOS_RE.match(linea):
                for m in _PESOS_RE.finditer(linea):
                    fuera.add(_entero(m.group(1)))
    return fuera


# ---------------------------------------------------------------------------
# Extras
# ---------------------------------------------------------------------------

def _valores_ninos(extras: Dict[str, Any]) -> List[int]:
    fuera = []
    for n in (extras or {}).get("ninos") or []:
        try:
            fuera.append(int(n["valor"]))
        except (KeyError, TypeError, ValueError):
            continue
    return fuera


def _valores_extras(extras: Dict[str, Any]) -> Set[int]:
    """Cifras sueltas de `extras` que el bot puede citar tal cual."""
    fuera: Set[int] = set(_valores_ninos(extras))
    for o in (extras or {}).get("otros") or []:
        if not isinstance(o, dict):
            continue
        for llave in ("valor", "valor_min", "valor_max"):
            try:
                fuera.add(int(o[llave]))
            except (KeyError, TypeError, ValueError):
                continue
    return fuera


def _sumas_ninos(extras: Dict[str, Any]) -> Set[int]:
    """0 a 4 niños, en cualquier combinación de edades (incluye el 0)."""
    valores = _valores_ninos(extras)
    sumas = {0}
    for k in range(1, _MAX_NINOS + 1):
        for combo in combinations_with_replacement(valores, k):
            sumas.add(sum(combo))
    return sumas


def _pct(extras: Dict[str, Any]) -> Optional[int]:
    try:
        pct = int((extras or {}).get("anticipo_pct"))
    except (TypeError, ValueError):
        return None
    return pct if 0 < pct < 100 else None


# ---------------------------------------------------------------------------
# Conjunto válido de una lista de filas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Contexto:
    """Qué derivados admite la frase del monto.

    El anticipo y el saldo se comparan con ±$1.000 de tolerancia, y sobre
    cientos de totales posibles esa tolerancia hace que casi cualquier cifra
    coincida por casualidad (p. ej. $550.000 ≈ 30 % de 4 × $459.000). Por eso
    solo se aceptan cuando la frase habla de anticipo / saldo; y la diferencia
    doble − múltiple, cuando habla de «más» o «diferencia». Lo mismo con los
    niños: «precio + un niño» coincide a menudo con el precio de otra fila
    (+$55.000), así que sumar niños exige que la frase los nombre.
    """
    anticipo: bool = False
    saldo: bool = False
    diferencia: bool = False
    ninos: bool = False


class _Validos:
    """Exactos, más anticipos / saldos (con tolerancia) y diferencias."""

    def __init__(self) -> None:
        self.exactos: Set[int] = set()
        self.diferencias: Set[int] = set()
        self._anticipos: List[float] = []
        self._saldos: List[float] = []

    def agregar(self, valores: Iterable[int], ninos: Set[int],
                pct: Optional[int]) -> None:
        nuevos = {v + k for v in valores for k in ninos}
        self.exactos |= nuevos
        if pct:
            for v in nuevos:
                self._anticipos.append(v * pct / 100)
                self._saldos.append(v * (100 - pct) / 100)

    def cerrar(self) -> "_Validos":
        self._anticipos.sort()
        self._saldos.sort()
        return self

    @staticmethod
    def _cerca(lista: List[float], valor: int) -> bool:
        i = bisect.bisect_left(lista, valor - _TOLERANCIA)
        return i < len(lista) and lista[i] <= valor + _TOLERANCIA

    def contiene(self, valor: int, ctx: _Contexto) -> bool:
        if valor in self.exactos:
            return True
        if ctx.diferencia and valor in self.diferencias:
            return True
        if ctx.anticipo and self._cerca(self._anticipos, valor):
            return True
        return ctx.saldo and self._cerca(self._saldos, valor)


def _validos_de(filas: Sequence[Fila], acomodaciones: Set[str],
                ninos: Set[int], pct: Optional[int]) -> _Validos:
    """Derivados de las filas en la(s) acomodación(es) indicada(s)."""
    ambas = not acomodaciones or acomodaciones >= {"doble", "multiple"}
    bases: Set[int] = set()
    v = _Validos()
    for f in filas:
        precios = []
        if ambas or "multiple" in acomodaciones:
            precios.append(f.multiple)
        if ambas or "doble" in acomodaciones:
            precios.append(f.doble)
        for p in precios:
            for n in range(1, _MAX_PERSONAS + 1):
                bases.add(n * p)
        # «La doble cuesta $46.000 más»: la frase puede nombrar una sola
        # acomodación y aun así hablar de la diferencia entre las dos.
        dif = f.doble - f.multiple
        v.diferencias |= {n * dif for n in range(1, _MAX_PERSONAS + 1)}
        if ambas:
            # Grupo mixto en la misma salida: n1 en múltiple + n2 en doble.
            for n1 in range(1, _MAX_PERSONAS):
                for n2 in range(1, _MAX_PERSONAS - n1 + 1):
                    bases.add(n1 * f.multiple + n2 * f.doble)
    v.agregar(bases, ninos, pct)
    return v.cerrar()


# ---------------------------------------------------------------------------
# Atributos del mensaje del bot
# ---------------------------------------------------------------------------

_UNIDADES_NO_FECHA = (
    r"(?!\s{0,3}(?:anos?|dias?|noches?|personas?|adultos?|ninos?|ninas?|bebes?|"
    r"horas?|hrs?|h\b|pm|am|p\.?\s?m|a\.?\s?m|%|por\s{0,3}ciento|mil\b|millon|"
    r"pax|cupos?|semanas?|meses|minutos?|min\b|habitaciones?|cuotas?|"
    r"pasajeros?|sillas?|puestos?|:\d))"
)
_DIA = r"(?<![\d$.,:'’])(?:[1-9]|[12]\d|3[01]|0[1-9])(?!\d|[.,:]\d)"
#: Meses como los escribe el bot: completos y abreviados («30 oct-2 nov»,
#: «Oct 30–Nov 02», «29 dic-2 ene»). «mar» NO va: choca con «Piedra Mar».
_MESES_BOT = dict(_MESES, **{
    "ene": 1, "feb": 2, "abr": 4, "jun": 6, "jul": 7, "ago": 8, "sep": 9,
    "sept": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
})
_MESB = "(?:" + "|".join(sorted(_MESES_BOT, key=len, reverse=True)) + r")\b"
_SEP = r"\s{0,3}(?:al|a|-|–)\s{0,3}"
_FECHA_RE = re.compile(
    # 30 de octubre al 2 de noviembre · 30 de oct al 02 de nov
    r"(?P<a_ini>" + _DIA + r")\s{1,3}de\s{1,3}(?P<a_mes>" + _MESB + r")\s{1,3}al?\s{1,3}"
    r"(?P<a_fin>" + _DIA + r")(?:\s{1,3}de\s{1,3}" + _MESB + r")?"
    # 30 oct-2 nov · 29 dic - 2 ene · 16 oct al 19
    r"|(?P<f_ini>" + _DIA + r")\s{1,3}(?P<f_mes>" + _MESB + r")" + _SEP
    + r"(?P<f_fin>" + _DIA + r")" + _UNIDADES_NO_FECHA
    + r"(?:\s{1,3}(?:de\s{1,3})?" + _MESB + r")?"
    # Oct 30–Nov 02 · octubre 30 - noviembre 2
    r"|\b(?P<g_mes>" + _MESB + r")\s{1,3}(?P<g_ini>" + _DIA + r")" + _SEP
    + _MESB + r"\s{1,3}(?P<g_fin>" + _DIA + r")"
    # 30 nov 02 (la salida es del mes anterior si el segundo día es menor)
    r"|(?P<h_ini>" + _DIA + r")\s{1,3}(?P<h_mes>" + _MESB + r")\s{1,3}(?P<h_fin>" + _DIA
    + r")" + _UNIDADES_NO_FECHA
    # 16 al 19 [de octubre] · 16-19 · 16 a 19
    + r"|(?P<b_ini>" + _DIA + r")" + _SEP + r"(?P<b_fin>" + _DIA + r")"
    + _UNIDADES_NO_FECHA + r"(?:\s{1,3}de\s{1,3}(?P<b_mes>" + _MESB + r"))?"
    # octubre 16 [al 19] · Oct 09-12
    r"|\b(?P<c_mes>" + _MESB + r")\s{1,3}(?P<c_ini>" + _DIA + r")"
    r"(?:" + _SEP + r"(?P<c_fin>" + _DIA + r"))?" + _UNIDADES_NO_FECHA
    # 16 de octubre · 8 dic
    + r"|(?P<d_ini>" + _DIA + r")\s{1,3}(?:de\s{1,3})?(?P<d_mes>" + _MESB + r")"
    # octubre (solo)
    r"|\b(?P<e_mes>" + _MESB + r")"
)
_ACOM_RE = re.compile(
    r"\b(?:(?P<doble>dobles?)|(?P<mult>multiples?|triples?|cuadruples?))\b"
)
_DESDE_RE = re.compile(
    r"(?:desde|a\s{1,3}partir\s{1,3}de|arrancan?\s{1,3}(?:en|desde)|empiezan?\s{1,3}(?:en|desde)"
    r"|partiendo\s{1,3}de|parten\s{1,3}de|precios?\s{1,3}de\s{1,3}entrada\s{1,3}de)"
    r"(?:\s{1,3}(?:solo|solamente|tan\s{1,3}solo|apenas|unos|los|el|en)){0,4}\s{0,3}$"
)


@dataclass(frozen=True)
class _Fecha:
    pos: int
    mes: Optional[int]
    ini: Optional[int]
    fin: Optional[int]


def _mes_anterior(mes: int) -> int:
    return 12 if mes == 1 else mes - 1


def _fechas(plano: str) -> List[_Fecha]:
    crudas: List[_Fecha] = []
    M = _MESES_BOT
    for m in _FECHA_RE.finditer(plano):
        g = m.groupdict()
        if g["a_ini"]:
            crudas.append(_Fecha(m.start(), M[g["a_mes"]], int(g["a_ini"]), int(g["a_fin"])))
        elif g["f_ini"]:
            crudas.append(_Fecha(m.start(), M[g["f_mes"]], int(g["f_ini"]), int(g["f_fin"])))
        elif g["g_mes"]:
            crudas.append(_Fecha(m.start(), M[g["g_mes"]], int(g["g_ini"]), int(g["g_fin"])))
        elif g["h_ini"]:
            ini, fin, mes = int(g["h_ini"]), int(g["h_fin"]), M[g["h_mes"]]
            crudas.append(_Fecha(m.start(), _mes_anterior(mes) if fin < ini else mes, ini, fin))
        elif g["b_ini"]:
            ini, fin = int(g["b_ini"]), int(g["b_fin"])
            mes = M[g["b_mes"]] if g["b_mes"] else None
            if mes is not None and fin < ini:
                # «30 al 2 de noviembre»: el mes nombrado es el del regreso;
                # la salida es del mes anterior.
                mes = _mes_anterior(mes)
            crudas.append(_Fecha(m.start(), mes, ini, fin))
        elif g["c_mes"]:
            crudas.append(_Fecha(m.start(), M[g["c_mes"]], int(g["c_ini"]),
                                 int(g["c_fin"]) if g["c_fin"] else None))
        elif g["d_ini"]:
            crudas.append(_Fecha(m.start(), M[g["d_mes"]], int(g["d_ini"]), None))
        elif g["e_mes"]:
            crudas.append(_Fecha(m.start(), M[g["e_mes"]], None, None))
    # Un rango sin mes hereda el último mes mencionado antes («En octubre: … el
    # 16 al 19 …»).
    fuera: List[_Fecha] = []
    ultimo_mes: Optional[int] = None
    for f in crudas:
        if f.mes is None and ultimo_mes is not None:
            f = _Fecha(f.pos, ultimo_mes, f.ini, f.fin)
        if f.mes is not None:
            ultimo_mes = f.mes
        fuera.append(f)
    return fuera


def _hoteles(plano: str) -> List[Tuple[int, str]]:
    fuera = []
    for m in _HOTEL_RE.finditer(plano):
        clave = "amor_de_dios" if (m.group("amor") or m.group("bohios")) else "piedra_mar"
        fuera.append((m.start(), clave))
    return fuera


def _acomodaciones(plano: str) -> List[Tuple[int, str]]:
    return [(m.start(), "doble" if m.group("doble") else "multiple")
            for m in _ACOM_RE.finditer(plano)]


def _frases(plano: str) -> List[Tuple[int, int]]:
    """(inicio, fin) de cada frase: corta en salto de línea y en . ! ? ; que
    no estén dentro de un número («$459.000» no se parte)."""
    cortes = []
    ini = 0
    for i, c in enumerate(plano):
        corta = c == "\n" or c in "!?;" or (
            c == "." and not (i + 1 < len(plano) and plano[i + 1].isdigit())
        )
        if corta:
            cortes.append((ini, i + 1))
            ini = i + 1
    cortes.append((ini, len(plano)))
    return [(a, b) for a, b in cortes if b > a]


class _Menciones:
    """Menciones ordenadas por posición, con búsqueda por bisección: cada monto
    pregunta «qué hay en mi frase» y «cuál es la última antes de mí» en
    O(log n), no recorriendo la lista entera (un mensaje con miles de montos
    sería cuadrático)."""

    def __init__(self, menciones: List[Tuple[int, Any]]) -> None:
        self.pos = [p for p, _ in menciones]
        self.val = [v for _, v in menciones]

    def en(self, a: int, b: int) -> List[Any]:
        return self.val[bisect.bisect_left(self.pos, a):bisect.bisect_left(self.pos, b)]

    def ultima_antes(self, pos: int) -> Optional[Tuple[int, Any]]:
        i = bisect.bisect_left(self.pos, pos)
        return (self.pos[i - 1], self.val[i - 1]) if i else None


class _Lineas:
    """Renglones del mensaje y cuáles son viñetas («• 16-19: $459.000», «📍
    *OCTUBRE…*», «- $799.000 (…)»): todo renglón que no arranca con letra,
    dígito, «¿», «¡» o «$»."""

    def __init__(self, plano: str) -> None:
        self.inicios = [0] + [i + 1 for i, c in enumerate(plano) if c == "\n"]
        self.vineta = []
        for k, a in enumerate(self.inicios):
            b = self.inicios[k + 1] - 1 if k + 1 < len(self.inicios) else len(plano)
            linea = plano[a:b].lstrip()
            self.vineta.append(bool(linea) and not (linea[0].isalnum() or linea[0] in "¿¡$"))

    def de(self, pos: int) -> int:
        return bisect.bisect_right(self.inicios, pos) - 1


def _atributos(pos: int, en_frase: frozenset, menciones: _Menciones,
               lineas: _Lineas) -> frozenset:
    """Las menciones (sin repetir) de la frase del monto, más la última antes
    del monto («la salida nombrada más cercana antes»).

    La de antes solo se hereda si está en el MISMO renglón, o si ni el renglón
    del monto ni el de la mención son viñetas. En una lista cada viñeta es su
    propia salida: «· Oct 09-12 (festivo): $559.000 / · Oct 16-19: $459.000»
    no puede juzgar la segunda contra la festiva (QA 2026-10-07)."""
    previa = menciones.ultima_antes(pos)
    if previa is None:
        return en_frase
    p_pos, valor = previa
    l_monto, l_mencion = lineas.de(pos), lineas.de(p_pos)
    if l_monto != l_mencion and (lineas.vineta[l_monto] or lineas.vineta[l_mencion]):
        return en_frase
    return en_frase | {valor}


_ANTICIPO_RE = re.compile(
    r"\b(?:anticipos?|adelantos?|cuota\s{1,3}inicial|inicial|abon\w{0,12}|separ\w{0,12}|"
    r"apart\w{0,12}|reserv\w{0,12})\b"
)
_SALDO_RE = re.compile(r"\b(?:saldos?|restantes?|resto|faltante|falta\w{0,12}|pendientes?)\b")
_NINOS_RE = re.compile(
    r"\b(?:ninos?|ninas?|bebes?|menores?|hij[oa]s?|nen[ea]s?|chiquit\w{0,12}|pequen\w{0,12}|"
    r"infantes?|anos|silla|seguro)\b"
)
_DIFERENCIA_RE = re.compile(r"\b(?:mas|diferencia|adicional\w{0,12}|extra|sube\w{0,12}|demas)\b")


def _contexto(texto: str, pct: Optional[int]) -> _Contexto:
    """Qué derivados admite el monto, mirando su frase y la anterior («El
    anticipo es del 30 %. Serían $151.500»)."""
    anticipo = bool(_ANTICIPO_RE.search(texto))
    saldo = bool(_SALDO_RE.search(texto))
    if pct:
        anticipo = anticipo or bool(
            re.search(rf"\b{pct}\s{{0,3}}(?:%|por\s{{0,3}}ciento)", texto))
        saldo = saldo or bool(
            re.search(rf"\b{100 - pct}\s{{0,3}}(?:%|por\s{{0,3}}ciento)", texto))
    return _Contexto(anticipo=anticipo, saldo=saldo,
                     diferencia=bool(_DIFERENCIA_RE.search(texto)),
                     ninos=bool(_NINOS_RE.search(texto)))


#: «anticipo del 40%», «el anticipo es del *50%*», «40 % de anticipo»: el
#: porcentaje se compara con `extras["anticipo_pct"]` (QA: el bot inventó 50 %
#: y 40 %). Entre la palabra y el número caben unas pocas palabras cortas.
_PCT_ANTICIPO_RE = re.compile(
    r"\b(?:anticipo|adelanto|abono|cuota\s{1,3}inicial)\w{0,2}"
    r"(?:[\s*_]{1,4}(?:es|seria|sería|del?|un|el|de\s{1,3}un|equivale\s{1,3}al?)){0,3}"
    r"[\s*_]{1,4}(?P<n1>\d{1,3})[\s*_]{0,3}(?:%|por\s{1,3}ciento)"
    r"|(?<![\d.,])(?P<n2>\d{1,3})[\s*_]{0,3}(?:%|por\s{1,3}ciento)[\s*_]{1,4}"
    r"(?:de|del|como|para\s{1,3}el)?[\s*_]{0,4}(?:anticipo|adelanto|abono|cuota\s{1,3}inicial)\b"
)
#: Lenguaje de presupuesto del cliente (regla 0, auditoría M1).
#: Acotado a frases que presentan una cifra como lo que el cliente TIENE, no
#: como lo que algo cuesta: «tienes» o «tus» sueltos dejaban pasar «te queda
#: en tus $200.000» (re-auditoría M1).
_PRESUPUESTO_RE = re.compile(
    r"\b(?:presupuesto|cuentas\s{1,3}con|con\s{1,3}(?:tus|sus|esos|los)\s"
    r"|tienes\s{1,3}(?:como|unos|hasta|disponibles?)|mencionaste|dijiste|"
    r"comentaste|tu\s{1,3}monto)"
)
#: «Con $350.000 no alcanza…»: «con» pegado al monto también presenta la
#: cifra como lo que el cliente tiene. Solo cuenta justo antes del monto (no
#: en la frase), y pasa por los mismos candados de M1: sin confirmación, sin
#: verbo de precio y, si la frase nombra una salida, con el precio real al lado.
_CON_MONTO_RE = re.compile(r"\bcon\s{0,3}[*_]{0,2}$")
#: «Solo te pasas $19.000», «apenas $19.000 más de tu presupuesto»: la
#: diferencia entre un precio y el presupuesto del cliente (QA 2026-10-07).
#: Tiene que ir PEGADA al monto, antes («solo te pasas $19.000», «se te pasa
#: solo $19.000») o justo después («$19.000 más de tu presupuesto»). Una
#: palabra suelta en cualquier parte de la frase dejaba pasar «…te queda en
#: $200.000 y no te pasas» (re-auditoría M1).
_DIF_ANTES_RE = re.compile(
    r"\b(?:pas[ao]s?|falta\w{0,4}|sobra\w{0,4}|diferencia\s{1,3}de|encima)"
    r"\s{0,3}(?:en\s|de\s|solo\s|apenas\s)?[\s$*_]{0,3}$"
)
_DIF_DESPUES_RE = re.compile(
    r"^[*_]{0,2}\s{0,3}(?:mas|por\s{1,3}encima)\s{1,3}de\s{1,3}(?:tu|su)\s{1,3}presupuesto\b"
)
#: «Tienes razón, $200.000»: el bot le da la razón al cliente sobre un precio.
#: Con esto en la frase, la cifra del cliente no se acepta como tal.
_CONFIRMA_RE = re.compile(
    r"\b(?:raz[oó]n|confirm\w{0,12}|correcto|as[ií]\s{1,3}es|exacto|efectivamente"
    r"|claro\s{1,3}que\s{1,3}s[ií])\b"
)
#: Verbo de precio justo antes del monto: «te queda en tus $200.000» es un
#: precio, no un presupuesto.
_VERBO_PRECIO_RE = re.compile(r"\b(?:queda\w{0,3}|cuesta\w{0,3}|vale\w{0,3}|sale\w{0,3}|precios?|valor\w{0,3}|tarifas?)\b")


_ClaveFecha = Tuple[Optional[int], Optional[int], Optional[int]]   # (mes, ini, fin)


def _casa(fila: Fila, fecha: _ClaveFecha, con_fin: bool) -> bool:
    mes, ini, fin = fecha
    if mes is not None and fila.mes is not None and fila.mes != mes:
        return False
    if ini is not None and fila.dia_ini != ini:
        return False
    if con_fin and fin is not None and fila.dia_fin != fin:
        return False
    return True


def _filas_que_casan(filas: Sequence[Fila], hoteles: Iterable[str],
                     fechas: Iterable[_ClaveFecha]) -> List[Fila]:
    hoteles, fechas = list(hoteles), list(fechas)
    candidatas = [f for f in filas if not hoteles or f.hotel in hoteles]
    if not fechas:
        return candidatas
    for con_fin in (True, False):
        casan = [f for f in candidatas if any(_casa(f, d, con_fin) for d in fechas)]
        if casan:
            return casan
    return []


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _pesos(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def _describir(filas: Sequence[Fila], acom: Set[str]) -> str:
    partes = []
    for f in filas[:3]:
        precios = []
        if not acom or "multiple" in acom:
            precios.append(f"múltiple {_pesos(f.multiple)}")
        if not acom or "doble" in acom:
            precios.append(f"doble {_pesos(f.doble)}")
        partes.append(
            f"{_NOMBRE_HOTEL.get(f.hotel, f.hotel)} {f.etiqueta}: "
            + " · ".join(precios)
        )
    return "; ".join(partes)


def viola_precio(
    texto_bot: str,
    *,
    resultados_precios: list[str],
    desde_validos: set[int],
    cifras_cliente: set[int],
    extras: dict,
) -> str | None:
    """None si todo monto del mensaje es válido; si no, una explicación corta
    para la corrección del modelo (sin datos del cliente).

    `resultados_precios`: textos COMPLETOS (no el recorte de 300 de la
    bitácora) de `consultar_tarifario` o `consultar_precios`.
    `desde_validos`: los «desde» que el bot puede anunciar sin consultar (p. ej.
    `tarifario.desde_temporada(hoy)` de la vitrina).
    `cifras_cliente`: montos que escribió el cliente (ver `extraer_montos`).
    `extras`: `tarifario.extras()`.
    """
    plano = _plano(texto_bot or "")
    pct = _pct(extras)
    if pct:
        for m in _PCT_ANTICIPO_RE.finditer(plano):
            n = int(m.group("n1") or m.group("n2"))
            if n != pct:
                return (
                    f"Escribiste un anticipo del {n}%, pero el anticipo para "
                    f"separar es del {pct}%. Reescribe el mensaje con ese "
                    "porcentaje."
                )
    montos = _montos(plano)
    if not montos:
        return None

    resultados = [r for r in (resultados_precios or []) if r]
    filas = filas_de_resultados(resultados)
    directos = _directos(resultados)
    ninos = _sumas_ninos(extras)
    extras_ok = _valores_extras(extras) | {s for s in ninos if s}
    cliente = {int(x) for x in (cifras_cliente or set())}
    minimo = min((min(f.multiple, f.doble) for f in filas), default=None)
    # El «desde» de temporada es el de la vitrina: vale mientras no se haya
    # consultado nada. Con filas consultadas (se habló de un mes, una fecha o
    # un presupuesto) solo vale si es el mínimo de lo consultado — si no, «En
    # octubre… desde $369.000» pasaba con el mínimo de diciembre (QA).
    desde_ok = {int(x) for x in (desde_validos or set())}
    if filas:
        desde_ok = {x for x in desde_ok if x == minimo}

    frases = _frases(plano)
    inicios = [a for a, _ in frases]
    lineas = _Lineas(plano)
    hoteles = _Menciones(_hoteles(plano))
    fechas = _Menciones([(f.pos, (f.mes, f.ini, f.fin)) for f in _fechas(plano)])
    acoms = _Menciones(_acomodaciones(plano))

    # Todo lo que depende solo de la frase se calcula una vez por frase, y los
    # conjuntos válidos una vez por combinación: lineal en el largo del texto.
    por_frase: Dict[int, Tuple[Any, ...]] = {}
    validos: Dict[Tuple[Any, ...], _Validos] = {}
    casan_cache: Dict[Tuple[frozenset, frozenset], List[Fila]] = {}

    def _de_frase(i: int) -> Tuple[Any, ...]:
        if i not in por_frase:
            a, b = frases[i]
            previa = frases[i - 1][0] if i > 0 else a
            h = frozenset(hoteles.en(a, b))
            f = frozenset(fechas.en(a, b))
            ac = frozenset(acoms.en(a, b))
            por_frase[i] = (
                _contexto(plano[previa:b], pct),
                bool(h or f or ac),
                bool(_PRESUPUESTO_RE.search(plano[a:b])),
                h, f, ac,
                bool(_CONFIRMA_RE.search(plano[a:b])),
            )
        return por_frase[i]

    def _casan(h: frozenset, f: frozenset) -> List[Fila]:
        if (h, f) not in casan_cache:
            casan_cache[(h, f)] = _filas_que_casan(filas, h, f)
        return casan_cache[(h, f)]

    def _validos(casan: Sequence[Fila], acom: Set[str], con_ninos: bool) -> _Validos:
        clave = (tuple(id(f) for f in casan), frozenset(acom), con_ninos)
        if clave not in validos:
            validos[clave] = _validos_de(casan, acom, ninos if con_ninos else {0}, pct)
        return validos[clave]

    difs_cliente = sorted({
        abs(p_ - c) for f in filas for p_ in (f.multiple, f.doble) for c in cliente
    })
    montos_por_frase: Dict[int, List[_Monto]] = {}
    for m in montos:
        montos_por_frase.setdefault(
            max(0, bisect.bisect_right(inicios, m.inicio) - 1), []
        ).append(m)

    for monto in montos:
        v = monto.valor
        i = max(0, bisect.bisect_right(inicios, monto.inicio) - 1)
        (ctx, nombra_fila, habla_de_presupuesto, h_frase, f_frase, a_frase,
         confirma) = _de_frase(i)

        # 0. Lo que dijo el cliente (su presupuesto). Solo si se habla de su
        # presupuesto: justo antes del monto («con tus 450 mil»), o en una
        # frase que NO nombra hotel / salida / acomodación. Si la frase nombra
        # una fila y el monto no viene presentado como presupuesto, manda la
        # regla 3: «En Amor de Dios en doble te queda en $200.000» no pasa
        # porque el cliente haya dicho 200 mil (auditoría M1).
        if v in cliente or any(
            abs(c / n - v) <= _TOLERANCIA for c in cliente
            for n in range(2, _MAX_PERSONAS + 1)
        ):
            ventana = plano[max(0, monto.inicio - 30):monto.inicio]
            cerca = bool(_PRESUPUESTO_RE.search(ventana) or _CON_MONTO_RE.search(ventana))
            verbo = _VERBO_PRECIO_RE.search(plano[max(0, monto.inicio - 25):monto.inicio])
            if not confirma and not verbo:
                if habla_de_presupuesto and not nombra_fila:
                    continue
                if cerca:
                    if not nombra_fila:
                        continue
                    # La frase nombra una salida: el eco del presupuesto solo
                    # vale si la misma frase trae el precio real de esa salida
                    # («Con tus 450 mil te alcanza el 16 al 19…, que queda en
                    # $459.000»). Sin él, «Con tus $200.000 te alcanza la doble
                    # del 6 al 9» le promete una salida que vale $505.000.
                    casan = _casan(
                        _atributos(monto.inicio, h_frase, hoteles, lineas),
                        _atributos(monto.inicio, f_frase, fechas, lineas),
                    )
                    # Sin fila que case (salida no consultada): NO pasa por
                    # aquí; sigue con las reglas 1→5 (re-auditoría M1).
                    ok = _validos(casan, set(a_frase), ctx.ninos) if casan else None
                    a, b = frases[i]
                    if ok is not None and any(
                        o is not monto and a <= o.inicio < b and o.valor not in cliente
                        and ok.contiene(o.valor, ctx)
                        for o in montos_por_frase.get(i, ())
                    ):
                        continue
        # 0b. Lo que le falta (o le sobra) al presupuesto del cliente para una
        # salida consultada: «Solo te pasas $19.000». Solo con la palabra de
        # diferencia pegada al monto, sin verbo de precio delante y sin
        # confirmación. Si la frase nombra una salida que casa, la diferencia
        # se calcula solo contra esa salida.
        if difs_cliente and not confirma and (
            _DIF_ANTES_RE.search(plano[max(0, monto.inicio - 20):monto.inicio])
            or _DIF_DESPUES_RE.search(plano[monto.fin:monto.fin + 40])
        ) and not _VERBO_PRECIO_RE.search(plano[max(0, monto.inicio - 25):monto.inicio]):
            difs = difs_cliente
            h_dif = _atributos(monto.inicio, h_frase, hoteles, lineas)
            f_dif = _atributos(monto.inicio, f_frase, fechas, lineas)
            if h_dif or f_dif or a_frase:
                # Con la salida nombrada (en la frase o heredada de la
                # anterior), la diferencia es contra ESA salida.
                casan = _casan(h_dif, f_dif)
                if casan:
                    acom = set(a_frase)
                    precios = [
                        p_ for f in casan for p_, nom in ((f.multiple, "multiple"), (f.doble, "doble"))
                        if not acom or nom in acom
                    ]
                    difs = sorted({abs(p_ - c) for p_ in precios for c in cliente})
            k = bisect.bisect_left(difs, v - _TOLERANCIA)
            if k < len(difs) and difs[k] <= v + _TOLERANCIA:
                continue
        # 1. Extras (niños, itinerario).
        if v in extras_ok:
            continue
        # 2. «desde».
        antes = plano[max(0, monto.inicio - 40):monto.inicio]
        if _DESDE_RE.search(antes):
            if v in desde_ok or (minimo is not None and v >= minimo):
                continue
            minimos = sorted(desde_ok | ({minimo} if minimo else set()))
            return (
                f"Anunciaste un «desde» de {_pesos(v)} que no sale del tarifario"
                + (f": los mínimos válidos son {', '.join(_pesos(x) for x in minimos)}."
                   if minimos else ". Consulta los precios antes de dar un «desde».")
                + " Reescribe el mensaje con el valor que devolvió la herramienta."
            )

        h_attr = _atributos(monto.inicio, h_frase, hoteles, lineas)
        f_attr = _atributos(monto.inicio, f_frase, fechas, lineas)
        a_attr = set(a_frase)

        # 3. Con atributos: la fila que nombró.
        if filas and (h_attr or f_attr or a_attr):
            casan = _casan(h_attr, f_attr)
            if casan:
                if _validos(casan, a_attr, ctx.ninos).contiene(v, ctx):
                    continue
                return (
                    f"Cotizaste {_pesos(v)}, pero para lo que nombraste el "
                    f"tarifario consultado dice: {_describir(casan, a_attr)} "
                    "(por persona). Es el precio de otra fila. Reescribe el "
                    "mensaje con el valor exacto de esa salida y acomodación."
                )

        # 4. Sin atributos (o sin fila que case): cualquier cifra consultada.
        if v in directos or v in desde_ok:
            continue
        if filas:
            if _validos(filas, set(), ctx.ninos).contiene(v, ctx):
                continue
            return (
                f"Escribiste {_pesos(v)}, que no sale del tarifario consultado "
                "ni de sus cálculos (personas, niños, anticipo o saldo). "
                "Reescribe el mensaje solo con valores que devolvió la "
                "herramienta."
            )
        # 5. Sin consulta.
        return (
            f"Escribiste {_pesos(v)} sin haber consultado los precios. Consulta "
            "la herramienta de precios antes de dar una cifra, o quita el valor."
        )
    return None
