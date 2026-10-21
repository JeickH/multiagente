import Head from 'next/head';
import Image from 'next/image';

/**
 * Autorización de tratamiento de datos personales (Ley 1581 de 2012 y
 * Decreto 1377 de 2013). Por decisión del CEO (2026-09-27) es corta: el
 * usuario autoriza, para contacto, marketing, promociones y novedades, sin
 * nombrar razón social ni NIT.
 *
 * Actualización del 2026-10-20 (#636, aprobada por el CEO): se agregan las
 * secciones de la demo de `/demo` (finalidad, datos, encargados con
 * transmisión internacional, conservación y derechos). Lo que ya decía la
 * página no cambia. El formulario de la demo también la enlaza.
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
const ACTUALIZACION = '20 de octubre de 2026';

const SECCIONES: { titulo: string; parrafos: string[] }[] = [
  {
    titulo: 'Autorización',
    parrafos: [
      'Al marcar la casilla del formulario de glomacx.com, o al escribirnos por el chat de la página, autorizas de manera previa, expresa e informada el tratamiento de tus datos personales, conforme a la Ley Estatutaria 1581 de 2012 y a su reglamentación, el Decreto 1377 de 2013.',
      'Los datos que entregas son tu nombre, correo electrónico, teléfono, el nombre de tu agencia y el rango de chats que reciben al mes.',
    ],
  },
  {
    titulo: 'Para qué autorizas el uso de tus datos',
    parrafos: [
      'Para contactarte y responder tu solicitud, agendar una demostración y enviarte información comercial: campañas de marketing, promociones y novedades del servicio, por correo electrónico, WhatsApp u otros medios de contacto que nos hayas dado.',
    ],
  },
  {
    titulo: 'Tus derechos',
    parrafos: [
      'Puedes conocer, actualizar o rectificar tus datos, y revocar esta autorización o pedir que dejemos de enviarte comunicaciones en cualquier momento, escribiendo a contacto@glomacx.com.',
    ],
  },
  // --- Demo de glomacx.com/demo (#636) ---
  {
    titulo: 'Si armas una demo en glomacx.com/demo',
    parrafos: [
      'Al marcar la casilla «Acepto que Gloma me contacte sobre esta demo» autorizas el tratamiento de los datos que se explican en esta sección. La casilla de promociones y novedades es aparte y no es obligatoria.',
    ],
  },
  {
    titulo: 'Qué datos usamos en la demo',
    parrafos: [
      'Tu nombre, el nombre y el tipo de tu empresa, tu teléfono y tu correo electrónico. También guardamos la conversación que tengas con el agente de demostración y registramos si haces clic en «Agendar una llamada» o en «Hablar con un asesor».',
    ],
  },
  {
    titulo: 'Para qué los usamos en la demo',
    parrafos: [
      'Con el nombre y el tipo de tu empresa creamos una demostración personalizada del agente de IA, con productos de ejemplo. Con tu teléfono y tu correo te contactamos para hablar de esa demostración.',
      'Solo te enviamos promociones y novedades de Gloma si marcaste esa casilla. Si no la marcaste, usamos tus datos únicamente para el seguimiento de tu demo.',
    ],
  },
  {
    titulo: 'Quién más trata tus datos en la demo',
    parrafos: [
      'Amazon Web Services aloja la plataforma y, a través de Amazon Bedrock, ejecuta el modelo de IA que responde en la demo. Ese tratamiento puede hacerse en servidores fuera de Colombia, así que tus datos pueden transmitirse a otros países. Amazon Web Services actúa como encargado: trata los datos por cuenta de Gloma y para prestar este servicio. Al aceptar esta autorización, autorizas también esa transmisión internacional.',
      'Cal.com gestiona el calendario para agendar una llamada con Gloma. Solo recibe datos si abres «Agendar una llamada»: en ese caso le llegan tu nombre y tu correo, si ya los habías escrito en el formulario de la demo, y lo que escribas en su formulario de reserva.',
    ],
  },
  {
    titulo: 'Cuánto tiempo guardamos los datos de la demo',
    parrafos: [
      'Guardamos tus datos y la conversación de la demo para hacerle seguimiento comercial, hasta que nos pidas eliminarlos.',
    ],
  },
  {
    titulo: 'Tus derechos sobre la demo',
    parrafos: [
      'Sobre los datos de la demo tienes los mismos derechos descritos en «Tus derechos». Además, puedes pedirnos que eliminemos tus datos y la conversación. Para cualquiera de estas solicitudes, escribe a contacto@glomacx.com.',
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
            Autorización de tratamiento de datos personales
          </h1>
          <p className="text-sm mb-10" style={{ color: BRAND.textMuted }}>
            Ley Estatutaria 1581 de 2012 · Decreto 1377 de 2013 · Vigente desde el {VIGENCIA} · Actualizada el {ACTUALIZACION}
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
