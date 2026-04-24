import '../styles/globals.css';
import type { AppProps } from 'next/app';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

// Rutas públicas de la plataforma que no requieren token
const PUBLIC_PAGES = ['/login', '/register', '/gloma', '/404'];

// Hosts donde vive SOLO la landing pública — no hay plataforma que proteger
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

  if (!ready && !PUBLIC_PAGES.includes(router.pathname) && !hostIsPublicLanding()) {
    return null;
  }

  return <Component {...pageProps} />;
}
