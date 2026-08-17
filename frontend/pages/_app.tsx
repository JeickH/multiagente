import '../styles/globals.css';
import type { AppProps } from 'next/app';
import Head from 'next/head';
import { useRouter } from 'next/router';
import { useCallback, useEffect, useState } from 'react';
import { haySesion } from '../lib/session';

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
  '/mascotas-panel': 'Mascotas · Gloma',
};

// Rutas públicas de la plataforma que no requieren token.
// `/mascotas` es el chat ciudadano de "Recupera Tu Mascota": quien llega ahí
// no tiene cuenta ni debe tenerla. (`/mascotas-panel` NO va aquí: ese es el
// panel privado de la cuenta y sí exige sesión.)
const PUBLIC_PAGES = [
  '/login', '/register', '/gloma', '/automatas', '/elecol', '/404', '/mascotas',
];

// Hosts donde vive SOLO contenido público — no hay plataforma que proteger.
// app.glomabeauty.com NO va aquí: es la URL bonita de la plataforma y debe
// pasar por el guard de autenticación normal.
const PUBLIC_HOSTS = [
  'glomabeauty.com',
  'www.glomabeauty.com',
  'mascotasperdidascolombia.com',
  'www.mascotasperdidascolombia.com',
  'mascotasperdidascali.glomabeauty.com',
];

function hostIsPublicLanding(): boolean {
  if (typeof window === 'undefined') return false;
  return PUBLIC_HOSTS.includes(window.location.hostname.toLowerCase());
}

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const [autorizado, setAutorizado] = useState(false);

  // Rutas que se pintan sin sesión. Se evalúa igual en servidor y en cliente,
  // así que las landings salen en el HTML inicial (importa para buscadores).
  const rutaPublica = PUBLIC_PAGES.includes(router.pathname);

  /**
   * El guard. `haySesion()` valida el `exp` del JWT, no solo que exista la
   * llave en localStorage: un token vencido cuenta como no tener sesión y
   * manda al login, que es lo que se espera al entrar a app.glomabeauty.com
   * sin sesión activa.
   */
  const revisarSesion = useCallback(() => {
    // En el dominio público de la landing nunca redirigimos a /login —
    // la plataforma vive bajo otro dominio.
    if (rutaPublica || hostIsPublicLanding()) {
      setAutorizado(true);
      return;
    }
    if (haySesion()) {
      setAutorizado(true);
      return;
    }
    // Se apaga primero para que no quede pintada la pantalla anterior
    // mientras el router hace el cambio.
    setAutorizado(false);
    router.replace('/login');
  }, [router, rutaPublica]);

  useEffect(() => {
    revisarSesion();
  }, [revisarSesion]);

  // El token puede vencerse con la pestaña abierta y quieta. Volver a ella es
  // justo el momento en que el usuario espera encontrarse el login.
  useEffect(() => {
    const alVolver = () => {
      if (document.visibilityState === 'visible') revisarSesion();
    };
    window.addEventListener('focus', revisarSesion);
    document.addEventListener('visibilitychange', alVolver);
    return () => {
      window.removeEventListener('focus', revisarSesion);
      document.removeEventListener('visibilitychange', alVolver);
    };
  }, [revisarSesion]);

  // Mientras se resuelve el guard de sesión no se pinta la página, pero el
  // título sí: si no, la pestaña muestra la URL cruda hasta que carga.
  const mostrarPagina = rutaPublica || autorizado;

  return (
    <>
      <Head>
        <title>{TITULOS[router.pathname] || 'Gloma'}</title>
      </Head>
      {mostrarPagina ? <Component {...pageProps} /> : null}
    </>
  );
}
