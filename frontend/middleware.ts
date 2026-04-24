import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Sprint 12: separación de dominios.
 *
 * glomabeauty.com (y www)
 *   /                → landing Gloma (rewrite interno a /gloma, URL navegador queda en /)
 *   /gloma/*         → assets de la landing
 *   /api/landing/*   → passthrough (form de contacto)
 *   /favicon.ico     → passthrough
 *   /_next/*         → internals de Next
 *   cualquier otra   → 404 brandeado (la plataforma vive SOLO bajo el dominio de Amplify)
 *
 * main.<amplify>.amplifyapp.com  → comportamiento normal (sin intervención del middleware).
 * localhost y otros hosts         → sin cambio.
 */

const GLOMA_HOSTS = new Set(['glomabeauty.com', 'www.glomabeauty.com']);

// Path no existente: garantiza que Next responda con status 404 + pages/404.tsx
const NOT_FOUND_PATH = '/__gloma_not_found__';

function isGlomaAllowed(pathname: string): boolean {
  if (pathname === '/') return true;
  if (pathname === '/favicon.ico') return true;
  if (pathname.startsWith('/gloma')) return true;
  if (pathname.startsWith('/api/landing')) return true;
  if (pathname.startsWith('/_next')) return true;
  return false;
}

export function middleware(req: NextRequest) {
  const host = (req.headers.get('host') || '').toLowerCase();
  if (!GLOMA_HOSTS.has(host)) return NextResponse.next();

  const { pathname } = req.nextUrl;

  // Raíz sirve el contenido de la landing (URL pública no cambia).
  if (pathname === '/') {
    return NextResponse.rewrite(new URL('/gloma', req.url));
  }

  if (isGlomaAllowed(pathname)) {
    return NextResponse.next();
  }

  // Cualquier ruta de plataforma bajo glomabeauty.com → 404 brandeado.
  return NextResponse.rewrite(new URL(NOT_FOUND_PATH, req.url));
}

export const config = {
  matcher: ['/((?!_next/static|_next/image).*)'],
};
