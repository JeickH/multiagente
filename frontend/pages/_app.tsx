import '../styles/globals.css';
import type { AppProps } from 'next/app';
import Head from 'next/head';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

/**
 * Título de la pestaña por ruta. Convención: `Sección · Gloma` — el nombre de
 * la sección primero porque en una pestaña angosta el navegador corta por la
 * derecha, y es lo que el usuario necesita para distinguir entre varias
 * pestañas de la plataforma abiertas a la vez. Las landings de marca traen su
 * propio `<title>` (más largo, pensado para buscadores) y ganan sobre este,
 * porque el `Head` de la página se resuelve después del de `_app`.
 */
const TITULOS: Record<string, string> = {
  '/': 'Inicio · Gloma',
  '/login': 'Iniciar sesión · Gloma',
  '/register': 'Crear cuenta · Gloma',
  '/mensajes': 'Mensajes · Gloma',
  '/bots': 'Bots · Gloma',
  '/bots/[id]': 'Bot · Gloma',
  '/campanas': 'Campañas · Gloma',
  '/campanas/nueva': 'Nueva campaña · Gloma',
  '/campanas/plantillas': 'Plantillas · Gloma',
  '/campanas/plantillas/nueva': 'Nueva plantilla · Gloma',
  '/citas': 'Citas · Gloma',
  '/usuario': 'Mi plan · Gloma',
};

// Rutas públicas de la plataforma que no requieren token
const PUBLIC_PAGES = ['/login', '/register', '/gloma', '/automatas', '/elecol', '/404'];

// Hosts donde vive SOLO la landing pública — no hay plataforma que proteger.
// app.glomabeauty.com NO va aquí: es la URL bonita de la plataforma y debe
// pasar por el guard de autenticación normal.
const PUBLIC_HOSTS = ['glomabeauty.com', 'www.glomabeauty.com'];

function hostIsPublicLanding(): boolean {
  if (typeof window === 'undefined') return false;
  return PUBLIC_HOSTS.includes(window.location.hostname.toLowerCase());
}

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // En el dominio público de la landing nunca redirigimos a /login —
    // la plataforma vive bajo otro dominio.
    if (hostIsPublicLanding()) {
      setReady(true);
      return;
    }
    const token = localStorage.getItem('token');
    if (!token && !PUBLIC_PAGES.includes(router.pathname)) {
      router.replace('/login');
    } else {
      setReady(true);
    }
  }, [router.pathname]);

  // Mientras se resuelve el guard de sesión no se pinta la página, pero el
  // título sí: si no, la pestaña muestra la URL cruda hasta que carga.
  const esperandoSesion =
    !ready && !PUBLIC_PAGES.includes(router.pathname) && !hostIsPublicLanding();

  return (
    <>
      <Head>
        <title>{TITULOS[router.pathname] || 'Gloma'}</title>
      </Head>
      {esperandoSesion ? null : <Component {...pageProps} />}
    </>
  );
}
