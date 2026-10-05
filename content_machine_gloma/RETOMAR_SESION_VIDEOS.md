# Prompt para retomar: máquina de contenido de Gloma → videos (desde el 5-oct-2026)

Cómo usarlo: en el Mac, `cd /Users/equipo/Documents/gloma_software`, haz `git pull` de la rama
indicada abajo, abre Claude Code y pega todo lo que está debajo de la línea.

---

Vamos a seguir construyendo la parte de **videos (reels)** de la máquina de contenido de Gloma
con el agente `community-manager` (`.claude/agents/community-manager.md`). En la sesión del
5-oct-2026 (en la nube) dejamos la metodología de video en el agente y los 3 primeros guiones.

**Antes de proponer nada, lee en este orden:**
1. `.claude/agents/community-manager.md` completo, en especial la sección nueva **"Videos
   cortos (reels): metodología"**: calendario de videos, investigar hooks, guion de video corto
   (tabla SEGUNDO / VOZ / PLANO, 40 s, máx. 100 palabras, plano cada 4–6 s, una sola idea), su
   lista de verificación y "Voz del guion para ElevenLabs (provisional)".
2. `content_machine_gloma/CONTEXTO_DE_MARCA.md` (tiene 3 filas nuevas: calendario de videos,
   guiones de video y hooks de video).
3. `content_machine_gloma/calendarios/videos-2026-11.md`: calendario de reels del 1 al 25-nov,
   aparte del de carruseles. Son las filas del 11-oct al 4-nov corridas +21 días (mismo día de la
   semana). Al final, las **decisiones pendientes del CEO**.
4. `content_machine_gloma/estructuras-de-afuera/hooks-video-2026-10.md`: investigación de hooks
   con URL y tipos A–F. Ojo: en la nube no se podían abrir páginas, solo el buscador; las
   fuentes están cotejadas contra el resumen del buscador. Desde el Mac se pueden abrir y
   verificar.
5. `content_machine_gloma/guiones-video/2026-11.md`: 3 guiones (1-nov D1-A1, 2-nov Post 01,
   3-nov D4-A1) y su **voz para ElevenLabs** con etiquetas de tono en español y en inglés.
6. Lo de siempre: `identidad_gloma/design_system_gloma.md`, la Parte 0 de
   `identidad_gloma/plan_contenido_instagram_gloma.md` y la voz del cliente del mes.

**Estado al 5-oct-2026**
- Guiones 1–3 escritos. Los demás (4-nov en adelante) esperan que el CEO apruebe el formato.
- Skills de ElevenLabs: en el Mac, instalar con `npx skills add elevenlabs/skills -g --agent
  claude-code` si no están. La clave va en `ELEVENLABS_API_KEY` dentro de `~/.zshrc`, nunca en
  un archivo del repo ni en el chat. **La clave que se pegó en el chat de la sesión del 5-oct
  hay que rotarla** (crear una nueva en elevenlabs.io y borrar la vieja).
- Pendiente probar con **Eleven v3** si respeta las etiquetas en español o hay que usar las de
  inglés, y elegir la voz. Cuando el CEO lo diga, se actualiza la sección provisional del agente.

**Decisiones pendientes del CEO** (detalle en el calendario de videos):
1. ¿Se acepta que cada video repita la cita de su carrusel 3 semanas después?
2. Memes MM1–MM4 en video: dos planos con la cita narrada, o solo carrusel.
3. 4-nov: choque con EA2 del calendario de carruseles si se destraba.
4. ¿Se aprueba el formato de los 3 guiones para escribir los 16 siguientes?

**Lo próximo**, en este orden y deteniéndose en cada paso para que el CEO apruebe:
1. Generar el audio de los 3 guiones con ElevenLabs (texto de la sección "Voz para ElevenLabs").
2. El CEO va a pegar las instrucciones del curso para las imágenes de cada PLANO y el montaje;
   se agregan al agente (no a una skill), adaptadas a lo que ya existe.
3. Constructor del video: 1080 × 1920, zona segura (~240 px arriba, ~300 px abajo), subtítulos,
   rótulos en HTML, render por estados con Chrome y MP4 con ffmpeg a 30 fps constantes (la
   técnica de `video_36.py`; ffmpeg del ambiente conda, nunca dos Chrome a la vez).

**Reglas que no se rompen** (el detalle está en el agente): citas textuales con sus errores;
nada inventado (`FALTA:` si falta algo); "un empresario", nunca el nombre del prospecto, de
empresas ni de autores de reseñas; CTA para el lector; colores exactos; nunca texto dentro de una
imagen generada; toda cifra con su fuente visible; nunca generar miedo; Recupera Tu Mascota
retirado; planear no es publicar. **El repo es público**: lo de `content_machine_gloma/` que se
sube a git queda visible para cualquiera.
