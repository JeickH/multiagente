# Copy de la landing: percepción de valor (Fase 1)

> **Reemplazado en buena parte por [`docs/landing-valor/AJUSTES_CEO.md`](../../docs/landing-valor/AJUSTES_CEO.md)
> (2026-10-26).** Siguen vigentes de aquí: el 70 % con su nota al pie y el bloque de garantía.
> La tabla de 22 filas y las opciones de «No necesitas saber de tecnología» quedaron descartadas.

> Borrador para revisión del CEO. Rama `feature/landing-valor`. **No se toca `gloma.tsx` hasta
> que el CEO apruebe este copy.**
>
> - Autor: Belfort (ventas). Voz revisada con la guía de `.claude/agents/community-manager.md`
>   y `docs/landing-valor/BRIEF_MARCA.md` (en esta sesión no hubo cómo lanzar al
>   `community-manager` como subagente; la revisión de voz y de las 8 marcas de agua la hizo
>   Belfort con su guía, y queda al final del archivo).
> - Fuentes que el copy no contradice: `FAQ`, `PASOS_INICIO`, `FEATURES`, `STATS`, `PRECIOS` y
>   `ComoEmpezarSection` de `frontend/pages/gloma.tsx`, y la sección 4 del brief.
> - Decisiones del CEO aplicadas: D1 (70 % con su base), D2 (garantía sin plazo en días),
>   D3 (pagos e inventario), D4 (PDF directo, sin formulario).
> - Lo que va entre `[CONFIRMAR: …]` no sale a la página hasta que el CEO lo confirme. La lista
>   completa está al final.

Orden propuesto dentro de Precios: texto de entrada → **línea de retorno (1c)** → los 3 cobros →
**tabla «Todos los paquetes incluyen» (1a)** → **garantía (1d)** → CTA final con **el botón del PDF**.

---

## 1a. Tabla «Todos los paquetes incluyen»

Va dentro de Precios, después de los 3 cobros. En escritorio, 4 columnas (función · 600 · 2.000 ·
6.000) con ✓ en todas. En móvil (375 px) colapsa a una sola lista con ✓ bajo el título
«Incluido en los 3 paquetes».

**Título:** Todos los paquetes incluyen

**Entrada:** Todas las funciones vienen en todos los paquetes. Lo único que cambia es cuántas
conversaciones traes.

**Encabezado de columnas:** `600 conversaciones` · `2.000 conversaciones` · `6.000 conversaciones`
(el de 2.000 conserva la marca de recomendado en Golden Hour, como en las tarjetas).

| Grupo | Fila (texto visible) | 600 | 2.000 | 6.000 |
|---|---|:-:|:-:|:-:|
| **Vende y atiende** | Atiende tu WhatsApp de día y de noche | ✓ | ✓ | ✓ |
| | Busca en tu catálogo de planes o productos | ✓ | ✓ | ✓ |
| | Cotiza con tus tarifas | ✓ | ✓ | ✓ |
| | Toma los datos del pedido o la reserva y los deja en tu Google Sheets | ✓ | ✓ | ✓ |
| | Comparte tus formas de pago o tu link de pago | ✓ | ✓ | ✓ |
| | Con Shopify, consulta si un pedido ya está pagado | ✓ | ✓ | ✓ |
| | Consulta qué planes o productos tienes en tu catálogo | ✓ | ✓ | ✓ |
| | Le vuelve a escribir a quien dejó de contestar | ✓ | ✓ | ✓ |
| | Le pasa el cliente a tu asesor con todo el historial | ✓ | ✓ | ✓ |
| **Asistentes** | Asistente de ventas y servicio al cliente | ✓ | ✓ | ✓ |
| | Agenda citas y llamadas con tu equipo | ✓ | ✓ | ✓ |
| **Tu plataforma** | Bandeja de mensajes para tu equipo | ✓ | ✓ | ✓ |
| | Campañas por WhatsApp | ✓ | ✓ | ✓ |
| | Tus contactos entran desde Excel | ✓ | ✓ | ✓ |
| | Simulador para probar tu agente antes de salir | ✓ | ✓ | ✓ |
| | Tablero con tus ventas y abandonos | ✓ | ✓ | ✓ |
| **Acompañamiento** | Instalación hecha por nuestro equipo | ✓ | ✓ | ✓ |
| | Ajustes durante los primeros 10 días | ✓ | ✓ | ✓ |
| | Garantía de que todo queda funcionando como quieres | ✓ | ✓ | ✓ |
| | Soporte 24/7 | ✓ | ✓ | ✓ |
| | Mantenimiento y actualizaciones incluidos | ✓ | ✓ | ✓ |

Notas para implementar (no son texto visible):
- «Campañas por WhatsApp» está en todos los paquetes, pero se paga por mensaje enviado (cobro 03).
  La tabla no lo repite: el cobro 03 está justo arriba.
