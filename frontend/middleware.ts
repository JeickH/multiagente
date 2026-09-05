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
 * Sprint 28: la marca se muda a `glomacx.com`. Este paso es **aditivo**:
 * `glomacx.com` y `www.glomacx.com` sirven la landing igual que el dominio
 * viejo, y `app.glomacx.com` cae en el passthrough (plataforma completa),
 * exactamente como `app.glomabeauty.com`. El redirect 301 del dominio viejo
 * al nuevo se activa en un segundo commit, y sólo cuando `glomacx.com` ya
 * resuelva con HTTPS: si se activara antes, el redirect mandaría a todos los
 * usuarios a un dominio muerto.
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

/**
 * Sprint 28, fase 2: el dominio viejo redirecciona al nuevo, conservando la
 * ruta y el query string. `app.glomabeauty.com/mensajes` cae en
 * `app.glomacx.com/mensajes`, y de ahí el guard de sesión hace lo de siempre:
 * si no hay sesión válida, al login del dominio nuevo.
 *
 * El 301 es permanente a propósito — la marca se mudó — pero eso también
 * significa que el navegador lo cachea de forma agresiva y prácticamente
 * indefinida. Volver atrás no es cambiar este mapa: a los usuarios que ya lo
 * recibieron habría que sacarlos del caché.
 */
const REDIRECCIONES_LEGADO: Record<string, string> = {
  'glomabeauty.com': 'glomacx.com',
  'www.glomabeauty.com': 'www.glomacx.com',
  'app.glomabeauty.com': 'app.glomacx.com',
};

const GLOMA_HOSTS = new Set([
  'glomabeauty.com',
  'www.glomabeauty.com',
  'glomacx.com',
  'www.glomacx.com',
]);
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

  // Dominio viejo → dominio nuevo, antes que cualquier otra regla.
  //
  // `/api/*` queda FUERA del redirect a propósito. Un navegador que ya tenía
  // la plataforma abierta en el dominio viejo sigue disparando XHR contra él;
  // si esas llamadas se redirigieran, el salto sería cross-origin y el
  // navegador descarta el header `Authorization` al seguirlo (protección
  // estándar contra fuga de credenciales), así que la sesión se caería sola a
  // mitad de uso. Dejándolas pasar, esas pestañas terminan su trabajo contra
  // el host viejo y se mudan al nuevo en la siguiente navegación.
  const destinoLegado = REDIRECCIONES_LEGADO[host];
  if (destinoLegado && !pathname.startsWith('/api/')) {
    const destino = req.nextUrl.clone();
    destino.protocol = 'https:';
    destino.host = destinoLegado;
    destino.port = '';
    return NextResponse.redirect(destino, 301);
  }

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
