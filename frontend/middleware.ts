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
 *   cualquier otra   → 404 brandeado (la plataforma NO vive bajo el apex/www)
 *
 * app.glomabeauty.com            → plataforma completa (login, /bots, etc.)
 * main.<amplify>.amplifyapp.com  → idem (URL técnica de respaldo)
 * localhost y otros hosts         → sin intervención.
 *
 * Sprint "Ayuda a Cali" — dominio propio `mascotasperdidascolombia.com`
 * (comprado en Hostinger, con el DNS delegado a Route 53), más el subdominio
 * `mascotasperdidascali.glomabeauty.com` que se mantiene como respaldo:
 *
 *   /                → chat de Recupera Tu Mascota (rewrite a /mascotas)
 *   /api/mascotas/*  → passthrough (chat, fotos y listado del bot)
 *   cualquier otra   → 404 brandeado (la plataforma NO vive en estos dominios,
 *                      y el panel privado tampoco: ese se usa desde
 *                      app.glomabeauty.com con sesión iniciada)
 */

const GLOMA_HOSTS = new Set(['glomabeauty.com', 'www.glomabeauty.com']);
const MASCOTAS_HOSTS = new Set([
  'mascotasperdidascolombia.com',
  'www.mascotasperdidascolombia.com',
  'mascotasperdidascali.glomabeauty.com',
]);

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

function isMascotasAllowed(pathname: string): boolean {
  if (pathname === '/') return true;
  if (pathname === '/favicon.ico') return true;
  if (pathname.startsWith('/_next')) return true;
  // Solo los endpoints públicos del bot. `/api/mascotas/panel*` queda fuera a
  // propósito: el panel exige JWT y se usa desde la app, no desde este dominio.
  if (pathname.startsWith('/api/mascotas/') && !pathname.startsWith('/api/mascotas/panel')) {
    return true;
  }
  return false;
}

export function middleware(req: NextRequest) {
  const host = (req.headers.get('host') || '').toLowerCase();
  const { pathname } = req.nextUrl;

  if (MASCOTAS_HOSTS.has(host)) {
    // La raíz sirve el chat (la URL pública no cambia).
    if (pathname === '/') {
      return NextResponse.rewrite(new URL('/mascotas', req.url));
    }
    if (isMascotasAllowed(pathname)) {
      return NextResponse.next();
    }
    return NextResponse.rewrite(new URL(NOT_FOUND_PATH, req.url));
  }

  if (!GLOMA_HOSTS.has(host)) return NextResponse.next();

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
