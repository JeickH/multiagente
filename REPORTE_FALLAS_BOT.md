# Reporte de fallas — bot de Recupera Tu Mascota

**Fecha:** 2026-08-14 · **Estado:** las tres corregidas y desplegadas en producción.

Tres fallas encontradas revisando conversaciones reales. Las tres tenían la misma raíz:
**el modelo escribía datos que nadie le había dado**. Se corrigieron con guardarraíles
que no dependen de que el modelo "se porte bien" — el servidor verifica y bloquea.

---

## Falla 1 — El bot inventó un número de teléfono

### Qué pasó
En una prueba, alguien confirmó que reconocía a su mascota y el bot respondió con
ubicación y teléfono de contacto. El teléfono **no existía en la base de datos**: se lo
inventó completo, con formato colombiano válido.

| Lo que dijo el bot | Lo que decía el reporte |
|---|---|
| `3012458967` | `+57 315 802 4471` (Julián Ospina) |
| "San Fernando, cerca del parque central" | "Parque de San Fernando, frente a la panadería" |

### Por qué importa
Es la peor falla posible en este servicio. Una familia angustiada marca un número
equivocado, molesta a un desconocido y pierde el rastro de su mascota. Y como el bot
suena seguro, nadie sospecha que el dato es falso.

### Por qué pasó
El modelo tenía el patrón de la conversación aprendido ("confirmó → dar contacto") y lo
completó de memoria en vez de llamar a la herramienta que consulta la base.

### Cómo se corrigió
Un guardarraíl en el motor (`_viola_contacto`): **si el bot escribe algo que parece un
teléfono y no llamó a `entregar_contacto` en ese mismo turno, el mensaje se descarta
antes de enviarse** y se le exige usar la herramienta. Máximo dos correcciones por turno.

No es una instrucción que el modelo pueda ignorar: es una verificación del servidor sobre
el texto ya generado. Verificado: hoy los datos que entrega son idénticos a los de la
base.

---

## Falla 2 — El bot describía mascotas que no había consultado

### Qué pasó
Conversación real (13 de agosto). La persona buscaba un **perro salchicha café** perdido
en **Valle del Lili**. El bot le presentó el reporte MC-00021 así:

> "Mira la última: perro salchicha, café, tamaño pequeño. Lo encontraron el 12 de agosto
> en la zona de Valle del Lili."

MC-00021 en la base es un **mestizo café oscuro con manchas, encontrado en Cra. 56
#7oeste-445, barrio Guadalupe**. Ni la raza, ni el tamaño, ni el lugar eran ciertos.

**El bot le devolvió su propia descripción como si fuera la del reporte.** La persona
dijo "sí, es mío" — y lo era o no, pero no por lo que el bot le contó.

### El detalle que delata la causa
En esa misma conversación, los turnos donde el bot **sí** consultó la ficha describieron
todo bien:

| Turno | ¿Consultó la ficha? | Descripción |
|---|---|---|
| MC-00024 | Sí | "Bulldog Francés, café con manchas atigradas… Carrera 56 #7 oeste-445" ✅ |
| MC-00022 | Sí | "mestizo, blanco con manchas café… Carrera 56 #7 oeste-445" ✅ |
| MC-00021 | **No** | "salchicha, café, pequeño… Valle del Lili" ❌ |
| "¿dónde está?" | **No** | "Está en el sector de Meléndez, donde se te perdió" ❌ |

Cuando quería mostrar "la siguiente" sin llamar a la herramienta, rellenaba los huecos
con lo último que había leído: las palabras de la propia persona.

### Cómo se corrigió
El mismo mecanismo que para el teléfono. Ahora, **si el bot presenta una mascota
—"mira esta otra", "¿es este tu perro?", "lo encontraron en…"— sin haber consultado su
ficha en ese turno, el mensaje se descarta** y se le exige llamar a `ver_ficha` y
describir solo lo que devuelva.

Probado contra los seis escenarios del caso real: bloquea las dos frases que fallaron y
deja pasar las descripciones legítimas y las preguntas normales.

Además, en las instrucciones del bot quedó escrito con el ejemplo concreto: *"si busca un
salchicha café en Valle del Lili, no digas que encontraste un salchicha café en Valle del
Lili a menos que la ficha lo diga"*.

---

## Falla 3 — Las mascotas de otras plataformas no mostraban foto

### Qué pasó
Los reportes traídos de Patitas a Casa llegaban al chat **sin imagen**: la persona recibía
un enlace a la otra plataforma en vez de ver al animal.

### Por qué pasó
Fue un error mío de diseño. Cuando escribí la función que muestra una ficha, asumí que
los reportes importados nunca tendrían imagen propia:

```python
if ficha.get("externo"):
    return ...      # ← salía ANTES de enviar la foto
```

Cierto para Mascotas por Colombia (de ahí solo enlazábamos), pero **falso para Patitas a
Casa: de esos 15 sí habíamos copiado la imagen a nuestro servidor**. Estaban guardadas y
accesibles — el bot simplemente nunca las mandaba.

Antes de tocar nada verifiqué que no fuera un problema de almacenamiento: hice un barrido
HTTP de las 45 fotos en producción y **las 45 respondían correctamente**. El problema era
de lógica, no de archivos.

### Cómo se corrigió
1. La foto se envía **siempre que exista**, venga el reporte de donde venga. El enlace al
   origen queda para los datos de contacto, no para ver la imagen.
2. El importador de Mascotas por Colombia **ahora también copia las fotos**, para que sus
   casos dejen de llegar sin imagen. Verificado con dos reportes reimportados.
3. Si un caso no tiene foto nuestra, el bot lo dice y comparte el enlace — pero ya no
   manda a nadie a otro sitio a ver algo que ya tiene enfrente.

---

## Qué queda de todo esto

**El patrón.** Las tres fallas fueron el modelo llenando huecos con lo que sonaba
razonable. La lección: en un servicio donde un dato falso manda a una persona a la
dirección equivocada, **las instrucciones no alcanzan**. Todo dato que el bot afirme sobre
un caso concreto tiene que venir de una consulta verificable, y el servidor tiene que
poder comprobarlo.

**Cómo se detectaron.** Las tres salieron de leer conversaciones reales, no de las
pruebas. Por eso el registro de conversaciones del panel —con los caminos que tomó el
bot— es la herramienta de calidad más valiosa que tiene el módulo hoy.

**Lo que sigue abierto.** El guardarraíl detecta que el bot describe sin consultar, pero
no puede verificar que lo que describe *coincida* con la ficha cuando sí consultó. Eso
requeriría comparar el texto contra los campos del reporte — factible, y sensato si
aparece un caso.
