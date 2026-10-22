# Plan — Percepción de valor en la landing de Gloma

> Branch `feature/landing-valor` (desde `main` 6b00fdb, 2026-10-22). Se trabaja en sesiones en la
> nube de Claude Code. **Nada sale a producción hasta que el CEO apruebe**: Amplify despliega solo
> `main` (la creación automática de branches está apagada), así que empujar este branch no
> publica nada en glomacx.com.
> Antes del merge se borra la carpeta `docs/landing-valor/` y los borradores que no se usen.

## 0. Reglas de la sesión

1. **Solo se trabaja en el branch `feature/landing-valor`.** Commits y push a ese branch y a
   ningún otro. Nada de merge a `main`, nada de PR sin que el CEO lo pida, nada de deploy.
2. **No se toca `BITACORA.md`** (otra sesión la está editando en paralelo y chocaríamos). La
   entrada se escribe al hacer el merge.
3. Material de marca: **[`BRIEF_MARCA.md`](BRIEF_MARCA.md)**. La carpeta `ventas/` no existe en la
   nube (está fuera de git porque tiene datos de prospectos) y **no se recrea**.
4. Archivos que se tocan: `frontend/pages/gloma.tsx`, `marketing/propuesta_comercial/*` y
   `frontend/public/gloma/propuesta-comercial-gloma.pdf`. Nada del backend: el contexto de Lía
   (`backend/app/bot_contexts/gloma.md`) se actualiza en la fase 5, con su propio deploy.
5. Repo **público**: nada de teléfonos o correos de personas reales. El WhatsApp y el correo de
   Gloma (+57 315 076 4000, contacto@glomacx.com) ya son públicos y sí se usan.
6. Lenguaje amigable para dueños de agencias, sin jerga técnica, y revisión de las 8 marcas de
   agua de la IA (en el brief) sobre todo texto visible antes de entregar.
7. No prometer lo que el producto no hace (brief, sección 4). No inventar cifras, casos ni
   testimonios.
8. Precios: los de `PRECIOS` en `gloma.tsx`. El PDF repite exactamente esas cifras.

## 1. Decisiones del CEO

Se le preguntan **todas juntas al empezar**, con una recomendación en cada una.

| # | Decisión | Propuesta por defecto | Qué bloquea |
|---|----------|-----------------------|-------------|
| D1 | Cómo se dice el 70 % | «Hasta un 70 % menos en el costo de atención», con una nota al pie que diga contra qué se compara (ej.: «frente a atender el mismo volumen solo con asesores»). Sin la base, la cifra no se cree | Bloque de ROI en la landing y en el PDF |
| D2 | Cuánto dura la garantía | Ninguna: se escribe `[X días]` hasta que el CEO lo defina. Tiene que cuadrar con «10 días de ajuste» y «Soporte 24/7», que ya están en la landing | Bloque de garantía |
| D3 | Qué se dice de **pagos** e **inventario** | Pagos: «comparte tus formas de pago o tu link de pago» (el agente no cobra él mismo); con Shopify, «consulta si un pedido ya está pagado». Inventario básico: «consulta qué hay disponible en tu catálogo». Confirmar | Tabla de lo que incluye |
| D4 | ¿El PDF se descarga directo o pide datos? | Directo, sin formulario. Alternativa si se quiere el lead: pedir solo nombre y WhatsApp | Botón de descarga |
| D5 | Cuál de las 3 propuestas PDF | La escoge el CEO al verlas | Fase 4 |

## 2. Investigación: qué debe tener una buena propuesta comercial de software

Hecha el 2026-10-22. Lo que coincide entre las fuentes:

- **Empezar por el problema del cliente**, con sus palabras, no por la historia de la empresa.
- **Resumen** corto → **solución** atada a ese problema → **qué incluye y qué no**.
- **Plan de implementación** realista: quién hace qué y en cuánto tiempo.
- **Retorno de inversión cuantificado y con los supuestos escritos.**
- **Inversión clara**: 2 o 3 opciones con lo que trae cada una, la instalación aparte y las
  condiciones.
- **Prueba social** del mismo sector con resultados medibles. Gloma no tiene testimonios
  autorizados: se usan solo las cifras autorizadas; no se inventan casos.
- **Seguridad y manejo de datos.**
- **Próximo paso explícito** (agendar la llamada) y **vigencia de los precios**.

Fuentes: mediasource.mx/blog/propuesta-comercial-estructura-ganadora-ejemplos-reales ·
salesdose.io/en/blog/propuesta-comercial-b2b · inventive.ai/blog-posts/saas-proposal-template-examples ·
fastspring.com/blog/what-should-every-saas-sales-proposal-include · dock.us/library/saas-proposal ·
qwilr.com/templates/saas-proposal-template

