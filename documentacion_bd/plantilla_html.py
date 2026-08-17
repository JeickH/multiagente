"""La plantilla de `index.html`. Separada de `generar.py` para que el HTML no
se mezcle con las consultas al catálogo.

Sin dependencias externas ni CDN: el archivo se abre con doble clic y se ve
igual sin internet.
"""
from __future__ import annotations

from datetime import datetime

FUENTES = [
    ("web", "Nuestro bot (Huella)", "perdida y encontrada", "Sí, obligatorio",
     "El ciudadano lo escribe en el chat"),
    ("royipets", "RoyiPets (Cali) — PDF", "encontrada", "Sí, el de la fundación",
     "PDF exportado de Excel, sin rejilla: se reconstruye por coordenadas"),
    ("petsearch", "petsearch.neuralync.dev", "perdida y encontrada", "Sí",
     "API JSON pública. <code>found</code> = reencontrada, no se trae"),
    ("encontradogs", "encontradogs.co", "perdida y encontrada",
     "No, a propósito", "HTML del servidor. El sitio hace de intermediario"),
    ("proteccionanimal", "Protección Animal del Valle", "perdida y encontrada",
     "A veces, dentro de la descripción",
     "API .NET. Marca todo «Perdido»: el tipo se deduce"),
    ("mascotasporcolombia", "mascotasporcolombia.com", "encontrada", "No",
     "Sitemap + payload de React"),
    ("patitasacasa", "patitasacasa.com", "perdida y encontrada",
     "Enmascarado (310****57)", "API pública. Su WAF bloquea las IPs de AWS"),
]

# (columna, web, royipets, petsearch, encontradogs, proteccionanimal, mpc, pac)
# ● publica · ~ se deduce de texto libre · — no lo tiene
MATRIZ = [
    ("tipo_registro", "●", "●", "●", "●", "~", "●", "●"),
    ("especie", "●", "●", "●", "●", "●", "●", "●"),
    ("raza", "●", "●", "●", "●", "—", "●", "●"),
    ("color", "●", "~", "~", "●", "~", "●", "●"),
    ("nombre", "●", "●", "●", "●", "●", "●", "●"),
    ("sexo", "●", "●", "~", "●", "●", "●", "●"),
    ("edad", "●", "~", "~", "~", "~", "●", "—"),
    ("tamano", "●", "~", "~", "●", "~", "●", "●"),
    ("senas", "●", "●", "●", "●", "●", "●", "●"),
    ("ubicacion", "●", "●", "●", "●", "●", "●", "●"),
    ("barrio", "●", "●", "●", "●", "●", "●", "●"),
    ("ciudad", "—", "●", "●", "~", "●", "●", "●"),
    ("departamento", "—", "●", "●", "—", "●", "—", "—"),
    ("maps_url", "●", "—", "—", "—", "—", "●", "—"),
    ("contacto_nombre", "●", "●", "—", "—", "●", "●", "—"),
    ("contacto_telefono", "●", "●", "●", "—", "~", "—", "—"),
    ("origen_url", "—", "—", "●", "●", "●", "●", "●"),
    ("fecha_evento", "●", "●", "●", "●", "—", "●", "●"),
    ("esterilizado", "—", "●", "—", "—", "●", "—", "—"),
    ("vacunado", "—", "—", "—", "—", "●", "—", "—"),
    ("desparasitado", "—", "—", "—", "—", "●", "—", "—"),
    ("peso_kg", "—", "—", "—", "—", "●", "—", "—"),
    ("salud", "—", "●", "—", "—", "—", "●", "—"),
    ("resguardo", "—", "●", "—", "—", "●", "●", "—"),
    ("resguardo_nombre", "—", "●", "—", "—", "●", "—", "—"),
    ("rescatado_por", "—", "●", "—", "—", "—", "—", "—"),
    ("rescatado_por_telefono", "—", "●", "—", "—", "—", "—", "—"),
    ("recompensa", "—", "—", "—", "—", "—", "●", "—"),
    ("estado_origen", "—", "●", "●", "●", "●", "●", "●"),
    ("publicado_origen_at", "—", "—", "●", "●", "—", "●", "—"),
]