- Cambios frente a la sugerencia del plan: «atención por conversación» pasó a «Asistente de ventas y
  servicio al cliente» (el nombre del cobro 02; «por conversación» se leía como forma de cobro); se
  agregó «Tus contactos entran desde Excel» porque es una pregunta frecuente y ya está en `FAQ`.
- Ninguna fila dice «integración»: Shopify se nombra como tienda, igual que en `FEATURES`.

---

## 1b. «No necesitas saber de tecnología»

Va dentro de `ComoEmpezarSection`, **debajo de los 4 pasos**, como cierre de la sección. Los 4
pasos dicen *cuándo* pasa cada cosa; este bloque dice *quién hace qué*. Por eso no repite la ruta.

**Título común a las 3 opciones (H3):** No necesitas saber de tecnología

### Opción 1 · Dos columnas: tu lista corta, la nuestra larga (la recomendada)

**Entrada:** Tu parte es contarnos cómo vende tu agencia. La técnica corre por nuestra cuenta.

| Lo que haces tú | Lo que hacemos nosotros |
|---|---|
| Una reunión para contarnos cómo vendes | Configuramos el agente con tus destinos, tarifas y el tono de tu marca |
| Nos compartes tus tarifas, itinerarios y políticas | Lo entrenamos con los mensajes y guiones que ya usa tu equipo |
| Nos das acceso a tu WhatsApp de empresa. Te guiamos paso a paso | Conectamos tu número de WhatsApp |
| Pruebas tu agente en el simulador y nos das el visto bueno | Cargamos tus contactos desde tu Excel |
| | Lo probamos contigo antes de que hable con el primer cliente |
| | Ajustamos los detalles durante los primeros 10 días |
| | Lo mantenemos al día, con soporte 24/7 |

**Cierre (CTA):** botón «Agendar una llamada» (`TEXTOS_AGENDAR.agendar`).

Por qué la recomiendo:
- **Muestra la objeción resuelta a la vista**: la columna de la izquierda es corta y la de la
  derecha es larga. El dueño que piensa «yo no sé de eso» ve en dos segundos que su parte son
  cuatro cosas que ya sabe hacer.
- **No duplica la ruta de 4 pasos**: la ruta es la línea de tiempo; esto es el reparto del trabajo.
- **No depende de ningún dato por confirmar**: todo sale de `PASOS_INICIO`, del cobro de
  Instalación y de la sección 4 del brief.
- Es el mismo reparto que sirve para la página 5 del PDF (Fase 3), así que landing y propuesta
  dicen lo mismo con las mismas palabras.
- Cambio frente al borrador del plan: el titular «Tú nos cuentas cómo vendes. Nosotros lo dejamos
  funcionando.» se quitó porque repite casi palabra por palabra el subtítulo que ya tiene la
  sección («Tu equipo nos cuenta cómo vende. Del resto nos encargamos nosotros.»).

### Opción 2 · Párrafo corto y tres momentos

**Titular:** Sin instalar nada y sin aprender a programar.

**Párrafo:** Tu agencia sigue vendiendo como siempre. Nosotros armamos el agente, lo conectamos a
tu WhatsApp y te lo entregamos probado.

**Tres momentos:**
1. **Nos reunimos.** Nos cuentas cómo vende tu equipo y nos compartes tus tarifas.
2. **Lo dejamos listo.** Lo configuramos, lo conectamos y lo pruebas en el simulador.
3. **Tu agente empieza a atender.** Y durante los primeros 10 días lo ajustamos contigo.

**Cierre:** Si algo hay que cambiar después, nos escribes por WhatsApp y lo ajustamos.

Por qué no es la primera: los tres momentos vuelven a contar, más corto, la misma ruta de 4 pasos
que está justo arriba. Si el CEO la prefiere, conviene ponerla **en lugar** del subtítulo de la
sección y no debajo de la ruta.

### Opción 3 · El tiempo del dueño

**Titular:** Tu parte toma una tarde `[CONFIRMAR: P1]`. La nuestra, el resto.

**Lo que cabe en tu tarde:**
- Una reunión para contarnos cómo vende tu agencia.
- Enviarnos tus tarifas, itinerarios y políticas.
- Darnos acceso a tu WhatsApp de empresa, con nuestra guía.

**Lo que sigue sin ti:** configuramos el agente, lo entrenamos con tus mensajes, conectamos tu
número y lo dejamos probado. Tú vuelves para revisarlo en el simulador y dar el visto bueno.

**Cierre (CTA):** botón «Agendar una llamada».

Por qué no es la primera: es la que más engancha (le habla al dueño de su tiempo, que es su dolor
de «si no estoy yo no funciona»), pero **todo descansa en «una tarde»**, que no está confirmado. La
conexión del número con Meta depende de los accesos del cliente y puede pedirle pasos en días
distintos (la `FAQ` ya lo dice en «¿Cuánto tarda en estar listo?»). Si el CEO confirma que la parte
del dueño cabe en una tarde, esta opción sube al primer lugar.