## 3. Fases

### Fase 1 — Copy (delegar en `belfort` con `community-manager`) → revisión del CEO

Leer antes: `BRIEF_MARCA.md`, `.claude/agents/belfort.md`, `.claude/agents/community-manager.md`
y `frontend/pages/gloma.tsx` completo (FAQ, PASOS_INICIO, FEATURES, STATS y PRECIOS ya dicen
cosas que el copy nuevo no puede contradecir).

Entregable: `marketing/propuesta_comercial/COPY_LANDING.md`, commit y push, y se le muestra al
CEO en el chat. **No se toca `gloma.tsx` hasta que lo apruebe.**

**1a. Tabla «Todos los paquetes incluyen»** (dentro de Precios, después de los paquetes). Las 3
columnas de paquete (600 / 2.000 / 6.000) con ✓ en todas las filas. El mensaje: todas las
funciones en todos los paquetes, solo cambia cuántas conversaciones traes. En móvil (375 px)
colapsa a una sola lista con ✓. Grupos y filas sugeridas, una línea cada una:
- *Vende y atiende*: atención comercial de día y de noche · busca en tu catálogo de planes o
  productos · cotiza con tus tarifas · toma pedidos y reservas y los deja en tu Google Sheets ·
  pagos (D3) · inventario básico (D3) · le vuelve a escribir a quien dejó de contestar · le pasa
  el cliente a tu asesor con todo el historial.
- *Asistentes*: atención por conversación · agendamiento de citas y llamadas · asistente
  corporativo (empresas y grupos).
- *Tu plataforma*: bandeja de mensajes para tu equipo · campañas por WhatsApp · simulador para
  probar antes de salir · tablero de resultados.
- *Acompañamiento*: instalación hecha por nosotros · ajustes los primeros 10 días · garantía (D2)
  · soporte técnico · mantenimiento y actualizaciones incluidas.

**1b. «No necesitas saber de tecnología»**: 3 opciones para que el CEO escoja. Formato sugerido:
dos columnas, «Lo que haces tú» (corta) y «Lo que hacemos nosotros» (larga). Borradores:
- *Opción 1 — «Tú nos cuentas cómo vendes. Nosotros lo dejamos funcionando.»* Tú: una reunión
  para contarnos cómo vende tu agencia · nos compartes tus tarifas e itinerarios · nos das acceso
  a tu WhatsApp de empresa (te guiamos paso a paso) · lo pruebas y lo apruebas. Nosotros:
  configuramos el agente, conectamos tu número, lo entrenamos con tus mensajes, lo probamos
  contigo, lo ajustamos los primeros días y lo mantenemos al día. (La recomendada.)
- *Opción 2 — «Sin instalar nada, sin aprender a programar.»* Párrafo corto + 3 pasos: «Nos
  reunimos» → «Lo dejamos listo» → «Tu agente empieza a atender». Cierra con: «Si algo hay que
  cambiar después, nos escribes por WhatsApp y lo ajustamos.»
- *Opción 3 — «Tu parte toma una tarde. La nuestra, el resto.»* Enfocada en el tiempo del dueño.
  Confirmar con el CEO que «una tarde» sea cierto.

Va junto a `ComoEmpezarSection`, que ya dice «Tu equipo nos cuenta cómo vende. Del resto nos
encargamos nosotros.»: ampliar, no duplicar.

**1c. ROI con el 70 %** (D1). `StatsSection` pasa de 3 a 4 cifras (`md:grid-cols-4` o 2×2), con
la nota al pie del supuesto. En Precios, una línea que conecte la inversión con ese ahorro.

**1d. Garantía, soporte y mantenimiento** (D2). Bloque corto en Precios, debajo de la tabla, y
una pregunta nueva en `FAQ` («¿Qué pasa después de la instalación?»). Tiene que cuadrar con
`PASOS_INICIO`.

### Fase 2 — Implementar en la landing (con el copy aprobado)

En `frontend/pages/gloma.tsx`, con el estilo del archivo (constantes de datos arriba con un
comentario de dónde salen, componentes con `Reveal`, colores de `BRAND`, Syne/Inter):
- Constante `INCLUYE` + componente `TablaIncluye` dentro de `PreciosSection`.
- Bloque «sin conocimientos técnicos» (1b).
- Cuarta cifra en `STATS` (1c); `AnimatedNumber` ya acepta `suffix` para el `%`.
- Bloque de garantía + pregunta en `FAQ` (1d).
- Botón **«Descargar propuesta comercial (PDF)»**:
  `<a href="/gloma/propuesta-comercial-gloma.pdf" download>` como secundario en el CTA final de
  Precios (junto a «Agendar una llamada», que sigue siendo el principal) y un enlace en el footer.

