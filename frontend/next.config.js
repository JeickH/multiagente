/** @type {import('next').NextConfig} */
const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  images: {
    // Permitimos servir SVG a través del optimizador de imágenes de Next porque
    // los SVG locales en /public/elecol/* son placeholders generados por nosotros
    // (frontend/scripts/generate_elecol_placeholders.mjs). CSP adicional evita
    // ejecución de scripts si llegara un SVG malicioso.
    dangerouslyAllowSVG: true,
    contentDispositionType: 'attachment',
    contentSecurityPolicy: "default-src 'self'; script-src 'none'; sandbox;",
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

/**
 * Avisos de la demo pública (`/demo`, Sprint 32) en el build de producción.
 * No fallan el build: lo dejan escrito en el log (Amplify) para que no pase
 * desapercibido.
 *  - Sin `NEXT_PUBLIC_DEMO_API_URL` la demo llama por el rewrite `/api`, y el
 *    backend no ve la IP real del prospecto (#608, A1): los topes por IP no
 *    sirven.
 *  - `NEXT_PUBLIC_DEMO_MOCK=1` deja la demo simulada, sin backend.
 * `NEXT_PUBLIC_*` se hornea al compilar: cambiar la env var exige re-build.
 */
const { PHASE_PRODUCTION_BUILD } = require('next/constants');

module.exports = (phase) => {
  // Next carga este archivo en cada worker del build; la marca en el entorno
  // (que heredan los workers) evita repetir el aviso.
  if (phase === PHASE_PRODUCTION_BUILD && !process.env.__GLOMA_AVISOS_DEMO) {
    process.env.__GLOMA_AVISOS_DEMO = '1';
    if (!process.env.NEXT_PUBLIC_DEMO_API_URL) {
      console.warn(
        '\n⚠️  [demo] NEXT_PUBLIC_DEMO_API_URL no está definida: /demo llamará a la API por el ' +
          'rewrite /api y el backend no verá la IP real (topes por IP inútiles, #608 A1). ' +
          'En producción debe ser https://api.glomacx.com.\n',
      );
    }
    if (process.env.NEXT_PUBLIC_DEMO_MOCK === '1') {
      console.warn(
        '\n⚠️  [demo] NEXT_PUBLIC_DEMO_MOCK=1 en un build de producción: /demo queda SIMULADA ' +
          '(no crea bots ni guarda leads). Quítala salvo que sea a propósito.\n',
      );
    }
  }
  return nextConfig;
};
