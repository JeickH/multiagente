# Brief de marca y producto para la landing y la propuesta comercial

Resumen, para trabajar desde una sesión en la nube, del material de marca que vive fuera de git
(`ventas/`, en el equipo del CEO). **Aquí no hay citas, nombres ni cifras de prospectos**: el
repositorio es público. Si una tarea necesita la voz del cliente textual, se pide al CEO.

> Para Belfort y el Community Manager: en la nube **no existe `ventas/`**. Este archivo reemplaza
> la lectura obligatoria de `design_system_gloma.md`, la Parte 0 del plan de contenido,
> `CONTEXTO_DE_MARCA.md` y la sección 6 de la voz del cliente. No te detengas por no encontrarlos.

## 1. Audiencia

Le hablamos a **quien vende el viaje**, no al viajero: dueños de agencias de viajes, gerentes
comerciales y asesores; también hoteles y operadores turísticos de LatAm (foco Colombia y
México). Filtro de todo texto: *¿le sirve a la dueña de una agencia con 6 asesores en Medellín?*
No son técnicos: nada de "API", "LLM", "integración", "webhook", "onboarding", "IA generativa",
"solución omnicanal".

## 2. Identidad visual

| Color | Código | Uso | Nunca |
|---|---|---|---|
| Deep Forest | `#004D40` | Fondo principal y color de marca; titulares sobre claro | Texto corrido sobre negro |
| Technical Black | `#101817` | Fondo oscuro; texto sobre fondos claros | Degradados sucios con Deep Forest |
| Soft Mint | `#E0F2F1` | Fondo claro y tarjetas | Fondo de texto mint (no contrasta) |
| Algorithmic Mint | `#4DB6AC` | **Acento único**: CTAs, cifras grandes, subrayados, flechas | Texto corrido o varios protagonistas a la vez |

- Golden Hour `#F5C24B` vive en el logo; en la landing solo marca el paquete recomendado.
- Tipografía: **Syne** 700/800 para titulares y cifras (interlineado 1,05–1,15) e **Inter**
  300/400/600 para cuerpo. Nunca una tercera fuente. Paleta vieja marrón/rosa: prohibida.
- Forma: botones y chips en píldora; tarjetas con radio 24 px (16 px si va dentro de otra).
- Logo: no se deforma, no se recolorea, no va sobre fondo saturado. Archivos en
  `frontend/public/gloma/` (`logo_blancotrans.png` sobre oscuro).
- Imágenes: nada genérico (gente con maletas, banderas, mapas con chinchetas, playas
  sobresaturadas) ni caras de personas reales sin autorización.

## 3. Reglas de copy

- Tuteo, frases cortas. La primera línea es una escena, no un anuncio.
- Se habla de **inversión** en Gloma, nunca de "costo" o "cuesta". (El "costo de atención" de la
  agencia sí se nombra así.)
- **Cifras públicas autorizadas**: +150.000 mensajes gestionados · +10.000 horas de asesores IA ·
  4 meses de retorno de inversión promedio · y, por decisión del CEO del 2026-10-21, la
  reducción del **70 % en el costo de atención** (la redacción exacta es la decisión D1 del plan).
  Nada de porcentajes de conversión inventados, testimonios ni casos que no existan.
- En público no se dice "un dueño de agencia me dijo": se dice "un empresario".

### Las 8 marcas de agua de la IA (revisar antes de entregar)

Ninguna se aplica mecánicamente: la lista dice dónde mirar, no qué borrar. Prueba general: si al
borrar la palabra la frase dice lo mismo, sobraba.

1. **Guión largo de comodín.** Vale como separador (`Corporativo — 12 pasajeros`) o inciso en
   pareja. No para colgar una coletilla al final: ahí va punto.
2. **Paralelismo negativo.** «No es solo X, es Y» prohibido. La antítesis seca «No A. B.» es voz
   de marca, con cupo: **una por pieza**, nunca dos seguidas ni repetida entre piezas.
3. **Muletillas**: «cabe destacar», «es importante mencionar», «sin duda», «en resumen».
4. **«Real» / «verdadero»** solo con contraste comprobable («tus tarifas reales» sí).
5. **Tríos forzados**: tres cosas concretas sí; tres adjetivos sinónimos no.
6. **Vocabulario inflado**: fuera «potenciar», «optimizar», «maximizar», «impulsar», «robusto»,
   «sinergia», «solución integral», «profundizar», «panorama».