Verificación en la nube: `cd frontend && npm ci && npx tsc --noEmit && npm test && npm run build`.
Capturas para que el CEO las vea sin correr nada: levantar `npm run dev -- -p 3001`, tomar
capturas con Chrome headless a 375 px y 1280 px de ancho de `/gloma` (secciones nuevas) y
commitearlas en `marketing/propuesta_comercial/capturas/`.

### Fase 3 — Tres propuestas comerciales en PDF (`belfort` + `community-manager` + `ui-ux`)

Fuente: HTML en `marketing/propuesta_comercial/opcion_a.html`, `opcion_b.html`, `opcion_c.html`.
Requisitos técnicos:
- `<meta charset="utf-8">` (sin eso, Chrome rompe las tildes).
- `@page { size: A4; margin: 0 }`, `print-color-adjust: exact`, una `<section>` de
  210 × 297 mm por página con `page-break-after: always`.
- Fuentes por Google Fonts (`<link>` a Syne 700/800 e Inter 300/400/600; `fonts.googleapis.com`
  está permitido en la nube) con `font-family: Syne, …` / `Inter, …`.
- Imágenes con ruta relativa a `../../frontend/public/gloma/` (ej. `logo_blancotrans.png`).

Contenido (las tres llevan lo mismo, cambia el concepto y el diseño):
1. Portada · 2. El problema en palabras de un empresario (los «¿Te suena?» de la landing) ·
3. Qué hace Gloma · 4. Todo lo que incluye (la tabla 1a) · 5. Cómo lo dejamos funcionando (1b) ·
6. Tu inversión: los 3 cobros en COP y USD con el ejemplo de campaña · 7. Retorno: el 70 % (D1),
los 4 meses de ROI y la cuenta de Belfort con supuestos escritos («haz el ejercicio con tus
números») · 8. Garantía, soporte y mantenimiento · 9. Tus datos están seguros · 10. Próximo paso:
agendar la llamada, WhatsApp y glomacx.com, más «Precios vigentes a [mes] de 2026».
Entre 6 y 10 páginas. Sin testimonios inventados.

Conceptos, para que se diferencien de verdad:
- **A — Ejecutiva**: fondo Technical Black, mucho aire, una idea por página, cifras grandes en
  mint. Para el dueño que decide rápido.
- **B — El viaje**: la propuesta como un itinerario (Embarque → Ruta → Destino), con la
  ventanilla del logo como marco. La más «de marca turismo».
- **C — Clara y cercana**: fondo Soft Mint, tono conversacional, organizada por las preguntas
  de un dueño de agencia («¿Qué hace?», «¿Cuánto invierto?», «¿Qué tengo que hacer yo?»).

Exportar las tres y commitear los PDF en `marketing/propuesta_comercial/pdf/` (GitHub los
muestra, el CEO los abre desde el navegador o el celular):
```bash
# Chrome no viene instalado en la nube: se baja Chrome for Testing (storage.googleapis.com está permitido)
npx -y @puppeteer/browsers install chrome@stable --path /tmp/chrome
export CHROME="$(ls -d /tmp/chrome/chrome/*/chrome-linux64)/chrome"
./marketing/propuesta_comercial/exportar_pdf.sh
```
Revisar el PDF: número de páginas, tamaño A4 (`pdfinfo`), tildes y que no se corte nada.

### Fase 4 — La elegida queda conectada al botón

```bash
./marketing/propuesta_comercial/exportar_pdf.sh opcion_X.html --publicar
# → frontend/public/gloma/propuesta-comercial-gloma.pdf
```
Comprobar que el botón de la landing la descarga.

### Fase 5 — QA y salida (con el CEO)

Checklist: móvil 375 px sin scroll horizontal (la tabla colapsa) · COP y USD · el botón descarga
el PDF · la pregunta nueva del FAQ abre · nada contradice FAQ ni PASOS_INICIO · auditoría de las
8 marcas de agua sobre el texto visible · `tsc`, `npm test` y `npm run build` en verde.

Para el merge, cuando el CEO lo apruebe:
- Actualizar `backend/app/bot_contexts/gloma.md` (el 70 %, la garantía y el mantenimiento), o
  Lía y la página se contradicen. Ese cambio necesita imagen nueva del backend.
- Anotar el 70 % en las cifras autorizadas del plan de contenido (`ventas/`, en el equipo del CEO).
- Borrar `docs/landing-valor/`, `capturas/` y los PDF de las opciones descartadas.
- PR, entrada en `BITACORA.md`, merge y deploy (Amplify despliega la landing al hacer merge a
  `main`).
