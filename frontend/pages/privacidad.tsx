import Head from 'next/head';
import Image from 'next/image';

/**
 * Política de tratamiento de datos personales de Gloma (Ley 1581 de 2012).
 *
 * La enlaza el formulario "Quiero que me contacten" de la landing, que exige
 * aceptarla antes de enviar (el backend guarda cuándo se aceptó en
 * `leads.acepto_privacidad_at`). Es pública: vive en el allowlist del
 * middleware para los dominios de la marca y en `PUBLIC_PAGES` de `_app.tsx`.
 */

const BRAND = {
  bgBase: '#101817',
  mint: '#4DB6AC',
  text: '#E6EFEE',
  textMuted: 'rgba(230,239,238,0.72)',
  border: 'rgba(77,182,172,0.15)',
};

const VIGENCIA = '27 de septiembre de 2026';

const SECCIONES: { titulo: string; parrafos: string[] }[] = [
  {
    titulo: '1. Quién es el responsable',
    parrafos: [
      'Gloma, empresa colombiana de tecnología con domicilio en la Calle 36, Vía Jamundí #128-321, Cali, Valle del Cauca. Correo de contacto para asuntos de datos personales: contacto@glomacx.com.',
    ],
  },
  {
    titulo: '2. Qué datos recogemos',
    parrafos: [
      'En el formulario de contacto de glomacx.com: nombre, correo electrónico, teléfono, nombre de la agencia y el rango de chats que reciben al mes.',
      'En el chat de la página: los mensajes que escribes y, si decides agendar una demostración, el correo y el horario que elijas.',
      'Además, por seguridad, la dirección IP y el navegador desde el que se envía el formulario.',
    ],
  },
  {
    titulo: '3. Para qué los usamos',
    parrafos: [
      'Para contactarte y responder a tu solicitud, agendar y realizar la demostración, enviarte la información comercial de Gloma que pediste y preparar una propuesta con el volumen de tu operación.',
      'No vendemos ni cedemos tus datos a terceros para fines comerciales.',
    ],
  },
  {
    titulo: '4. Dónde se guardan',
    parrafos: [
      'Los datos se almacenan en la infraestructura de Amazon Web Services, en servidores ubicados en Brasil, con acceso restringido al equipo de Gloma. Al aceptar esta política autorizas esa transferencia internacional de datos.',
    ],
  },
  {
    titulo: '5. Tus derechos',
    parrafos: [
      'Como titular puedes conocer, actualizar y rectificar tus datos; pedir prueba de la autorización que nos diste; saber qué uso les hemos dado; revocar la autorización o pedir que los eliminemos cuando no exista un deber legal de conservarlos; y presentar quejas ante la Superintendencia de Industria y Comercio.',
    ],
  },
  {
    titulo: '6. Cómo ejercerlos',
    parrafos: [
      'Escríbenos a contacto@glomacx.com indicando tu nombre, el correo o teléfono con que te registraste y lo que solicitas. Las consultas se responden en un máximo de diez (10) días hábiles y los reclamos en un máximo de quince (15) días hábiles, en los términos de la Ley 1581 de 2012.',
    ],
  },
  {
    titulo: '7. Vigencia',
    parrafos: [
      `Esta política rige desde el ${VIGENCIA}. Los datos se conservan mientras sean necesarios para las finalidades descritas o mientras no pidas su eliminación. Si la cambiamos, publicaremos la nueva versión en esta misma página.`,
    ],
  },
];

export default function Privacidad() {
  return (
    <>
      <Head>
        <title>Política de tratamiento de datos · Gloma</title>
        <meta name="robots" content="noindex" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <style jsx global>{`
        html,
        body {
          background-color: ${BRAND.bgBase};
        }
      `}</style>
      <main
        className="min-h-screen px-6 py-12 md:py-16"
        style={{ backgroundColor: BRAND.bgBase, color: BRAND.text, fontFamily: 'Inter, system-ui, sans-serif' }}
      >
        <div className="max-w-3xl mx-auto">
          <a href="/" aria-label="Volver a Gloma" className="inline-block mb-10">
            <Image
              src="/gloma/logo_blancotrans.png"
              alt="Gloma"
              width={320}
              height={192}
              className="object-contain h-20 w-auto"
            />
          </a>
          <h1
            className="text-3xl md:text-4xl leading-tight mb-3"
            style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700 }}
          >
            Política de tratamiento de datos personales
          </h1>
          <p className="text-sm mb-10" style={{ color: BRAND.textMuted }}>
            Ley 1581 de 2012 · Vigente desde el {VIGENCIA}
          </p>
          <div className="space-y-8">
            {SECCIONES.map((s) => (
              <section key={s.titulo} className="pt-6" style={{ borderTop: `1px solid ${BRAND.border}` }}>
                <h2 className="text-lg font-semibold mb-3" style={{ color: BRAND.mint }}>
                  {s.titulo}
                </h2>
                {s.parrafos.map((p) => (
                  <p key={p} className="text-base leading-relaxed mb-3" style={{ color: BRAND.textMuted }}>
                    {p}
                  </p>
                ))}
              </section>
            ))}
          </div>
          <a
            href="/"
            className="inline-block mt-12 px-6 py-3 rounded-full text-sm font-semibold"
            style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
          >
            Volver a Gloma
          </a>
        </div>
      </main>
    </>
  );
}
