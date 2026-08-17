# Plan de pruebas manuales — Sprint "Ayuda a Cali"

**Iniciativa "Recupera Tu Mascota"** · bot de mascotas perdidas por el terremoto en Colombia.

| Qué | Dónde |
|---|---|
| Chat ciudadano (público, sin login) | **https://mascotasperdidascolombia.com** |
| Panel de la cuenta (con login) | **https://app.glomabeauty.com** → menú lateral **🐾 Mascotas** |
| Credenciales del panel | usuario `recuperatumascota@gmail.com` · contraseña **en el gestor de contraseñas del CEO** (este repo es público: nunca se escribe aquí) |
| API | `https://api.glomabeauty.com` |

> En producción ya hay **10 reportes de demostración** (`source = demo`, fotos reales
> descargadas de internet) con **3 pares diseñados para coincidir**: Canela, Michi y
> Rocky. Sirven para probar todo sin esperar reportes reales. Se borran re-corriendo el
> seed o desde el panel.

---

## Bloque 1 — Camino "busco a mi mascota" (con coincidencia)

| # | Paso | Resultado esperado |
|---|---|---|
| 1.1 | Abre https://mascotasperdidascolombia.com | Ventana estilo WhatsApp. Header "Huella · Recupera Tu Mascota". Aviso amarillo que dice que es **gratuito** y que es por el **terremoto**, y debajo el **aviso de uso de datos**. Saludo del bot con **los 3 casos de uso** y, al final, la línea de aceptación de datos. |
| 1.2 | Verifica los 3 botones de acceso rápido | "Buscar a mi mascota", "Reporté una que encontré", "Descargar el listado". |
| 1.3 | Escribe: `se me perdió mi perrita labrador café clarita en San Fernando, tiene una mancha blanca en el pecho` | El bot responde con empatía y **busca de inmediato** (no te hace 4 preguntas antes). |
| 1.4 | Observa el resultado | Dice cuántas coincidencias hay y muestra **una ficha con foto**: labrador café, hembra, San Fernando, mancha blanca en el pecho. Termina preguntando "¿es esta tu mascota?". |
| 1.5 | Responde: `sí es ella` | Entrega **ubicación**, **enlace de Google Maps** y **teléfono** de quien la encontró: `Parque de San Fernando, frente a la panadería` · `+57 315 802 4471` (Julián Ospina). |
| **1.6** | **Contrasta ese teléfono con el panel** (bloque 5) | Debe ser **idéntico** al de la fila `MC-00002`. ⚠️ Si aparece un número distinto, el bot lo inventó — reportarlo de inmediato. |

## Bloque 2 — Camino "busco a mi mascota" (SIN coincidencia)

| # | Paso | Resultado esperado |
|---|---|---|
| 2.1 | Recarga la página y escribe: `se me perdió mi loro verde y amarillo en el barrio San Antonio, se llama Pepe` | El bot pide algún dato más y busca. |
| 2.2 | Responde: `no tengo más datos` | El bot dice que **todavía** no hay coincidencias, que **la lista se actualiza todos los días**, que **tu caso queda guardado en la base de datos** y que **te contactan apenas aparezca algo**. Después pide **teléfono**. |
| 2.3 | Escribe: `mi teléfono es 3009998877, soy Carlos` | Registra el caso y **confirma un código `MC-000xx`**. También aparece arriba a la derecha del header. |
| 2.4 | Observa el cierre | Pregunta **si tienes otra mascota que registrar**. |
| 2.5 | Verifica en el panel | El reporte aparece en la pestaña **🔎 Se buscan**, con el teléfono y la ubicación que diste. |

## Bloque 3 — Camino "encontré una mascota" (con fotos)

| # | Paso | Resultado esperado |
|---|---|---|
| 3.1 | Recarga y **adjunta 1–2 fotos con el clip 📎 antes de escribir nada** | Las fotos se ven en el chat como mensajes tuyos. |
| 3.2 | Escribe: `encontré este perrito negro con blanco, mediano, cojea de una pata` | El bot agradece y pregunta **dónde** está. |
| 3.3 | Escribe: `está en mi casa en el barrio Meléndez, mi teléfono es 3145566778, soy Ana` | **Registra el caso** (código `MC-000xx`) sin seguir preguntando, y confirma cuántas fotos quedaron guardadas. |
| 3.4 | Escribe: `tiene un collar azul y una mancha blanca en la pata de atrás` | Completa **el mismo** reporte (no crea uno nuevo). |
| 3.5 | Observa | Cruza contra las mascotas que se buscan y te muestra a **Rocky** (`MC-00005`), que coincide. |
| 3.6 | Verifica en el panel | El reporte está en **🐾 Encontradas**, con **las fotos que subiste** y las señas del paso 3.4. |