---

## 1c. Retorno de inversión: el 70 %

### Cuarta cifra para `STATS`

| Campo | Valor |
|---|---|
| `value` | `70` |
| `prefix` | `'Hasta '` |
| `suffix` | `' %'` (espacio sin corte antes del %, para que no quede solo en otra línea) |
| `label` | `menos en el costo de atención*` |
| `icon` | `medicion` (ya existe; `retorno` lo usa la cifra de 4 meses) |

Se lee: **Hasta 70 %** / menos en el costo de atención*

Orden sugerido de las 4 cifras: +150.000 mensajes · +10.000 horas · Hasta 70 % · 4 meses. Así las
dos cifras de plata quedan juntas.

**Nota al pie, debajo de las 4 cifras (Inter pequeña, centrada):**
\* Frente a atender el mismo volumen de chats solo con asesores.

En la cifra grande se cae el «un» de la frase de D1 por espacio. La frase completa, tal como la
decidió el CEO, va en Precios (abajo) y en el PDF.

### Línea para Precios

Debajo del texto de entrada de Precios, antes de los chips:

> Hasta un 70 % menos en el costo de atención\*, y tu inversión se recupera en 4 meses, en promedio.
>
> \* Frente a atender el mismo volumen de chats solo con asesores.

Notas:
- Solo usa cifras autorizadas: el 70 % (D1) y los 4 meses de retorno promedio.
- No compara con un sueldo: la base es la que fijó el CEO en D1 y la línea no pone a Gloma al lado
  de lo que gana un asesor. La cuenta con los números del prospecto (chats al mes × su tasa de
  cierre × ticket promedio) se hace en la llamada; el CTA que ya existe («¿No sabes qué paquete te
  conviene? Lo calculamos con el volumen de chats de tu agencia.») la cubre y no se toca.
- «Costo de atención» es el de la agencia, que el brief permite nombrar así. Para Gloma, «inversión».

---

## 1d. Garantía, soporte y mantenimiento

### Bloque corto para Precios (debajo de la tabla 1a)

**Titular:** Queda funcionando como tú quieres.

**Texto:** Esa es nuestra garantía. Instalamos el agente, lo probamos contigo y durante los primeros
10 días lo ajustamos con las conversaciones que van llegando. Después sigues con soporte 24/7 y
mantenimiento incluido: si algo no responde como esperas, nos escribes por WhatsApp y lo ajustamos.

**Chips (píldoras):** Garantía de funcionamiento · Soporte 24/7 · Mantenimiento incluido

Cómo cuadra con lo que ya está en la página:
- «10 días de ajuste» y «Soporte 24/7» son las etiquetas de los pasos 3 y 4 de `PASOS_INICIO`; el
  bloque usa las mismas cifras y no les agrega plazos.
- No habla de devoluciones de dinero ni de un número de días de garantía (D2).
- «Si algo no responde como esperas» se queda en el agente que ya se instaló; no promete
  conexiones nuevas a otros sistemas (esas siguen siendo a la medida, como dice la `FAQ`).

### Pregunta nueva para `FAQ`

Va justo después de «¿Cuánto tarda en estar listo?».

**Pregunta:** ¿Qué pasa después de la instalación?

**Respuesta:** Tu agente empieza a atender y durante los primeros 10 días ajustamos los detalles
con las conversaciones que van llegando. Después tienes soporte 24/7, mantenimiento incluido y
rondas de mejora con lo que muestra tu tablero. Nuestra garantía es que todo quede funcionando como
tú quieres: si algo no responde como esperas, nos escribes por WhatsApp y lo ajustamos.

Recordatorio del plan: el contexto de Lía (`backend/app/bot_contexts/gloma.md`) tiene que decir lo
mismo antes del merge, o Lía y la página se contradicen.

---

## Botón y enlace del PDF (D4)

- **Botón** (secundario, en el CTA final de Precios, al lado de «Agendar una llamada», que sigue
  siendo el principal): **Descargar propuesta comercial (PDF)**
  - `<a href="/gloma/propuesta-comercial-gloma.pdf" download>`; sin formulario.
  - Línea opcional debajo, en Inter pequeña: «Para compartirla con tu socio o tu equipo.» (Le da
    una razón a quien no decide solo. Si el CEO prefiere el CTA más limpio, se omite.)
- **Enlace en el footer** (columna «Conecta», después de Instagram):
  **Propuesta comercial (PDF) →**

---

## Revisión de las 8 marcas de agua

Revisadas una por una sobre el texto visible de este archivo, con lectura y búsqueda de palabras (titulares, filas de la tabla,
columnas, párrafos, chips, nota al pie, FAQ, botón y enlace). Las notas para el equipo no cuentan.