PESOS = [
    ("raza · color", "5", "Lo que de verdad identifica a un animal en la calle"),
    ("señas", "hasta 5", "«collar azul», «mancha en la pata»"),
    ("tamaño", "3", ""),
    ("zona", "2", "<b>No descarta</b>: el animal camina, y quien lo encuentra "
                  "reporta dónde está, no dónde se perdió"),
    ("sexo · edad · especie", "2", "<code>desconocido</code> no puntúa"),
    ("nombre", "1", "Quien encuentra un animal en la calle no sabe cómo se llama"),
]

CSS = """
:root { --tinta:#12211c; --suave:#5d726a; --linea:#dfe7e3; --fondo:#f6f8f7;
        --acento:#0f5c46; --aviso:#b4530a; --aviso-bg:#fff6ec; --mono:#f0f4f2; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fondo); color:var(--tinta);
       font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
header { background:#fff; border-bottom:1px solid var(--linea); padding:36px 28px; }
.wrap { max-width:1120px; margin:0 auto; }
h1 { margin:0 0 8px; font-size:28px; letter-spacing:-.4px; }
h2 { font-size:21px; margin:38px 0 14px; padding-bottom:8px;
     border-bottom:2px solid var(--acento); }
h3 { font-size:16px; margin:26px 0 10px; }
.sub { color:var(--suave); margin:0; max-width:70ch; }
main { padding:28px; }
code { background:var(--mono); padding:1px 5px; border-radius:4px;
       font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.9em; }
.card { background:#fff; border:1px solid var(--linea); border-radius:12px;
        padding:22px 24px; margin-bottom:18px; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th { text-align:left; color:var(--suave); font-size:12.5px; text-transform:uppercase;
     letter-spacing:.04em; padding:8px 10px; border-bottom:2px solid var(--linea); }
td { padding:8px 10px; border-bottom:1px solid #f0f4f2; vertical-align:top; }
tr:last-child td { border-bottom:none; }
td.col { font-family:ui-monospace,monospace; font-size:12.5px; white-space:nowrap; }
td.tipo { color:var(--suave); font-size:12.5px; white-space:nowrap; }
.scroll { overflow-x:auto; }
.nota { background:var(--aviso-bg); border:1px solid #f0d7b8; border-left:4px solid var(--aviso);
        border-radius:8px; padding:12px 16px; margin:12px 0; font-size:14px; }
.nota b:first-child { color:var(--aviso); }
.grupo { background:var(--mono); font-weight:600; font-size:12px;
         text-transform:uppercase; letter-spacing:.05em; color:var(--acento); }
.si { color:var(--acento); font-weight:700; text-align:center; }
.deduce { color:var(--aviso); font-weight:700; text-align:center; }
.no { color:#c6d0cb; text-align:center; }
.kpis { display:flex; flex-wrap:wrap; gap:10px; margin-top:20px; }
.kpi { background:var(--fondo); border:1px solid var(--linea); border-radius:10px;
       padding:10px 16px; }
.kpi b { display:block; font-size:22px; }
.kpi span { color:var(--suave); font-size:12.5px; }
.er { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; }
.ent { border:2px solid var(--acento); border-radius:10px; background:#fff; overflow:hidden; }
.ent h4 { margin:0; background:var(--acento); color:#fff; padding:9px 14px; font-size:14px;
          font-family:ui-monospace,monospace; }
.ent ul { margin:0; padding:10px 14px; list-style:none; font-size:12.5px;
          font-family:ui-monospace,monospace; color:var(--suave); }
.ent li.pk { color:var(--tinta); font-weight:700; }
.rel { color:var(--suave); font-size:13.5px; margin:14px 0 0; }
.pasos { counter-reset:paso; padding:0; list-style:none; margin:0; }
.pasos li { counter-increment:paso; position:relative; padding:0 0 16px 42px; }
.pasos li::before { counter-increment:none; content:counter(paso); position:absolute; left:0; top:0;
  width:26px; height:26px; border-radius:50%; background:var(--acento); color:#fff;
  display:grid; place-items:center; font-size:13px; font-weight:700; }
footer { color:var(--suave); font-size:13px; padding:30px 28px 50px; text-align:center; }
@media (max-width:640px) { table { font-size:13px; } }
"""


