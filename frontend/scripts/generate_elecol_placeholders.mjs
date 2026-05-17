#!/usr/bin/env node
// Genera placeholders SVG provisionales para la landing /elecol.
// Idempotente: re-ejecutar regenera todos los .placeholder.svg / .svg que
// nazcan de este script, sin tocar assets reales.
//
// Uso:
//   cd frontend && node scripts/generate_elecol_placeholders.mjs

import { mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', 'public', 'elecol');

const PALETTE = {
  deep: '#03045E',
  electric: '#0077B6',
  cyan: '#00B4D8',
  sky: '#90E0EF',
  foam: '#CAF0F8',
  solar: '#FFC300',
};

// Definición declarativa de cada asset esperado por la landing.
// Mantener sincronizado con frontend/public/elecol/README.md.
const ASSETS = [
  // hero/
  { dir: 'hero', file: 'hero-render.webp', w: 1280, h: 800, label: 'Hero render principal', accent: PALETTE.solar },
  { dir: 'hero', file: 'hero-video.mp4', w: 1920, h: 1080, label: 'Hero video loop (mp4)', accent: PALETTE.cyan },
  { dir: 'hero', file: 'hero-video.webm', w: 1920, h: 1080, label: 'Hero video loop (webm)', accent: PALETTE.cyan },
  { dir: 'hero', file: 'hero-poster.webp', w: 1920, h: 1080, label: 'Hero poster', accent: PALETTE.electric },

  // infraestructura/
  { dir: 'infraestructura', file: 'estacion-render.webp', w: 720, h: 900, label: 'Render estación', accent: PALETTE.cyan },
  { dir: 'infraestructura', file: 'icon-solar.svg', w: 64, h: 64, label: 'Solar', accent: PALETTE.solar, kind: 'icon' },
  { dir: 'infraestructura', file: 'icon-autonomia.svg', w: 64, h: 64, label: 'Autonomía 24/7', accent: PALETTE.cyan, kind: 'icon' },
  { dir: 'infraestructura', file: 'icon-ev.svg', w: 64, h: 64, label: 'EV universal', accent: PALETTE.sky, kind: 'icon' },
  { dir: 'infraestructura', file: 'icon-carga-rapida.svg', w: 64, h: 64, label: 'Carga rápida', accent: PALETTE.solar, kind: 'icon' },

  // software/
  { dir: 'software', file: 'dashboard-mockup.webp', w: 1120, h: 700, label: 'Dashboard ELECOL OS', accent: PALETTE.cyan },
  { dir: 'software', file: 'dashboard-mockup-mobile.webp', w: 360, h: 720, label: 'Dashboard mobile', accent: PALETTE.sky },
  { dir: 'software', file: 'icon-reservas.svg', w: 48, h: 48, label: 'Reservas', accent: PALETTE.cyan, kind: 'icon' },
  { dir: 'software', file: 'icon-remoto.svg', w: 48, h: 48, label: 'Gestión remota', accent: PALETTE.sky, kind: 'icon' },
  { dir: 'software', file: 'icon-monitoreo.svg', w: 48, h: 48, label: 'Monitoreo', accent: PALETTE.solar, kind: 'icon' },
  { dir: 'software', file: 'icon-analitica.svg', w: 48, h: 48, label: 'Analítica', accent: PALETTE.cyan, kind: 'icon' },
  { dir: 'software', file: 'icon-franquicias.svg', w: 48, h: 48, label: 'Franquicias', accent: PALETTE.sky, kind: 'icon' },
  { dir: 'software', file: 'icon-pagos.svg', w: 48, h: 48, label: 'Pagos', accent: PALETTE.solar, kind: 'icon' },

  // red-latam/
  { dir: 'red-latam', file: 'mapa-latam.svg', w: 1200, h: 800, label: 'Mapa LATAM', accent: PALETTE.cyan, kind: 'map' },
  { dir: 'red-latam', file: 'mapa-latam.webp', w: 1200, h: 800, label: 'Mapa LATAM (raster)', accent: PALETTE.cyan },
  { dir: 'red-latam', file: 'dot-glow.svg', w: 24, h: 24, label: 'Dot glow', accent: PALETTE.solar, kind: 'dot' },

  // cta/
  { dir: 'cta', file: 'cta-bg.webp', w: 1920, h: 900, label: 'CTA background', accent: PALETTE.solar },
  { dir: 'cta', file: 'cta-bg-mobile.webp', w: 750, h: 1200, label: 'CTA background mobile', accent: PALETTE.solar },

  // brand/
  { dir: 'brand', file: 'logo-elecol.svg', w: 160, h: 40, label: 'ELECOL', accent: PALETTE.cyan, kind: 'logo' },
  { dir: 'brand', file: 'logo-elecol-mono.svg', w: 160, h: 40, label: 'ELECOL', accent: PALETTE.foam, kind: 'logo' },
  { dir: 'brand', file: 'isotipo.svg', w: 64, h: 64, label: 'E', accent: PALETTE.solar, kind: 'iso' },
  { dir: 'brand', file: 'favicon.ico', w: 32, h: 32, label: 'fav', accent: PALETTE.solar, kind: 'iso' },
  { dir: 'brand', file: 'og-image.png', w: 1200, h: 630, label: 'ELECOL — Energía que fluye como nuestro mar', accent: PALETTE.solar },
];

// ---- Generadores SVG --------------------------------------------------------

function escape(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function svgHero({ w, h, label, file, accent }) {
  // Placeholder cinematográfico para imágenes grandes.
  const fontSize = Math.max(18, Math.round(Math.min(w, h) / 18));
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${escape(label)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${PALETTE.deep}"/>
      <stop offset="1" stop-color="${PALETTE.electric}"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="55%" r="60%">
      <stop offset="0" stop-color="${accent}" stop-opacity="0.35"/>
      <stop offset="1" stop-color="${accent}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M 48 0 L 0 0 0 48" fill="none" stroke="${PALETTE.cyan}" stroke-opacity="0.07" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <rect width="100%" height="100%" fill="url(#grid)"/>
  <rect width="100%" height="100%" fill="url(#glow)"/>
  <g opacity="0.55">
    <circle cx="${w * 0.18}" cy="${h * 0.22}" r="${Math.min(w, h) * 0.04}" fill="${PALETTE.cyan}"/>
    <circle cx="${w * 0.82}" cy="${h * 0.78}" r="${Math.min(w, h) * 0.06}" fill="${accent}"/>
    <path d="M0 ${h * 0.65} Q ${w * 0.5} ${h * 0.45} ${w} ${h * 0.7}" stroke="${PALETTE.sky}" stroke-opacity="0.4" stroke-width="1.5" fill="none"/>
  </g>
  <g font-family="ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif" fill="${PALETTE.foam}" text-anchor="middle">
    <text x="50%" y="${h * 0.45}" font-size="${fontSize * 1.6}" font-weight="700" letter-spacing="2">${escape(label.toUpperCase())}</text>
    <text x="50%" y="${h * 0.55}" font-size="${fontSize * 0.9}" fill="${PALETTE.sky}" opacity="0.9">${w} × ${h}  ·  PLACEHOLDER</text>
    <text x="50%" y="${h * 0.62}" font-size="${fontSize * 0.7}" fill="${PALETTE.foam}" opacity="0.55">${escape(file)}</text>
  </g>
  <rect x="12" y="12" width="${w - 24}" height="${h - 24}" fill="none" stroke="${accent}" stroke-opacity="0.35" stroke-width="2" stroke-dasharray="6 8" rx="8"/>
</svg>`;
}

function svgIcon({ w, h, label, accent }) {
  // Icono genérico: círculo con halo y "rayo" estilizado en el accent.
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${escape(label)}">
  <defs>
    <radialGradient id="halo" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="${accent}" stop-opacity="0.45"/>
      <stop offset="1" stop-color="${accent}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="${PALETTE.deep}" rx="${w * 0.18}"/>
  <circle cx="50%" cy="50%" r="${w * 0.48}" fill="url(#halo)"/>
  <g stroke="${accent}" stroke-width="${Math.max(1.2, w / 36)}" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="M ${w * 0.55} ${h * 0.22} L ${w * 0.38} ${h * 0.52} L ${w * 0.52} ${h * 0.52} L ${w * 0.40} ${h * 0.80} L ${w * 0.62} ${h * 0.48} L ${w * 0.48} ${h * 0.48} Z" fill="${accent}" fill-opacity="0.18"/>
  </g>
  <rect x="2" y="2" width="${w - 4}" height="${h - 4}" rx="${w * 0.18}" fill="none" stroke="${accent}" stroke-opacity="0.4" stroke-width="1"/>
</svg>`;
}

function svgLogo({ w, h, label, accent }) {
  // Wordmark "ELECOL" minimal con un rayo al lado.
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${escape(label)}">
  <rect width="100%" height="100%" fill="transparent"/>
  <g font-family="ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif" font-weight="800" letter-spacing="4">
    <text x="${h * 1.0}" y="${h * 0.72}" font-size="${h * 0.66}" fill="${PALETTE.foam}">ELE<tspan fill="${accent}">COL</tspan></text>
  </g>
  <path d="M ${h * 0.18} ${h * 0.25} L ${h * 0.55} ${h * 0.25} L ${h * 0.35} ${h * 0.50} L ${h * 0.62} ${h * 0.50} L ${h * 0.28} ${h * 0.85} L ${h * 0.42} ${h * 0.55} L ${h * 0.20} ${h * 0.55} Z" fill="${accent}"/>
</svg>`;
}

function svgIso({ w, h, accent }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="ELECOL">
  <rect width="100%" height="100%" fill="${PALETTE.deep}" rx="${w * 0.22}"/>
  <path d="M ${w * 0.42} ${h * 0.18} L ${w * 0.78} ${h * 0.18} L ${w * 0.50} ${h * 0.46} L ${w * 0.74} ${h * 0.46} L ${w * 0.32} ${h * 0.82} L ${w * 0.52} ${h * 0.54} L ${w * 0.30} ${h * 0.54} Z" fill="${accent}"/>
</svg>`;
}

function svgDot({ w, h, accent }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="dot">
  <defs>
    <radialGradient id="g" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="${accent}" stop-opacity="0.9"/>
      <stop offset="0.4" stop-color="${accent}" stop-opacity="0.35"/>
      <stop offset="1" stop-color="${accent}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="50%" cy="50%" r="50%" fill="url(#g)"/>
  <circle cx="50%" cy="50%" r="${Math.max(1, w * 0.15)}" fill="${PALETTE.foam}"/>
</svg>`;
}

function svgMap({ w, h, label, accent }) {
  // "Mapa" estilizado: blob suave que evoca el contorno de LATAM.
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${escape(label)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${PALETTE.deep}"/>
      <stop offset="1" stop-color="#020330"/>
    </linearGradient>
    <radialGradient id="g" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="${accent}" stop-opacity="0.2"/>
      <stop offset="1" stop-color="${accent}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="50%" cy="50%" r="42%" fill="url(#g)"/>
  <g fill="none" stroke="${PALETTE.electric}" stroke-opacity="0.55" stroke-width="1.5">
    <path d="M ${w * 0.48} ${h * 0.10}
             C ${w * 0.62} ${h * 0.18}, ${w * 0.70} ${h * 0.32}, ${w * 0.64} ${h * 0.46}
             C ${w * 0.74} ${h * 0.56}, ${w * 0.62} ${h * 0.72}, ${w * 0.54} ${h * 0.84}
             C ${w * 0.46} ${h * 0.92}, ${w * 0.38} ${h * 0.86}, ${w * 0.40} ${h * 0.72}
             C ${w * 0.30} ${h * 0.62}, ${w * 0.32} ${h * 0.46}, ${w * 0.40} ${h * 0.36}
             C ${w * 0.36} ${h * 0.22}, ${w * 0.42} ${h * 0.12}, ${w * 0.48} ${h * 0.10} Z"/>
  </g>
  <g>
    <circle cx="${w * 0.46}" cy="${h * 0.30}" r="6" fill="${PALETTE.solar}"/>
    <circle cx="${w * 0.54}" cy="${h * 0.44}" r="6" fill="${PALETTE.cyan}"/>
    <circle cx="${w * 0.50}" cy="${h * 0.62}" r="6" fill="${PALETTE.solar}"/>
    <circle cx="${w * 0.44}" cy="${h * 0.76}" r="6" fill="${PALETTE.cyan}"/>
  </g>
  <text x="50%" y="${h * 0.96}" text-anchor="middle" font-family="ui-sans-serif, system-ui, -apple-system, sans-serif" font-size="${Math.max(14, h / 40)}" fill="${PALETTE.foam}" opacity="0.5">${escape(label)} · PLACEHOLDER</text>
</svg>`;
}

// ---- Main -------------------------------------------------------------------

function targetPath(asset) {
  // Reglas:
  //   - Si el archivo es .svg → se escribe directo (sirve como placeholder y como naming canónico).
  //   - Si no es .svg (.webp, .mp4, .webm, .png, .ico) → escribimos `<file>.placeholder.svg`
  //     junto al filename canónico, para que el real (cuando llegue) lo reemplace sin colisión.
  const isSvg = asset.file.toLowerCase().endsWith('.svg');
  const filename = isSvg ? asset.file : `${asset.file}.placeholder.svg`;
  return join(ROOT, asset.dir, filename);
}

function render(asset) {
  switch (asset.kind) {
    case 'icon': return svgIcon(asset);
    case 'logo': return svgLogo(asset);
    case 'iso': return svgIso(asset);
    case 'dot': return svgDot(asset);
    case 'map': return svgMap(asset);
    default: return svgHero(asset);
  }
}

function main() {
  let written = 0;
  let skippedReal = 0;
  for (const asset of ASSETS) {
    const dir = join(ROOT, asset.dir);
    mkdirSync(dir, { recursive: true });

    const isSvg = asset.file.toLowerCase().endsWith('.svg');
    const realPath = join(dir, asset.file);
    // Si NO es svg, y el archivo real ya existe (el diseñador lo entregó), no
    // sobreescribir nada y no generar placeholder de respaldo.
    if (!isSvg && existsSync(realPath)) {
      skippedReal++;
      continue;
    }

    const out = targetPath(asset);
    writeFileSync(out, render(asset), 'utf8');
    written++;
  }
  console.log(`ELECOL placeholders: escritos ${written}, omitidos por asset real ${skippedReal}.`);
}

main();