| # | Marca | Qué encontré | Qué hice |
|---|---|---|---|
| 1 | Guión largo de comodín | Ninguno. Lo verifiqué buscando «—» en el archivo: no aparece en el texto visible. En la opción 2, la mención de los 10 días va como frase aparte («Y durante los primeros 10 días…»), no colgada de un guión. | Sin cambios. |
| 2 | Paralelismo negativo y antítesis seca | Ningún «No es solo X, es Y». Antítesis seca «No A. B.»: ninguna en el texto visible. El contraste de la opción 3 («Tu parte toma una tarde. La nuestra, el resto.») es de reparto, no de negación. El titular de la opción 2 tiene dos «sin», que es una suma de beneficios y no una antítesis. | Sin cambios. El cupo de una antítesis por pieza queda libre. |
| 3 | Muletillas | Ninguna («cabe destacar», «sin duda», «en resumen»…). | Sin cambios. |
| 4 | «Real» / «verdadero» | Ninguno en el copy nuevo. Hallazgo fuera de alcance: la sección de contacto que ya está en la página dice «tus destinos y tarifas reales»; ahí el contraste es con una demo genérica, así que se puede defender, pero conviene que el CEO lo mire. | Sin cambios en este copy. |
| 5 | Tríos forzados | Los tríos que quedan son de cosas concretas: «destinos, tarifas y el tono de tu marca» (el mismo del cobro de Instalación), «tarifas, itinerarios y políticas», los 3 chips de garantía y los 3 momentos de la opción 2. Ninguno es de adjetivos sinónimos. | Sin cambios. |
| 6 | Vocabulario inflado y jerga | Ninguno. Busqué «potenciar», «optimizar», «maximizar», «impulsar», «robusto», «solución integral», «integración», «onboarding» y «API»: no aparecen en el texto visible (la única «integración» del archivo está en una nota para el equipo). | Sin cambios. |
| 7 | Cierre de manual | Cada bloque cierra con un dato o con el CTA: 1b con «Agendar una llamada», 1c con la nota al pie, 1d con «nos escribes y lo ajustamos», la tabla con su última fila. El cierre de la opción 2 es el que el CEO puso en el plan y es específico de Gloma. | Sin cambios. |
| 8 | Negritas en cascada y emojis | Solo hay negrita en la cifra grande de `STATS` y en los nombres de los tres momentos de la opción 2. El ✓ de la tabla es la marca de «incluido», con función, no decoración. No hay emojis. | Sin cambios. |

Otras reglas revisadas: tuteo en todo; «inversión» para Gloma, nunca «costo» ni «cuesta» (el
«costo de atención» es el de la agencia); solo cifras autorizadas (70 %, 4 meses, más las que ya
están en `STATS`); sin testimonios ni casos; nada que el producto no haga (solo WhatsApp por
escrito, el agente no cobra, no inventa precios ni cupos); sin teléfonos ni correos de personas.

---

## Decisiones del CEO sobre los pendientes (2026-10-26)

| # | Tema | Decisión |
|---|---|---|
| P1 | «Una tarde» (opción 3) | No se puede sostener: la conexión con Meta suele pedirle pasos al cliente en otro día. **Opción 3 descartada.** |
| P2 | Opción de 1b | **Opción 1** (dos columnas). La 2 queda solo en el HTML de prueba para comparar. |
| P3 | Filas de «Asistentes» | «Agenda citas y llamadas con tu equipo» **se queda**: el motor del agente ya agenda citas en un calendario con franjas (`registrar_demo`, activable por cuenta). «Asistente para empresas y grupos» **se quita**: no hay nada en el producto que lo respalde hoy. |
| P4 | Fila de inventario | «Consulta qué planes o productos tienes en tu catálogo». |
| P5 | Alcance de «lo ajustamos» | Se quitó «o cambian tus tarifas» de la FAQ: no se promete actualización de tarifas incluida hasta que el CEO lo defina. Queda «si algo no responde como esperas, lo ajustamos». |
| P6 | «Mantenimiento incluido» | Se mantiene: está en el plan del CEO («mantenimiento y actualizaciones incluidas»). |
| P7 | Canal del soporte 24/7 | WhatsApp de Gloma (público). El copy dice «nos escribes por WhatsApp». |
| P8 | «Hasta 70 %» sin «un» | Aprobado. |
| P9 | Línea bajo el botón del PDF | Se deja. |
| — | «tus destinos y tarifas reales» (contacto) | Se deja: el brief permite «real» con contraste comprobable y pone «tus tarifas reales» como ejemplo válido (marca 4). El contraste es con una demo genérica. |

Sigue abierto para el CEO: si actualizar tarifas después de los 10 días va dentro del mantenimiento (P5).
