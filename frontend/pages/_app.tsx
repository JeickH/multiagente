import '../styles/globals.css';
import type { AppProps } from 'next/app';
import Head from 'next/head';
import { useRouter } from 'next/router';
import { useCallback, useEffect, useState } from 'react';
import { haySesion, msParaVencer } from '../lib/session';

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
  // Ruta que YA pasó el guard, no un simple booleano: al navegar entre
  // pantallas privadas el estado sobrevive al cambio de ruta, y un `true`
  // heredado alcanzaría a pintar la pantalla nueva antes de que el guard
  // vuelva a correr. Atándolo a la ruta, la autorización de una no sirve
  // para la siguiente.
  const [autorizadaEn, setAutorizadaEn] = useState<string | null>(null);

  // Rutas que se pintan sin sesión. Se evalúa igual en servidor y en cliente,
  // así que las landings salen en el HTML inicial (importa para buscadores).
  const rutaPublica = PUBLIC_PAGES.includes(router.pathname);
  const ruta = router.pathname;

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
      setAutorizadaEn(ruta);
      return;
    }
    if (haySesion()) {
      setAutorizadaEn(ruta);
      return;
    }
    // Se apaga primero para que no quede pintada la pantalla anterior
    // mientras el router hace el cambio.
    setAutorizadaEn(null);
    router.replace('/login');
  }, [router, ruta, rutaPublica]);

  useEffect(() => {
    revisarSesion();
  }, [revisarSesion]);

  // El token puede vencerse con la pestaña abierta y quieta. Estos son los
  // momentos en que hay que volver a mirar:
  //  - `focus` / `visibilitychange`: el usuario vuelve a la pestaña, que es
  //    justo cuando espera encontrarse el login.
  //  - `pageshow`: vuelve con el botón "atrás" y el navegador restaura la
  //    página desde el bfcache, ya pintada y sin remontar nada.
  //  - el temporizador: la pestaña sigue enfocada y quieta en una pantalla que
  //    no llama al backend (`/` es exactamente ese caso), así que nadie más se
  //    enteraría de que la sesión venció.
  useEffect(() => {
    const alVolver = () => {
      if (document.visibilityState === 'visible') revisarSesion();
    };
    window.addEventListener('focus', revisarSesion);
    window.addEventListener('pageshow', revisarSesion);
    document.addEventListener('visibilitychange', alVolver);

    const restante = msParaVencer();
    const temporizador =
      restante === null ? null : window.setTimeout(revisarSesion, restante + 500);

    return () => {
      window.removeEventListener('focus', revisarSesion);
      window.removeEventListener('pageshow', revisarSesion);
      document.removeEventListener('visibilitychange', alVolver);
      if (temporizador !== null) window.clearTimeout(temporizador);
    };
  }, [revisarSesion]);

  // Mientras se resuelve el guard de sesión no se pinta la página, pero el
  // título sí: si no, la pestaña muestra la URL cruda hasta que carga.
  const mostrarPagina = rutaPublica || autorizadaEn === ruta;

  return (
    <>
      <Head>
        <title>{TITULOS[router.pathname] || 'Gloma'}</title>
      </Head>
      {mostrarPagina ? <Component {...pageProps} /> : null}
    </>
  );
}