## Bloque 4 — Listado en Excel y fuera de alcance

| # | Paso | Resultado esperado |
|---|---|---|
| 4.1 | Escribe: `quiero el listado en Excel` | Aparece una **tarjeta de descarga** en el chat. |
| 4.2 | Descárgala y ábrela | `.xlsx` válido, encabezado verde congelado, con **filtros**, y columnas de señas, **comentarios adicionales**, ubicación, Maps, teléfono y estado. |
| 4.3 | Recarga y escribe: `quiero vender seguros de vida` | El bot aclara **una vez** los 3 casos de uso y pregunta si necesitas alguno. |
| 4.4 | Insiste: `no, solo quiero vender seguros` | Se despide y **cierra la conversación**. |
| 4.5 | Recarga y escribe cualquier cosa | Mensaje de **chat en pausa** recordando los 3 casos de uso. La pausa dura **20 minutos**. |

## Bloque 5 — Panel de la cuenta (validación de datos)

Entra a **https://app.glomabeauty.com** con `recuperatumascota@gmail.com` / `«en el gestor del CEO»`
y abre **🐾 Mascotas** en el menú lateral.

| # | Paso | Resultado esperado |
|---|---|---|
| 5.1 | Revisa los 6 contadores | Reportes totales · Se están buscando · Fueron encontradas · Reunidas · **Coincidencias sin revisar** · Fotos guardadas. |
| 5.2 | Pestaña **🔗 Coincidencias** | Pares lado a lado ("La están buscando" vs "La encontraron") con foto, teléfono de **ambas** partes, **puntaje de parecido** y **qué campos coincidieron**. Canela↔MC-00002 debe ser la más alta (24). |
| 5.3 | Botón **🎉 Es la misma** en un par | La etiqueta cambia y el contador de "sin revisar" baja. |
| 5.4 | Botón **🔄 Cruzar ahora** | Recalcula sin esperar al job de las 12:00. |
| 5.5 | Pestaña **🔎 Se buscan** | Tabla con foto, código, mascota, señas y comentarios, ubicación (+ Maps), contacto, origen y estado. |
| 5.6 | **Filtros**: escribe `labrador`, luego usa especie / zona / estado / "solo con foto" | La tabla se filtra y el contador de abajo se actualiza. "Limpiar filtros" los reinicia. |
| 5.7 | Clic en una **miniatura** | Se abre el **visor a pantalla completa**: foto grande, flechas ‹ › si hay varias, datos de contacto y **la ruta donde quedó guardado el recurso** (`s3://gloma-mascotas-747456040509/mascotas/MC-000xx/…`). `Esc` cierra. |
| 5.8 | Cambia el estado de un reporte a **Reunida 🎉** | Se guarda y el contador "Reunidas" sube. |
| 5.9 | Botón **📊 Descargar Excel** | Mismo archivo del bloque 4, ya autenticado. |

## Bloque 5b — Editar y borrar (para dejar la base limpia tras probar)

| # | Paso | Resultado esperado |
|---|---|---|
| 5b.1 | En una fila, botón **✏️ Editar** | Se abre el formulario con todos los campos del reporte. **Ubicación**, **teléfono de contacto** y **especie** están marcados con `*`. |
| 5b.2 | Cambia el color y las señas, y guarda | Se guarda y la tabla se actualiza. |
| 5b.3 | Borra el contenido de **Ubicación** y guarda | No deja: avisa que es obligatoria. Lo mismo con el **teléfono**. |
| 5b.4 | Escribe un teléfono inválido (`abc`) y guarda | Lo rechaza con un mensaje claro. |
| 5b.5 | Cambia el **estado** a *Reunida 🎉* desde el formulario o el selector de la fila | Se refleja en el contador de arriba. |
| 5b.6 | Abre el visor de fotos y usa **🗑 Eliminar esta foto** | La foto desaparece del reporte (y del almacenamiento). |
| 5b.7 | Botón **🗑 Eliminar** de una fila | Pide confirmación y borra el reporte con sus fotos y coincidencias. |
| 5b.8 | Botón **🧪 Borrar datos de prueba** (arriba a la derecha) | Pide confirmación, borra **solo** los reportes marcados 🧪 Demo y dice cuántos eliminó. Los que entraron por el chat **no se tocan**. |
| 5b.9 | Tras purgar, revisa la pestaña de coincidencias | Las coincidencias de los reportes borrados desaparecen solas. |