7. **Cierre de manual**: si el último renglón sirve para cualquier otra pieza, no es un cierre.
   Se cierra con una frase con filo o con el CTA.
8. **Negritas en cascada y emojis decorativos**: pocas negritas, para el dato que más pesa; emojis
   nunca como viñeta.

## 4. Lo que Gloma hace (y lo que no) — respuestas de producto aprobadas por el CEO

- Pone un agente de IA en el WhatsApp del negocio. En la instalación se carga el contexto del
  negocio (catálogo, tarifarios, políticas, guiones y chats del equipo). El catálogo vive en la
  base de datos y el agente lo **busca** (por nombre o por presupuesto) en cada conversación.
- **No inventa** precios, cupos ni promociones. Si le falta un dato, pasa la conversación a una
  persona.
- **Pasa al asesor** con todo el historial cuando el cliente pide una persona, cuando el caso es
  delicado o cuando está listo para cerrar. El equipo lo atiende desde la bandeja de la plataforma.
- **Solo WhatsApp, por escrito.** No atiende llamadas telefónicas.
- Le vuelve a escribir hasta 3 veces en 24 horas a quien dejó de contestar; si no vuelve, pasa a
  la lista de llamadas de un asesor.
- **Pedidos y reservas**: cuando el cliente da sus datos, el agente los registra en la plataforma
  y en el Google Sheets del equipo.
- **Shopify (probado)**: consulta estado del pedido, pago, envío y link de rastreo.
- **Contactos**: se importan desde Excel con una plantilla; las columnas que ya usan (ciudad,
  tipo de cliente, etapa) se conservan.
- **Integraciones**: todas se pueden hacer, a la medida (sistema de reservas, CRM, base
  operativa). Probadas: Google Sheets y Shopify.
- **Plataforma incluida** (app.glomacx.com): bandeja de mensajes, campañas segmentadas por
  WhatsApp, simulador para probar el agente antes de salir y tablero de resultados (ventas,
  abandonos y en qué paso se va la gente).
- **Tasa de cierre**: arranca parecida a la que ya tiene la empresa, porque vende con sus mismos
  mensajes, y desde ahí se trabaja para subirla. No hay porcentaje genérico que prometer.
- **Qué no tiene**: embudo de ventas por etapas tipo tablero (si la empresa tiene CRM, se integra).
- **Datos**: cuenta aislada en AWS, credenciales cifradas, las conversaciones no entrenan
  modelos, manejo alineado con la Ley 1581.
- **Arranque**: recogemos cómo vende la agencia → activamos la cuenta e instalamos el WhatsApp →
  arranca con 10 días de ajuste → soporte 24/7 y mejora continua. El tiempo depende de la
  información disponible y de la conexión del número con Meta (que depende de los accesos del
  cliente).

## 5. Inversión (fuente única: `PRECIOS` en `frontend/pages/gloma.tsx`)

| Cobro | COP | USD |
|---|---|---|
| Instalación (una sola vez) | 2.400.000 | 750 |
| Paquete 600 conversaciones | 760.000 | 245 |
| Paquete 2.000 conversaciones (**recomendado**) | 2.490.000 | 795 |
| Paquete 6.000 conversaciones | 7.190.000 | 2.295 |
| Campañas, por mensaje enviado | 90 | 0,03 |

IVA y tarifa de Meta incluidos. **No es mensualidad**: el paquete se recarga cuando se acaba y lo
que no se usa pasa al mes siguiente. Una conversación = un chat con un cliente dentro de 24 horas.
Recomendar el de 2.000 **por volumen**, nunca por precio por conversación (el de 6.000 sale más
barato por conversación). Si los precios cambian aquí, cambian en `gloma.tsx`, en la propuesta
PDF y en `backend/app/bot_contexts/gloma.md`.

## 6. Cómo vende Belfort (resumen de `.claude/agents/belfort.md`)

- Gloma ayuda al asesor, no lo reemplaza. Toda pieza muestra el paso a una persona.
- Cuidado con comparar a Gloma con un sueldo: con ticket bajo esa comparación pierde. En turismo,
  con ticket alto, gana si se hace la cuenta con los números del prospecto: chats al mes × su
  tasa de cierre actual × ticket promedio. En una pieza pública, esa cuenta va como «haz el
  ejercicio con tus números», marcada como ilustrativa.
- Cada pieza se juzga por si mueve al siguiente paso (agendar la llamada).