def render(datos, conteos, esc) -> str:
    total = sum(int(c[2]) for c in conteos)
    fuentes_html = "".join(
        f"<tr><td class='col'>{s}</td><td>{o}</td><td>{t}</td><td>{tel}</td><td>{c}</td></tr>"
        for s, o, t, tel, c in FUENTES
    )
    cab_matriz = "".join(f"<th>{s}</th>" for s, *_ in FUENTES)
    def celda(v):
        clase = {"●": "si", "~": "deduce", "—": "no"}[v]
        return f"<td class='{clase}'>{v}</td>"
    matriz_html = "".join(
        f"<tr><td class='col'>{f[0]}</td>" + "".join(celda(v) for v in f[1:]) + "</tr>"
        for f in MATRIZ
    )
    pesos_html = "".join(
        f"<tr><td class='col'>{c}</td><td><b>{p}</b></td><td>{d}</td></tr>"
        for c, p, d in PESOS
    )
    conteos_html = "".join(
        f"<tr><td class='col'>{s}</td><td>{t}</td><td>{n}</td></tr>" for s, t, n in conteos
    )

    tablas_html = []
    for nombre, info in datos.items():
        notas = "".join(
            f"<div class='nota'><b>{t}</b><br>{c}</div>" for t, c in info["notas"])
        filas, grupo_actual = [], None
        for c in info["columnas"]:
            if c["grupo"] and c["grupo"] != grupo_actual:
                grupo_actual = c["grupo"]
                filas.append(f"<tr><td colspan='4' class='grupo'>{esc(grupo_actual)}</td></tr>")
            filas.append(
                f"<tr><td class='col'>{esc(c['nombre'])}</td>"
                f"<td class='tipo'>{esc(c['tipo'])}</td>"
                f"<td class='tipo'>{'sí' if c['nulo'] else '<b>no</b>'}</td>"
                f"<td>{c['desc'] or '—'}</td></tr>"
            )
        extras = ""
        if info["restricciones"]:
            extras += "<h3>Restricciones</h3><ul>" + "".join(
                f"<li><code>{esc(n)}</code> — <code>{esc(d)}</code></li>"
                for n, d in info["restricciones"]) + "</ul>"
        if info["indices"]:
            extras += "<h3>Índices</h3><ul>" + "".join(
                f"<li><code>{esc(n)}</code> — <code>{esc(d.split('USING')[-1].strip())}</code></li>"
                for n, d in info["indices"]) + "</ul>"
        tablas_html.append(
            f"<h2 id='{nombre}'><code>{nombre}</code></h2><div class='card'>{notas}"
            f"<div class='scroll'><table><thead><tr><th>Columna</th><th>Tipo</th>"
            f"<th>Nulo</th><th>Qué es</th></tr></thead><tbody>{''.join(filas)}"
            f"</tbody></table></div>{extras}</div>"
        )

    er = "".join(
        f"<div class='ent'><h4>{n}</h4><ul>" + "".join(
            f"<li class='{'pk' if c['nombre'] in ('id', 'codigo') else ''}'>"
            f"{c['nombre']}</li>"
            for c in datos[n]["columnas"][:9]
        ) + f"<li>… {len(datos[n]['columnas'])} columnas</li></ul></div>"
        for n in datos
    )

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Base de datos · Recupera Tu Mascota</title>
<style>{CSS}</style></head><body>
<header><div class="wrap">
  <h1>Base de datos · Recupera Tu Mascota</h1>
  <p class="sub">Una sola tabla <code>mascotas</code> capaz de recibir lo que publica
  cualquiera de las siete fuentes, sin que ninguna tenga que esconder datos dentro de un
  campo de texto libre para que quepan. Generado leyendo la base local el
  {datetime.now():%Y-%m-%d %H:%M}.</p>
  <div class="kpis">
    <div class="kpi"><b>{total}</b><span>reportes cargados</span></div>
    <div class="kpi"><b>{len(datos['mascotas']['columnas'])}</b><span>columnas en <code>mascotas</code></span></div>
    <div class="kpi"><b>{len(FUENTES)}</b><span>fuentes soportadas</span></div>
    <div class="kpi"><b>3</b><span>tablas del módulo</span></div>
  </div>
