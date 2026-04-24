import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState } from 'react';

/**
 * 404 brandeado Gloma. Se muestra cuando:
 *  - Alguien entra a una ruta inexistente.
 *  - Middleware rewritea rutas de plataforma (login, bots, …) cuando el host
 *    es glomabeauty.com, porque la plataforma vive bajo el dominio de Amplify.
 *
 * Diseño alineado con /gloma (Syne + Inter, rosa empolvado + marrón tierra).
 */

const BRAND = {
  rose: '#F7D1CD',
  brown: '#5E503F',
  cream: '#FDFBF7',
  roseSoft: '#FBE9E7',
  brownLight: '#8B7A67',
};

export default function NotFound() {
  const [isGloma, setIsGloma] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const h = window.location.hostname.toLowerCase();
      setIsGloma(h === 'glomabeauty.com' || h === 'www.glomabeauty.com');
    }
  }, []);

  return (
    <>
      <Head>
        <title>Página no encontrada — Gloma</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </Head>
      <div
        className="min-h-screen flex items-center justify-center px-6"
        style={{ backgroundColor: BRAND.cream, color: BRAND.brown }}
      >
        <div className="max-w-lg w-full text-center">
          <div
            className="inline-block text-xs tracking-widest uppercase mb-6 px-3 py-1 rounded-full"
            style={{ backgroundColor: BRAND.roseSoft, color: BRAND.brown }}
          >
            Error 404
          </div>
          <h1
            className="text-5xl md:text-7xl mb-5 leading-none"
            style={{
              fontFamily: 'Syne, system-ui, sans-serif',
              fontWeight: 800,
              color: BRAND.brown,
            }}
          >
            No encontramos esta página
          </h1>
          <p
            className="text-base md:text-lg mb-10"
            style={{
              fontFamily: 'Inter, system-ui, sans-serif',
              color: BRAND.brownLight,
            }}
          >
            {isGloma
              ? 'Puede que el enlace sea viejo o que la página haya cambiado de lugar. Vuelve al inicio y conversemos.'
              : 'La dirección que buscas no existe. Te llevamos de regreso.'}
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/"
              className="px-6 py-3 rounded-full text-sm font-semibold transition-opacity hover:opacity-90"
              style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
            >
              Volver al inicio
            </Link>
            <a
              href="https://wa.me/573003187871?text=Hola%20Gloma"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 rounded-full text-sm font-semibold transition-opacity hover:opacity-90"
              style={{ backgroundColor: BRAND.rose, color: BRAND.brown }}
            >
              Escríbenos por WhatsApp
            </a>
          </div>
        </div>
      </div>
    </>
  );
}
