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

module.exports = nextConfig;