> El botón de purga solo aparece si quedan datos de prueba. Úsalo cuando termines de
> probar, antes de abrir el sitio al público.

## Bloque 6 — Seguridad y aislamiento

| # | Paso | Resultado esperado |
|---|---|---|
| 6.1 | Entra a app.glomabeauty.com con **otra cuenta** (p. ej. `gloma@glomabeauty.com`) | **No aparece** el módulo 🐾 Mascotas en el menú. |
| 6.2 | Con esa cuenta entra a mano a `/mascotas-panel` | "Este módulo no está disponible en tu cuenta". |
| 6.3 | Abre https://mascotasperdidascolombia.com/login | **404**. En ese dominio solo vive el chat. |
| 6.4 | Abre https://mascotasperdidascolombia.com/mascotas-panel | **404**. El panel solo se usa desde la app con sesión. |
| 6.5 | Verifica que la app siguió igual | https://app.glomabeauty.com y https://glomabeauty.com funcionan como siempre. |
| 6.6 | En el chat, antes de confirmar una mascota, pídele el teléfono al bot | **No lo entrega**: solo lo da cuando confirmas que la reconoces. |

## Bloque 7 — Job diario de coincidencias

| # | Paso | Resultado esperado |
|---|---|---|
| 7.1 | Corre desde el panel **🔄 Cruzar ahora** tras crear un reporte nuevo que se parezca a otro | Aparece una coincidencia nueva. |
| 7.2 | Marca una coincidencia como **✕ No es** y vuelve a cruzar | **No** vuelve a aparecer como "sin revisar": el cruce respeta lo que ya revisó el equipo. |
| 7.3 | Automático: mañana a las **12:00 (hora Colombia)** | El cruce corre solo (EventBridge `mascotas-cruce-diario`). Se verifica en el panel o en CloudWatch (`/ecs/multiagente-backend`, buscar `job_coincidencias`). |

---

## Qué mirar con lupa

1. **Teléfonos y direcciones**: que lo que dice el bot coincida **exactamente** con el
   panel. Hay un guardarraíl que bloquea números inventados, pero es la validación más
   importante del sprint.
2. **Que registre siempre**: ninguna conversación donde alguien dio teléfono y ubicación
   debería terminar sin un código `MC-`.
3. **Que no repregunte** datos que ya diste tres mensajes atrás.
4. **Fotos**: que se vean en el chat, en el panel y en el visor, y que la ruta `s3://`
   corresponda al código del reporte.

## Datos de demostración cargados

| Código | Tipo | Mascota | Zona | Par |
|---|---|---|---|---|
| MC-00001 | perdida | Canela · labrador café · collar rojo | San Fernando | ↔ MC-00002 (24 pts) |
| MC-00002 | encontrada | labrador café · mancha blanca en el pecho | San Fernando | |
| MC-00003 | perdida | Michi · gato gris atigrado | Ciudad Jardín | ↔ MC-00004 (15 pts) |
| MC-00004 | encontrada | gato gris · cola blanca, oreja partida | Ciudad Jardín | |
| MC-00005 | perdida | Rocky · criollo negro · cojea | Meléndez | ↔ MC-00006 (19 pts) |
| MC-00006 | encontrada | negro con blanco · cojea | Meléndez | |
| MC-00007 | encontrada | Pincher negro y café | Tequendama | — |
| MC-00008 | perdida | Nube · gata blanca y naranja | Granada | — |
| MC-00009 | encontrada | conejo blanco (especie "otra") | El Refugio | — |
| MC-00010 | perdida | Simba · golden · pañoleta azul | Pance | — |
