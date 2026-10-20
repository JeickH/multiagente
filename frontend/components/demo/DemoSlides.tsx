/**
 * Etapa 2: las 3 slides que tapan la generación del bot (dialog modal).
 *
 * Decisiones del wireframe #611 que se respetan aquí:
 *  - `EstadoAgente` arriba de las 3 slides es la única fuente de verdad del
 *    bot; la barra es indeterminada (nunca un porcentaje) y los subtítulos
 *    rotativos son cosméticos.
 *  - Sin avance automático; navegación con flechas, puntos, teclado (← →) y
 *    deslizando (40 px, solo si el gesto es más horizontal que vertical).
 *  - El botón de la slide 3 usa `aria-disabled` (sigue enfocable) mientras
 *    genera y solo se activa con `estado=lista`, nunca por tiempo.
 *  - Si está lista antes de llegar, «Probar ahora →» salta las slides.
 *  - Al quedar lista NO se mueve el foco ni se cambia de slide: se anuncia por
 *    `role=status` y el botón hace un pulso de 2 ciclos.
 *  - Sin botón de cerrar y Escape no cierra; foco atrapado en el dialog.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { DEMO_COPY, DEMO_UI, rellenarCopy } from '../../lib/demo_copy';
import type { EstadoGeneracion, ProductoDemo } from '../../lib/demoApi';
import { ATRIBUTO_MODAL_AGENDAR } from '../AgendarLlamadaModal';
import CtaAgendar, { type AccionesAgendar } from './CtaAgendar';
import { ICONOS_BENEFICIOS, IconoAlerta, IconoChat, IconoFlecha, IconoIr, IconoOk } from './iconos';

const S = DEMO_COPY.slides;
const U = DEMO_UI;

function Esqueleto() {
  return (
    <div className="mt-2 flex flex-wrap gap-2" aria-hidden="true">
      <span className="demo-esqueleto h-8 w-44 rounded-full" />
      <span className="demo-esqueleto h-8 w-36 rounded-full" />
      <span className="demo-esqueleto h-8 w-40 rounded-full" />
    </div>
  );
}

const FOCUSABLES =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function DemoSlides({
  nombre,
  empresa,
  estado,
  lento,
  reconectando,
  productos,
  animarListo,
  onProbar,
  onReintentar,
  reintentando,
  acciones,
}: {
  nombre: string;
  empresa: string;
  estado: EstadoGeneracion;
  lento: boolean;
  reconectando: boolean;
  productos: ProductoDemo[];
  /** true solo si pasó de generando a lista con las slides abiertas. */
  animarListo: boolean;
  onProbar: () => void;
  /** Error: repetir la demo con los mismos datos (o volver al formulario). */
  onReintentar: () => void;
  reintentando: boolean;
  acciones: AccionesAgendar;
}) {
  const [slide, setSlide] = useState(0);
  const [sub, setSub] = useState(0);
  const dialogo = useRef<HTMLDivElement>(null);
  const titulos = useRef<(HTMLHeadingElement | null)[]>([]);
  const gesto = useRef<{ x: number; y: number } | null>(null);
  const datos = { nombre, empresa };

  const ir = useCallback((n: number) => setSlide(Math.max(0, Math.min(2, n))), []);

  // Al abrir: foco al título de la slide 1 y sin scroll detrás.
  useEffect(() => {
    titulos.current[0]?.focus({ preventScroll: true });
    const previo = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previo;
    };
  }, []);

  // Subtítulos cosméticos mientras genera.
  useEffect(() => {
    if (estado !== 'generando') return;
    const id = window.setInterval(() => setSub((s) => (s + 1) % U.estado.subtitulos.length), 4000);
    return () => window.clearInterval(id);
  }, [estado]);

  // Si el foco quedó en una slide que ahora es `inert` (o se cayó al body),
  // el navegador lo suelta y el teclado deja de llegar al dialog: se lleva al
  // título de la slide visible. Si está en los controles, no se toca.
  useEffect(() => {
    const activo = document.activeElement as HTMLElement | null;
    const fuera = !activo || activo === document.body || !dialogo.current?.contains(activo);
    if (fuera || activo?.closest('[inert]')) titulos.current[slide]?.focus({ preventScroll: true });
  }, [slide]);

  // ← → también con el foco fuera del dialog (p. ej. tras un clic en el fondo).
  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      if (dialogo.current?.contains(e.target as Node)) return; // lo maneja onKeyDown
      // Con el modal de Cal encima, las flechas no mueven las slides de atrás.
      if (document.querySelector(`[${ATRIBUTO_MODAL_AGENDAR}]`)) return;
      if (e.key === 'ArrowRight') setSlide((n) => Math.min(2, n + 1));
      if (e.key === 'ArrowLeft') setSlide((n) => Math.max(0, n - 1));
    };
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault(); // no cierra: dejaría la demo a medias
      return;
    }
    if (e.key === 'Tab' && dialogo.current) {
      const els = Array.from(dialogo.current.querySelectorAll<HTMLElement>(FOCUSABLES)).filter(
        (el) => !el.closest('[inert]') && el.offsetParent !== null,
      );
      if (els.length === 0) return;
      const primero = els[0];
      const ultimo = els[els.length - 1];
      if (e.shiftKey && document.activeElement === primero) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && document.activeElement === ultimo) {
        e.preventDefault();
        primero.focus();
      }
      return;
    }
    const tag = (e.target as HTMLElement).tagName;
    if (/INPUT|TEXTAREA|SELECT/.test(tag)) return;
    if (e.key === 'ArrowRight') ir(slide + 1);
    if (e.key === 'ArrowLeft') ir(slide - 1);
  };

  const alPresionar = (e: React.PointerEvent) => {
    gesto.current = { x: e.clientX, y: e.clientY };
  };
  const alSoltar = (e: React.PointerEvent) => {
    const g = gesto.current;
    gesto.current = null;
    if (!g) return;
    const dx = e.clientX - g.x;
    const dy = e.clientY - g.y;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) ir(slide + (dx < 0 ? 1 : -1));
  };

  const generando = estado === 'generando';
  const lista = estado === 'lista';
  const error = estado === 'error';

  // ---- EstadoAgente ----
  let titulo: React.ReactNode;
  let subtitulo: string;
  if (lista) {
    titulo = U.estado.listo;
    subtitulo = rellenarCopy(U.estado.listoSub, datos);
  } else if (error) {
    titulo = DEMO_COPY.error.titulo;
    subtitulo = DEMO_COPY.error.texto;
  } else {
    titulo = rellenarCopy(U.estado.generando, datos);
    subtitulo = reconectando ? U.estado.reconectando : lento ? U.estado.lento : U.estado.subtitulos[sub];
  }

  const anuncio = lista && animarListo ? U.estado.anuncioListo : error ? U.estado.anuncioError : '';

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60 md:backdrop-blur-[2px]" aria-hidden="true" />
      <div
        ref={dialogo}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dlg-titulo"
        aria-describedby="anuncio-agente"
        onKeyDown={onKeyDown}
        className="fixed z-50 inset-0 md:inset-auto md:left-1/2 md:top-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-[600px] md:h-[min(600px,calc(100dvh-2rem))] flex flex-col bg-gloma-ink md:rounded-3xl md:border md:border-gloma-mint/25 md:shadow-2xl overflow-hidden text-gloma-ink-text"
      >
        <h2 id="dlg-titulo" className="sr-only">
          {U.estado.dialogo}
        </h2>

        {/* EstadoAgente */}
        <div
          className="shrink-0 px-4 md:px-6 pb-3 border-b border-white/10"
          style={{ paddingTop: 'max(16px, env(safe-area-inset-top))' }}
        >
          <div className="flex items-center gap-3 min-h-[44px]">
            <span
              className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${
                lista ? 'bg-gloma-mint text-gloma-ink' : error ? 'bg-gloma-ink-err/15' : 'bg-gloma-mint/15 text-gloma-mint'
              }`}
            >
              {lista ? <IconoOk /> : error ? <IconoAlerta size={18} /> : <span className="demo-spin" aria-hidden="true" />}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-white leading-snug break-words">{titulo}</p>
              <p className="text-xs text-gloma-ink-muted leading-snug mt-0.5">{subtitulo}</p>
            </div>
            {lista && slide !== 2 && (
              <button
                type="button"
                onClick={onProbar}
                className="shrink-0 text-sm font-semibold text-gloma-mint hover:text-gloma-rose px-2 min-h-[44px]"
              >
                {U.estado.probarAhora}
              </button>
            )}
            <span className="shrink-0 text-xs tabular-nums text-gloma-ink-muted" aria-hidden="true">
              {slide + 1} / 3
            </span>
          </div>
          {generando && <div className="demo-barra mt-3" aria-hidden="true" />}
        </div>
        <p id="anuncio-agente" role="status" aria-live="polite" className="sr-only">
          {anuncio}
        </p>

        {/* Carrusel */}
        <div
          className="relative flex-1 overflow-hidden touch-pan-y"
          aria-roledescription="carrusel"
          aria-label={U.slides.carrusel}
          onPointerDown={alPresionar}
          onPointerUp={alSoltar}
          onPointerCancel={() => (gesto.current = null)}
          // El carrusel se mueve con `transform`; si el navegador lo desplaza
          // por su cuenta (foco o búsqueda en una slide oculta) se desincroniza.
          onScroll={(e) => {
            e.currentTarget.scrollLeft = 0;
          }}
        >
          <div className="demo-pista flex h-full" style={{ transform: `translateX(${-slide * 100}%)` }}>
            {/* Slide 1 · bienvenida */}
            <div
              className="w-full h-full shrink-0 overflow-y-auto px-5 md:px-10 py-8 md:py-10 flex flex-col"
              role="group"
              aria-roledescription="slide"
              aria-label="1 de 3"
              inert={slide !== 0}
            >
              <div className="w-16 h-16 rounded-[22px] border-2 border-gloma-mint flex items-center justify-center" aria-hidden="true">
                <IconoChat />
              </div>
              <h3
                ref={(el) => {
                  titulos.current[0] = el;
                }}
                tabIndex={-1}
                className="font-heading font-extrabold text-[28px] md:text-4xl leading-[1.1] mt-6 text-white focus:outline-none break-words"
              >
                {rellenarCopy(S.bienvenida.titulo, datos)}
              </h3>
              <p className="mt-4 text-[15px] md:text-lg font-light text-white/85 leading-relaxed break-words">
                {rellenarCopy(lista ? U.slides.bienvenidaLista : S.bienvenida.texto, datos)}
              </p>
              <p className="mt-auto pt-6 text-xs text-gloma-ink-muted">
                <span className="md:hidden">{U.slides.pistaMovil}</span>
                <span className="hidden md:inline">{U.slides.pistaEscritorio}</span>
              </p>
            </div>

            {/* Slide 2 · beneficios */}
            <div
              className="w-full h-full shrink-0 overflow-y-auto px-5 md:px-10 py-8 md:py-10"
              role="group"
              aria-roledescription="slide"
              aria-label="2 de 3"
              inert={slide !== 1}
            >
              <h3
                ref={(el) => {
                  titulos.current[1] = el;
                }}
                tabIndex={-1}
                className="font-heading font-extrabold text-2xl md:text-3xl leading-tight text-white focus:outline-none"
              >
                {S.beneficios.titulo}
              </h3>
              <ul className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
                {S.beneficios.items.map((b, i) => (
                  <li key={b.titulo} className="rounded-2xl bg-white/[0.04] border border-gloma-mint/15 p-4 flex sm:block gap-3">
                    {ICONOS_BENEFICIOS[i]}
                    <div className="sm:mt-3">
                      <p className="font-semibold text-white text-sm">{b.titulo}</p>
                      <p className="text-[13px] text-gloma-ink-muted mt-1 leading-snug">{b.texto}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {/* Slide 3 · probar */}
            <div
              className="w-full h-full shrink-0 overflow-y-auto px-5 md:px-10 py-8 md:py-10 flex flex-col"
              role="group"
              aria-roledescription="slide"
              aria-label="3 de 3"
              inert={slide !== 2}
            >
              <h3
                ref={(el) => {
                  titulos.current[2] = el;
                }}
                tabIndex={-1}
                className="font-heading font-extrabold text-[26px] md:text-4xl leading-[1.1] text-white focus:outline-none"
              >
                {S.invitacion.titulo}
              </h3>
              <p className="mt-4 text-[15px] md:text-base font-light text-white/85 leading-relaxed break-words">
                {rellenarCopy(S.invitacion.texto, datos)}
              </p>

              <div className="mt-6">
                {generando && (
                  <>
                    <p className="text-xs text-gloma-ink-muted">{U.slides.productosCargando}</p>
                    <Esqueleto />
                  </>
                )}
                {lista && productos.length > 0 && (
                  <>
                    <p className="text-xs text-gloma-ink-muted">{U.slides.productosListos}</p>
                    <ul className="mt-2 flex flex-wrap gap-2">
                      {productos.map((p) => (
                        <li
                          key={p.nombre}
                          className="demo-entra text-[13px] font-medium px-3 py-1.5 rounded-full bg-gloma-mint/15 text-gloma-rose border border-gloma-mint/30"
                        >
                          {p.nombre}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>

              <div className="mt-auto pt-6">
                {error ? (
                  <button
                    type="button"
                    onClick={onReintentar}
                    disabled={reintentando}
                    aria-busy={reintentando}
                    className="demo-btn-primario w-full"
                  >
                    {reintentando && <span className="demo-spin" aria-hidden="true" />}
                    <span>{DEMO_COPY.error.boton}</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      if (lista) onProbar();
                    }}
                    aria-disabled={lista ? undefined : true}
                    aria-describedby="btn-probar-ayuda"
                    className={`demo-btn-primario w-full ${lista ? (animarListo ? 'demo-pulso-1' : '') : 'demo-btn-espera'}`}
                  >
                    {lista ? (
                      <>
                        <span>{S.invitacion.botonListo}</span>
                        <IconoIr />
                      </>
                    ) : (
                      <>
                        <span className="demo-spin" aria-hidden="true" />
                        <span>{S.invitacion.botonCargando}</span>
                      </>
                    )}
                  </button>
                )}
                <p id="btn-probar-ayuda" className="text-xs text-center text-gloma-ink-muted mt-3 min-h-[1rem]">
                  {generando && U.slides.botonCargandoAyuda}
                </p>
                {error && <CtaAgendar acciones={acciones} variante="enlaces" className="mt-1" />}
              </div>
            </div>
          </div>
        </div>

        {/* NavSlides */}
        <div
          className="shrink-0 flex items-center justify-between gap-3 px-4 md:px-6 pt-3 border-t border-white/10"
          style={{ paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
        >
          <button
            type="button"
            onClick={() => ir(slide - 1)}
            disabled={slide === 0}
            className="w-11 h-11 rounded-full border border-white/30 flex items-center justify-center disabled:opacity-30 hover:bg-white/5"
            aria-label={U.slides.anterior}
          >
            <IconoFlecha dir="izq" />
          </button>
          <div className="flex items-center gap-1" role="group" aria-label="Elegir slide">
            {[0, 1, 2].map((n) => (
              <button
                key={n}
                type="button"
                className="p-2 min-w-[28px] min-h-[44px] flex items-center justify-center"
                onClick={() => ir(n)}
                aria-label={U.slides.irA.replace('{n}', String(n + 1))}
                aria-current={n === slide ? 'step' : undefined}
              >
                <span className={`demo-punto block ${n === slide ? 'demo-punto-activo' : ''}`} />
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => ir(slide + 1)}
            className={`h-11 px-5 rounded-full bg-white/10 hover:bg-white/15 text-sm font-semibold flex items-center gap-2 ${
              slide === 2 ? 'invisible' : ''
            }`}
            aria-label="Slide siguiente"
            tabIndex={slide === 2 ? -1 : undefined}
          >
            <span>{U.slides.siguiente}</span>
            <IconoFlecha dir="der" size={16} />
          </button>
        </div>
      </div>
    </>
  );
}
