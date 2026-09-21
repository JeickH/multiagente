import Head from 'next/head';

/**
 * "Recupera Tu Mascota" — página de cierre.
 *
 * Decisión del CEO (2026-09-20): `mascotasperdidascolombia.com` deja de
 * mantenerse. Lo que vivía acá era un chat a pantalla completa con el bot
 * ("Huella"), la antesala de intake, la subida de fotos y la descarga del
 * listado. Todo eso se retiró: **esta página es estática y no llama al
 * backend**. Ni el chat, ni `POST /api/mascotas/chat`, ni
 * `POST /api/mascotas/foto`, ni `GET /api/mascotas/listado/enlace`.
 *
 * El motivo de que sea estática es operativo: así los endpoints del bot se
 * pueden apagar después, en el orden que se quiera, sin que el visitante se
 * encuentre un 500 o un spinner eterno. Si alguien vuelve a poner una llamada
 * al backend en esta pantalla, ese candado se pierde.
 *
 * Los endpoints del backend NO se tocaron: el panel privado
 * (`/mascotas-panel`, bajo `app.glomacx.com` y con sesión) sigue usando
 * `/mascotas/panel*`.
 *
 * La marca del pie ("Tecnología de Gloma App") vive solo en este sitio; la
 * plataforma y la landing de Gloma conservan la suya.
 */

// Identidad Gloma: Deep Forest / Algorithmic Mint, Syne + Inter. Los tonos se
// resuelven por variables CSS para que la página se vea bien en claro y en
// oscuro sin duplicar el marcado.
const BRAND = {
  forest: '#004D40',
  mint: '#4DB6AC',
  softMint: '#E0F2F1',
};

export default function MascotasCierre() {
  return (
    <>
      <Head>
        <title>Gracias · Recupera Tu Mascota</title>
        <meta
          name="description"
          content="Recupera Tu Mascota cerró. Gracias a todos los que reportaron, compartieron y salieron a buscar."
        />
        {/* El sitio ya no presta servicio: sacarlo del índice evita que alguien
            llegue desde una búsqueda esperando reportar una mascota. */}
        <meta name="robots" content="noindex, follow" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600&display=swap"
          rel="stylesheet"
        />
      </Head>

      <style jsx global>{`
        html,
        body,
        #__next {
          min-height: 100%;
          margin: 0;
        }
        .rt-cierre {
          --rt-bg: #f7faf9;
          --rt-panel: #ffffff;
          --rt-borde: rgba(0, 77, 64, 0.14);
          --rt-texto: #16211f;
          --rt-tenue: rgba(22, 33, 31, 0.68);
          --rt-apagado: rgba(22, 33, 31, 0.45);
          --rt-acento: ${BRAND.forest};
          --rt-halo: rgba(77, 182, 172, 0.18);
        }
        @media (prefers-color-scheme: dark) {
          .rt-cierre {
            --rt-bg: #101817;
            --rt-panel: rgba(255, 255, 255, 0.04);
            --rt-borde: rgba(77, 182, 172, 0.2);
            --rt-texto: #e6efee;
            --rt-tenue: rgba(230, 239, 238, 0.7);
            --rt-apagado: rgba(230, 239, 238, 0.45);
            --rt-acento: ${BRAND.mint};
            --rt-halo: rgba(77, 182, 172, 0.12);
          }
        }
        body {
          background-color: var(--rt-bg, #f7faf9);
          font-family: Inter, system-ui, -apple-system, sans-serif;
        }
        .rt-cierre ::selection {
          background: ${BRAND.mint};
          color: #0b1413;
        }
      `}</style>

      <div
        className="rt-cierre flex min-h-screen flex-col"
        style={{ backgroundColor: 'var(--rt-bg)', color: 'var(--rt-texto)' }}
      >
        <main className="flex flex-1 items-center justify-center px-5 py-12 sm:py-16">
          <article
            className="w-full max-w-xl rounded-2xl px-6 py-10 sm:px-10 sm:py-12"
            style={{
              backgroundColor: 'var(--rt-panel)',
              border: '1px solid var(--rt-borde)',
              boxShadow: '0 24px 60px -32px var(--rt-halo)',
            }}
          >
            <p
              className="text-[11px] uppercase tracking-[0.18em]"
              style={{ color: 'var(--rt-apagado)' }}
            >
              Recupera Tu Mascota
            </p>

            <h1
              className="mt-3 text-4xl sm:text-5xl"
              style={{
                fontFamily: 'Syne, system-ui, sans-serif',
                fontWeight: 700,
                color: 'var(--rt-acento)',
                letterSpacing: '-0.02em',
              }}
            >
              Gracias.
            </h1>

            <div
              className="mt-6 space-y-5 text-[15px] leading-relaxed sm:text-base"
              style={{ color: 'var(--rt-tenue)' }}
            >
              <p>
                Este sitio se armó en los días del terremoto, para que las familias que
                perdían a su mascota y la gente que se encontraba un animal en la calle
                pudieran cruzarse en alguna parte.
              </p>
              <p>
                Funcionó porque mucha gente se tomó el trabajo: escribir el reporte con
                todos los detalles, mandar la foto, pasarle el enlace al vecino, salir a
                preguntar por el barrio. Gracias por eso.
              </p>
              <p>
                Hoy lo cerramos. El sitio ya no recibe reportes nuevos y no tiene quién
                lo atienda, así que lo dejamos en esta nota y nada más.
              </p>
              <p>
                Si todavía estás buscando a tu mascota, busca un grupo activo de tu
                ciudad que te acompañe. Nosotros de aquí en adelante no podemos ayudarte
                con eso, y preferimos decírtelo de frente antes que dejarte escribiéndole
                a un lugar vacío.
              </p>
            </div>

            <div
              className="mt-9 border-t pt-6 text-sm"
              style={{ borderColor: 'var(--rt-borde)', color: 'var(--rt-apagado)' }}
            >
              <p style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 600 }}>
                El equipo de Gloma
              </p>
              <p className="mt-1">Colombia, 2026</p>
            </div>
          </article>
        </main>

        {/* Firma de la tecnología. Vive SOLO en este sitio: la plataforma y la
            landing conservan su marca sin cambios. */}
        <footer
          className="shrink-0 px-5 pb-6 text-center text-[11px]"
          style={{
            color: 'var(--rt-apagado)',
            paddingBottom: 'calc(1.5rem + env(safe-area-inset-bottom))',
          }}
        >
          Tecnología de{' '}
          <a
            href="https://www.instagram.com/gloma_app/"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold hover:underline"
            style={{ color: 'var(--rt-acento)' }}
            title="Ver @gloma_app en Instagram"
          >
            Gloma App
          </a>
        </footer>
      </div>
    </>
  );
}
