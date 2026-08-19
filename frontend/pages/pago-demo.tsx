import Head from 'next/head';
import { useEffect, useState } from 'react';

/**
 * Pasarela de pago **de demostración**.
 *
 * Es el destino del link que entrega la herramienta `registrar_venta` del motor
 * de bots (`llm_config.venta.link_pago`). Existe para que una demo de venta por
 * WhatsApp no termine en un enlace roto: el prospecto hace clic, ve su número de
 * pedido y entiende que el cobro es simulado.
 *
 * Reglas de esta página, a propósito:
 *  - NO pide ni un solo dato: ni tarjeta, ni cédula, ni correo. Nada que se
 *    parezca a un formulario de pago real.
 *  - Dice en tres lugares distintos que es una simulación.
 *  - El "pago aprobado" es 100% del navegador: no llama a ningún backend.
 *
 * Todo llega por query string (`?ref=JRQ-7F3K2M&total=160000&marca=Jerarquía`),
 * así que sirve para cualquier cuenta demo sin tocar código.
 */

const BRAND = {
  mint: '#8FD6CE',
  forest: '#004D40',
  cream: '#F5FAF9',
  mintSoft: '#E0F2F1',
  forestLight: '#4A7A72',
};

function formatearCOP(valor: string | null): string | null {
  if (!valor) return null;
  const n = Number(valor.replace(/[^\d]/g, ''));
  if (!Number.isFinite(n) || n <= 0) return null;
  return '$' + n.toLocaleString('es-CO');
}

export default function PagoDemo() {
  const [ref, setRef] = useState('');
  const [total, setTotal] = useState<string | null>(null);
  const [marca, setMarca] = useState('');
  const [pagado, setPagado] = useState(false);

  // Los params se leen en el cliente (la página es estática, sin SSR).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const q = new URLSearchParams(window.location.search);
    setRef((q.get('ref') || '').slice(0, 32));
    setTotal(formatearCOP(q.get('total')));
    setMarca((q.get('marca') || '').slice(0, 40));
  }, []);

  return (
    <>
      <Head>
        <title>Pago de demostración{marca ? ` — ${marca}` : ''}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="robots" content="noindex" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </Head>
      <div
        className="min-h-screen flex items-center justify-center px-5 py-12"
        style={{ backgroundColor: BRAND.cream, color: BRAND.forest }}
      >
        <div className="w-full max-w-md">
          <div
            className="rounded-2xl overflow-hidden"
            style={{ backgroundColor: '#FFFFFF', boxShadow: '0 12px 40px rgba(0,77,64,0.12)' }}
          >
            {/* Banda de advertencia: lo primero que se ve */}
            <div
              className="px-6 py-3 text-center text-xs font-semibold tracking-widest uppercase"
              style={{ backgroundColor: BRAND.forest, color: BRAND.mint }}
            >
              Simulación · no se cobra dinero
            </div>

            <div className="px-6 py-8">
              <p
                className="text-xs tracking-widest uppercase mb-2"
                style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.forestLight }}
              >
                {marca ? `Pedido de ${marca}` : 'Pedido'}
              </p>
              <h1
                className="text-3xl md:text-4xl mb-6 leading-tight"
                style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800 }}
              >
                {pagado ? 'Pago aprobado' : 'Pasarela de pago'}
              </h1>

              <div
                className="rounded-xl px-5 py-4 mb-6"
                style={{ backgroundColor: BRAND.mintSoft }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className="text-sm"
                    style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.forestLight }}
                  >
                    Número de pedido
                  </span>
                  <span className="text-sm font-semibold tracking-wide">
                    {ref || '—'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span
                    className="text-sm"
                    style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.forestLight }}
                  >
                    Total
                  </span>
                  <span className="text-lg font-bold">{total || 'Según tu pedido'}</span>
                </div>
              </div>

              {pagado ? (
                <div style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
                  <p className="text-base mb-4">
                    Listo. Este es tu <strong>comprobante simulado</strong> del pedido{' '}
                    <strong>{ref || 'sin referencia'}</strong>.
                  </p>
                  <p className="text-sm" style={{ color: BRAND.forestLight }}>
                    Toma un pantallazo y envíalo por el chat para continuar con el
                    despacho. Recuerda: <strong>no se movió ningún dinero</strong>,
                    esto es una demostración.
                  </p>
                </div>
              ) : (
                <div style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
                  <p className="text-sm mb-6" style={{ color: BRAND.forestLight }}>
                    Esta página es una <strong>demostración</strong> de cómo se ve el
                    cierre de una venta por WhatsApp. No pide datos de tarjeta, no
                    procesa cobros y no guarda información.
                  </p>
                  <button
                    type="button"
                    onClick={() => setPagado(true)}
                    className="w-full px-6 py-3 rounded-full text-sm font-semibold transition-opacity hover:opacity-90"
                    style={{ backgroundColor: BRAND.forest, color: '#FFFFFF' }}
                  >
                    Simular pago aprobado
                  </button>
                </div>
              )}
            </div>
          </div>

          <p
            className="text-center text-xs mt-6"
            style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.forestLight }}
          >
            Demostración de agente de ventas · Tecnología de <strong>Gloma</strong>
          </p>
        </div>
      </div>
    </>
  );
}
