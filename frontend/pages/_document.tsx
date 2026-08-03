import { Html, Head, Main, NextScript } from 'next/document';

export default function Document() {
  return (
    <Html lang="es">
      <Head>
        {/* Iconos de marca (generados desde identidad_gloma/logo_blancotrans).
            El logo es blanco sobre transparente, así que va montado sobre una
            placa Deep Forest: sin ella desaparecería en las pestañas claras.
            A 16-32 px el wordmark "GLOMA" es ilegible, por eso el icono usa
            solo el símbolo. `apple-touch-icon` es el que toma iOS al agregar
            la página a la pantalla de inicio. */}
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="icon" type="image/png" sizes="32x32" href="/icons/favicon-32.png" />
        <link rel="apple-touch-icon" sizes="180x180" href="/icons/apple-touch-icon.png" />
        <link rel="manifest" href="/site.webmanifest" />
        {/* Nombre bajo el icono en la pantalla de inicio del iPhone */}
        <meta name="apple-mobile-web-app-title" content="Gloma" />
        <meta name="theme-color" content="#004D40" />

        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}

