"""Un escritor de PDF mínimo, sin dependencias.

Por qué a mano y no con `reportlab`/`weasyprint`
------------------------------------------------
La factura que hay que emitir es una página de texto con dos filas de tabla y
un logo tipográfico. `reportlab` son ~15 MB en la imagen de ECS y `weasyprint`
arrastra Cairo, Pango y GObject por apt — para dibujar quince líneas rectas.
Un PDF de texto plano es un formato sencillo de escribir y acá cabe completo
en un archivo que se lee de una sentada.

Lo que este módulo NO hace, y hay que saberlo antes de pedírselo: imágenes,
salto de página automático, tablas que se acomodan solas, ni fuentes
incrustadas. Si mañana la factura necesita el logo en PNG o crece a varias
páginas, la respuesta correcta es traer una librería, no estirar esto.

Las fuentes son las **base 14** que todo lector de PDF trae de fábrica
(Helvetica y Helvetica-Bold), declaradas con `/WinAnsiEncoding`: por eso las
tildes y la eñe salen bien sin incrustar nada, y por eso el texto se codifica
en latin-1 al escribirlo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

#: Tamaño carta en puntos (1 punto = 1/72 de pulgada). Carta y no A4 porque es
#: el papel que se usa en Colombia.
ANCHO_CARTA = 612.0
ALTO_CARTA = 792.0

#: Las dos fuentes disponibles, con el nombre con el que se piden acá.
NORMAL = "normal"
NEGRILLA = "negrilla"

_RECURSO_FUENTE = {NORMAL: "/F1", NEGRILLA: "/F2"}

#: Anchos de los glifos de Helvetica, en milésimas de em, para poder medir el
#: texto (alinear a la derecha una columna de valores necesita saber cuánto
#: mide cada número). Solo se tabulan los caracteres que salen en una factura;
#: cualquier otro usa el ancho promedio, que para alinear un renglón corto no
#: se nota.
_ANCHO_PROMEDIO = 556
_ANCHOS = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, "0": 556, "1": 556, "2": 556, "3": 556, "4": 556,
    "5": 556, "6": 556, "7": 556, "8": 556, "9": 556, ":": 278, ";": 278,
    "=": 584, "?": 556, "@": 1015, "[": 278, "]": 278, "_": 556,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
}


def ancho_texto(texto: str, tamaño: float, *, fuente: str = NORMAL) -> float:
    """Cuánto mide el texto en puntos. Helvetica-Bold es ~6% más ancha."""
    milesimas = sum(_ANCHOS.get(c, _ANCHO_PROMEDIO) for c in texto)
    factor = 1.06 if fuente == NEGRILLA else 1.0
    return milesimas / 1000.0 * tamaño * factor


def _escapar(texto: str) -> bytes:
    """Texto → bytes listos para ir dentro de `(...)` en el contenido.

    Los tres caracteres que hay que neutralizar son `\\`, `(` y `)`: sin eso un
    paréntesis en el concepto («Implementación (fase 1)») cierra la cadena
    antes de tiempo y el PDF queda ilegible. El `errors="replace"` es la red
    de seguridad para un carácter fuera de latin-1 (un emoji pegado en el
    concepto): sale un `?` en vez de tumbar la descarga de la factura.
    """
    crudo = (
        texto.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    )
    return crudo.encode("latin-1", errors="replace")


@dataclass
class Pagina:
    """Una página en construcción: se le van agregando órdenes de dibujo.

    Las coordenadas son las del PDF — el origen está **abajo a la izquierda**
    y la `y` crece hacia arriba. Quien llama trabaja con un cursor que baja, y
    por eso lleva su propia `y` restando.
    """

    ancho: float = ANCHO_CARTA
    alto: float = ALTO_CARTA
    _ordenes: List[bytes] = field(default_factory=list)

    def texto(
        self,
        contenido: str,
        x: float,
        y: float,
        *,
        tamaño: float = 10.0,
        fuente: str = NORMAL,
        gris: float = 0.0,
    ) -> None:
        """Escribe una línea. `gris` va de 0 (negro) a 1 (blanco)."""
        self._ordenes.append(
            b"BT %.2f %.2f %.2f rg %s %.2f Tf %.2f %.2f Td (%s) Tj ET"
            % (
                gris, gris, gris,
                _RECURSO_FUENTE.get(fuente, "/F1").encode("ascii"),
                tamaño, x, y,
                _escapar(contenido),
            )
        )

    def texto_derecha(
        self,
        contenido: str,
        x_derecha: float,
        y: float,
        *,
        tamaño: float = 10.0,
        fuente: str = NORMAL,
        gris: float = 0.0,
    ) -> None:
        """Escribe una línea terminándola en `x_derecha`. Para los valores."""
        x = x_derecha - ancho_texto(contenido, tamaño, fuente=fuente)
        self.texto(contenido, x, y, tamaño=tamaño, fuente=fuente, gris=gris)

    def linea(
        self, x1: float, y1: float, x2: float, y2: float, *, gris: float = 0.8
    ) -> None:
        self._ordenes.append(
            b"%.2f %.2f %.2f RG 0.6 w %.2f %.2f m %.2f %.2f l S"
            % (gris, gris, gris, x1, y1, x2, y2)
        )

    def rectangulo(
        self, x: float, y: float, ancho: float, alto: float, *, rgb: Tuple[float, float, float]
    ) -> None:
        r, g, b = rgb
        self._ordenes.append(
            b"%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (r, g, b, x, y, ancho, alto)
        )

    def contenido(self) -> bytes:
        return b"\n".join(self._ordenes)


def construir(paginas: List[Pagina], *, titulo: str = "") -> bytes:
    """Arma el archivo PDF completo a partir de las páginas dibujadas.

    Escribe los objetos en orden y va anotando en qué byte empieza cada uno:
    esa tabla de posiciones (la `xref`) es lo que le permite al lector saltar
    a un objeto sin leer el archivo entero, y es lo único delicado del
    formato. Si las posiciones no cuadran, los lectores estrictos rechazan el
    archivo aunque el contenido esté bien.
    """
    if not paginas:
        paginas = [Pagina()]

    objetos: List[bytes] = []

    def agregar(cuerpo: bytes) -> int:
        objetos.append(cuerpo)
        return len(objetos)  # los números de objeto arrancan en 1

    # Se reservan los números por adelantado porque el árbol se referencia en
    # los dos sentidos: la página apunta a /Pages y /Pages lista a las páginas.
    num_catalogo = 1
    num_pages = 2
    num_fuente_normal = 3
    num_fuente_negrilla = 4
    primer_num_pagina = 5
    nums_pagina = [primer_num_pagina + i * 2 for i in range(len(paginas))]

    kids = b" ".join(b"%d 0 R" % n for n in nums_pagina)
    agregar(b"<< /Type /Catalog /Pages %d 0 R >>" % num_pages)
    agregar(
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(paginas))
    )
    agregar(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>"
    )
    agregar(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        b"/Encoding /WinAnsiEncoding >>"
    )

    for pagina, num in zip(paginas, nums_pagina):
        flujo = pagina.contenido()
        agregar(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
            b"/Contents %d 0 R >>"
            % (
                num_pages, pagina.ancho, pagina.alto,
                num_fuente_normal, num_fuente_negrilla,
                num + 1,
            )
        )
        agregar(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(flujo), flujo))

    num_info = agregar(
        b"<< /Title (%s) /Producer (Gloma) >>" % _escapar(titulo)
    )

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posiciones: List[int] = []
    for i, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % i + cuerpo + b"\nendobj\n"

    inicio_xref = len(salida)
    salida += b"xref\n0 %d\n" % (len(objetos) + 1)
    salida += b"0000000000 65535 f \n"
    for posicion in posiciones:
        salida += b"%010d 00000 n \n" % posicion
    salida += (
        b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objetos) + 1, num_catalogo, num_info, inicio_xref)
    )
    return bytes(salida)