</div></header>
<main><div class="wrap">

<h2>El esquema de un vistazo</h2>
<div class="card">
  <div class="er">{er}</div>
  <p class="rel"><b>Relaciones:</b>
  <code>mascota_fotos.mascota_id</code> → <code>mascotas.id</code> (ON DELETE CASCADE) ·
  <code>mascota_coincidencias.perdida_id</code> y <code>.encontrada_id</code> →
  <code>mascotas.id</code> (ON DELETE CASCADE) ·
  <code>mascotas.bot_id</code> → <code>bots.id</code> (ON DELETE SET NULL).
  El diagrama completo está en <code>esquema_mascotas.puml</code>.</p>
</div>

<h2>Las fuentes</h2>
<div class="card"><div class="scroll"><table>
  <thead><tr><th>source</th><th>Origen</th><th>Trae</th><th>¿Teléfono?</th><th>Cómo se baja</th></tr></thead>
  <tbody>{fuentes_html}</tbody></table></div>
  <h3>Qué hay cargado hoy</h3>
  <div class="scroll"><table><thead><tr><th>source</th><th>tipo</th><th>reportes</th></tr></thead>
  <tbody>{conteos_html}</tbody></table></div>
</div>

<h2>Qué publica cada fuente</h2>
<div class="card">
  <p class="sub"><span class="si">●</span> la fuente lo publica como campo aparte ·
  <span class="deduce">~</span> se deduce leyendo texto libre ·
  <span class="no">—</span> no lo tiene.</p>
  <div class="scroll"><table>
    <thead><tr><th>Columna</th>{cab_matriz}</tr></thead>
    <tbody>{matriz_html}</tbody></table></div>
</div>

<h2>Cómo entra un reporte</h2>
<div class="card">
  <ol class="pasos">
    <li><b>Revisar</b> — <code>actualizar_fuente.py &lt;fuente&gt; --revisar</code> baja la
    fuente, descarta lo que ya está en la base por <code>(source, origen_id)</code>, baja las
    fotos y arma un HTML con las fichas nuevas. <b>La base solo se lee.</b></li>
    <li><b>La compuerta</b> — el CEO abre el HTML y revisa ficha por ficha. Las alertas
    marcan lo que hay que confirmar: tipo deducido, posible duplicado, sin foto, sin vía de
    contacto, campo leído de la descripción.</li>
    <li><b>Cargar</b> — <code>--cargar</code> escribe solo lo aprobado, volviendo a verificar
    contra la base. Correrlo dos veces da <code>creados=0 ya_estaban=N</code>.</li>
  </ol>
  <div class="nota"><b>Ningún importador escribe en la base sin que un humano haya visto el
  HTML.</b><br>No es una convención: el paso de revisión y el de carga son comandos distintos.</div>
</div>

<h2>Cómo se cruzan los reportes</h2>
<div class="card">
  <p class="sub">El scoring puntúa campo a campo y <b>nada es obligatorio</b>: lo que la
  persona no sabe, no puntúa. La especie es el único filtro duro.</p>
  <div class="scroll"><table>
    <thead><tr><th>Campo</th><th>Peso</th><th>Por qué</th></tr></thead>
    <tbody>{pesos_html}</tbody></table></div>
  <div class="nota"><b>Umbrales</b><br>Búsqueda en vivo ≥3 · cruce diario ≥12 y máximo 3
  candidatas por caso. Con 250×50 pares, un umbral de 6 daba 5.284 coincidencias y el panel
  quedaba inservible.</div>
  <div class="nota"><b>No puntúan</b><br>El sexo <code>desconocido</code> y las zonas
  genéricas (<code>Cali</code>, <code>Valle</code>), porque los trae casi todo reporte
  importado e inflaban cualquier par.</div>
</div>

{''.join(tablas_html)}

</div></main>
<footer>Generado por <code>documentacion_bd/generar.py</code> ·
La fuente de verdad del esquema es <code>backend/app/models.py</code></footer>
</body></html>"""
