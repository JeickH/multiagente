/**
 * Pantalla de premio (#643): aparece una sola vez, justo después de «Iniciar
 * demo» y antes de las slides. El bot se sigue armando en segundo plano (el
 * sondeo de `DemoPage` no se detiene). Al recargar no vuelve: esta etapa no se
 * guarda en `gloma_demo`, que ya dice «slides».
 *
 * - Monto: COP si el teléfono es +57; USD si es de otro país.
 * - Correo y teléfono son texto que escribió la persona: se pintan como texto.
 * - Accesible: `role="dialog"` + `aria-modal`, foco al título al abrir, Tab no
 *   sale del diálogo (solo hay un botón). El confeti es decorativo
 *   (`aria-hidden`) y con `prefers-reduced-motion` no se mueve.
 */
import { useEffect, useMemo, useRef } from 'react';

import { DEMO_UI, rellenarCopy } from '../../lib/demo_copy';

const T = DEMO_UI.premio;
const COLORES = ['#4DB6AC', '#8FD6CE', '#E0F2F1', '#F5C24B', '#FFFFFF'];

/** Piezas de confeti con posiciones fijas (sin `Math.random` en el render). */
function piezas(n: number) {
  return Array.from({ length: n }, (_, i) => {
    const x = (i * 37) % 100;
    return {
      left: `${x}%`,
      delay: `${((i * 13) % 17) / 10}s`,
      duracion: `${3.2 + ((i * 7) % 10) / 5}s`,
      color: COLORES[i % COLORES.length],
      ancho: 6 + (i % 3) * 3,
      alto: i % 4 === 0 ? 6 : 12,
      giro: `${(i * 47) % 360}deg`,
      redondo: i % 5 === 0,
    };
  });
}

export default function DemoPremio({
  nombre,
  correo,
  telefono,
  colombia,
  onContinuar,
}: {
  nombre: string;
  correo: string;
  /** Ya formateado: «+57 300 123 4567». */
  telefono: string;
  colombia: boolean;
  onContinuar: () => void;
}) {
  const titulo = useRef<HTMLHeadingElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const confeti = useMemo(() => piezas(36), []);

  useEffect(() => {
    titulo.current?.focus({ preventScroll: true });
    const previo = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previo;
    };
  }, []);

  const atrapar = (e: React.KeyboardEvent) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      boton.current?.focus();
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="premio-titulo"
      aria-describedby="premio-monto premio-detalle"
      onKeyDown={atrapar}
      className="fixed inset-0 z-50 overflow-y-auto overflow-x-hidden text-gloma-ink-text"
      style={{ background: 'radial-gradient(ellipse at 50% 18%, #00594B 0%, #003A30 38%, #101817 78%)' }}
    >
      <style jsx>{`
        .confeti {
          position: absolute;
          top: -24px;
          opacity: 0;
          animation-name: caer;
          animation-timing-function: cubic-bezier(0.35, 0.1, 0.6, 1);
          animation-fill-mode: forwards;
          animation-iteration-count: 2;
        }
        @keyframes caer {
          0% {
            opacity: 0;
            transform: translate3d(0, 0, 0) rotate(0deg);
          }
          8% {
            opacity: 1;
          }
          100% {
            opacity: 0.9;
            transform: translate3d(24px, 105vh, 0) rotate(540deg);
          }
        }
        .destello {
          animation: destello 2.4s ease-in-out infinite;
        }
        @keyframes destello {
          0%,
          100% {
            box-shadow: 0 0 0 0 rgba(245, 194, 75, 0), 0 0 40px 8px rgba(77, 182, 172, 0.35);
          }
          50% {
            box-shadow: 0 0 0 10px rgba(245, 194, 75, 0.12), 0 0 64px 16px rgba(77, 182, 172, 0.5);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .confeti {
            animation: none;
            opacity: 0.85;
            top: var(--y);
          }
          .destello {
            animation: none;
          }
        }
      `}</style>

      {/* Confeti (decorativo). Con movimiento reducido queda quieto. */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        {confeti.map((c, i) => (
          <span
            key={i}
            className="confeti"
            style={{
              left: c.left,
              width: c.ancho,
              height: c.alto,
              background: c.color,
              borderRadius: c.redondo ? 9999 : 2,
              animationDelay: c.delay,
              animationDuration: c.duracion,
              transform: `rotate(${c.giro})`,
              // Para movimiento reducido: piezas quietas en la franja superior.
              ['--y' as string]: `${(i * 23) % 10}%`,
            }}
          />
        ))}
      </div>

      <div className="relative min-h-full flex flex-col items-center justify-center px-5 py-10 md:py-10">
        <div className="w-full max-w-md md:max-w-2xl text-center">
          {/* Trofeo / regalo con destello */}
          <div className="destello mx-auto w-20 h-20 rounded-[28px] bg-gloma-mint/15 border-2 border-gloma-mint flex items-center justify-center" aria-hidden="true">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#4DB6AC" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="8" width="18" height="4" rx="1" />
              <path d="M12 8v13M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7" />
              <path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8s1-5 4.5-5a2.5 2.5 0 0 1 0 5" stroke="#F5C24B" />
            </svg>
          </div>

          <p className="mt-5 text-sm md:text-base font-semibold text-gloma-rose break-words">
            {rellenarCopy(T.eyebrow, { nombre })}
          </p>
          <h2
            id="premio-titulo"
            ref={titulo}
            tabIndex={-1}
            className="mt-2 font-heading font-extrabold text-[30px] leading-[1.08] md:text-5xl text-white focus:outline-none"
          >
            {T.titulo}
          </h2>

          <p id="premio-monto" className="mt-5">
            {T.prefijoMonto && (
              <span className="block text-base md:text-lg font-semibold text-white/90">{T.prefijoMonto}</span>
            )}
            <span className="block font-heading font-extrabold leading-tight text-gloma-mint break-words text-[clamp(28px,9vw,60px)]">
              {colombia ? T.montoColombia : T.montoExterior}
            </span>
            <span className="block mt-1 text-base md:text-lg text-white/90">{T.sufijoMonto}</span>
          </p>

          <div id="premio-detalle" className="mt-4 mx-auto max-w-md space-y-2">
            <p className="text-[15px] md:text-base font-semibold text-white">{T.detalle}</p>
            <p className="inline-block rounded-2xl bg-gloma-mint/15 border border-gloma-mint/40 px-4 py-2 text-sm text-gloma-ink-text">
              {T.seSuma}
            </p>
          </div>

          <div className="mt-7 mx-auto max-w-md rounded-3xl bg-white/[0.06] border border-gloma-mint/25 p-5 text-left">
            <p className="text-sm text-gloma-ink-text">{T.envio}</p>
            <dl className="mt-3 space-y-2.5 text-sm">
              <div className="flex flex-col sm:flex-row sm:items-baseline sm:gap-3">
                <dt className="text-gloma-ink-muted sm:w-24 shrink-0">{T.correo}</dt>
                <dd className="font-semibold text-white break-all">{correo}</dd>
              </div>
              <div className="flex flex-col sm:flex-row sm:items-baseline sm:gap-3">
                <dt className="text-gloma-ink-muted sm:w-24 shrink-0">{T.whatsapp}</dt>
                <dd className="font-semibold text-white tabular-nums">{telefono}</dd>
              </div>
            </dl>
          </div>

          <p className="mt-6 text-sm text-gloma-ink-muted" role="status">
            {T.mientras}
          </p>

          <button ref={boton} type="button" onClick={onContinuar} className="demo-btn-primario w-full max-w-md mt-5">
            {T.boton}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
