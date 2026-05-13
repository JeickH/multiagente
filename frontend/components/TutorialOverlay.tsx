/**
 * Tutorial interactivo con spotlight (Sprint 15).
 *
 * Uso:
 *   <TutorialOverlay
 *     moduleKey="mi_plan"
 *     steps={[
 *       { selector: '[data-tour="plan-card"]', title: 'Tu plan', body: '...' },
 *       ...
 *     ]}
 *   />
 *
 * Comportamiento:
 *  1. Al montar, hace GET /usuario/me/tutorials. Si la llave aún no está
 *     done ni skipped, muestra el overlay.
 *  2. El overlay oscurece toda la pantalla salvo un "cutout" rectangular
 *     sobre el bounding-rect del selector del paso actual.
 *  3. Cada paso ofrece "Atrás / Siguiente / Finalizar" + "Omitir tutorial"
 *     siempre visible. La caja flotante se ubica debajo del cutout (o
 *     encima si no cabe).
 *  4. Al finalizar o al omitir, hace PATCH /usuario/me/tutorials/{module}
 *     y desaparece. No vuelve a mostrarse salvo que el backend resetee
 *     el flag.
 *  5. Si un selector no resuelve a un elemento, el paso se muestra
 *     centrado sin spotlight (fallback no bloqueante).
 *  6. Cerrar con Esc equivale a Omitir.
 *
 * Sin libs externas: 100% Tailwind + React puro.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { authedFetch } from '../lib/api';

export type TutorialStep = {
  selector: string;
  title: string;
  body: string;
};

type TutorialsResponse = {
  tutorials: Record<string, { done: boolean; skipped: boolean; completed_at: string | null }>;
};

type Props = {
  moduleKey: 'mi_plan' | 'mensajes' | 'bots' | 'campanas';
  steps: TutorialStep[];
  /** Si true, fuerza arrancar el tutorial ignorando el estado del backend.
   *  Útil para un futuro botón "Ver tutorial otra vez" (no implementado en UI). */
  force?: boolean;
};

type Rect = { top: number; left: number; width: number; height: number };

const PAD = 8; // padding alrededor del elemento resaltado

function getRect(selector: string): Rect | null {
  if (typeof window === 'undefined') return null;
  const el = document.querySelector(selector) as HTMLElement | null;
  if (!el) return null;
  const r = el.getBoundingClientRect();
  // Si el elemento existe pero está fuera del viewport (display:none), retornar null
  if (r.width === 0 && r.height === 0) return null;
  return {
    top: Math.max(0, r.top - PAD),
    left: Math.max(0, r.left - PAD),
    width: r.width + PAD * 2,
    height: r.height + PAD * 2,
  };
}

export default function TutorialOverlay({ moduleKey, steps, force = false }: Props) {
  const [active, setActive] = useState(false);
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const [viewport, setViewport] = useState({ w: 0, h: 0 });
  const submittedRef = useRef(false);

  // 1) decidir si arrancamos
  useEffect(() => {
    let cancelled = false;
    async function decide() {
      if (force) {
        if (!cancelled) setActive(true);
        return;
      }
      try {
        const data = await authedFetch<TutorialsResponse>('/usuario/me/tutorials');
        const entry = data?.tutorials?.[moduleKey];
        if (!entry || (!entry.done && !entry.skipped)) {
          if (!cancelled) setActive(true);
        }
      } catch {
        // si falla la consulta, mejor no molestar al usuario con un overlay
      }
    }
    decide();
    return () => {
      cancelled = true;
    };
  }, [moduleKey, force]);

  // 2) re-medir el rect al cambiar de paso, al hacer resize/scroll
  useEffect(() => {
    if (!active) return;
    function measure() {
      setRect(getRect(steps[idx]?.selector || ''));
      setViewport({ w: window.innerWidth, h: window.innerHeight });
    }
    measure();
    // pequeño retry — algunos selectores aparecen tras un microtick
    const t = window.setTimeout(measure, 80);
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [active, idx, steps]);

  // 3) Esc → omitir
  useEffect(() => {
    if (!active) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') handleClose(true);
      if (e.key === 'ArrowRight') handleNext();
      if (e.key === 'ArrowLeft') handlePrev();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, idx]);

  async function persist(done: boolean, skipped: boolean) {
    if (submittedRef.current) return;
    submittedRef.current = true;
    try {
      await authedFetch(`/usuario/me/tutorials/${moduleKey}`, {
        method: 'PATCH',
        body: JSON.stringify({ done, skipped }),
      });
    } catch {
      // si falla el persist, no romper la UX: igual cerramos
    }
  }

  function handleClose(skipped: boolean) {
    setActive(false);
    persist(!skipped, skipped);
  }

  function handleNext() {
    if (idx >= steps.length - 1) {
      handleClose(false);
    } else {
      setIdx((v) => v + 1);
    }
  }

  function handlePrev() {
    setIdx((v) => Math.max(0, v - 1));
  }

  const tipPos = useMemo(() => {
    // Decide arriba/abajo según espacio disponible
    if (!rect || viewport.h === 0) {
      return { top: viewport.h ? viewport.h / 2 - 120 : 200, left: viewport.w ? viewport.w / 2 - 200 : 200, anchored: false };
    }
    const tipW = 400;
    const tipH = 220;
    const below = rect.top + rect.height + 16;
    const above = rect.top - tipH - 16;
    const left = Math.min(
      Math.max(8, rect.left + rect.width / 2 - tipW / 2),
      viewport.w - tipW - 8,
    );
    const top = below + tipH + 8 <= viewport.h ? below : Math.max(8, above);
    return { top, left, anchored: true };
  }, [rect, viewport]);

  if (!active || steps.length === 0) return null;
  const step = steps[idx];

  // Cutout rectangular: 4 paneles oscuros alrededor del rect.
  // Si rect === null → un único panel cubre toda la pantalla (sin cutout).
  return (
    <div
      className="fixed inset-0 z-[9999] font-body"
      role="dialog"
      aria-modal="true"
      aria-label={`Tutorial: ${step.title}`}
    >
      {rect ? (
        <>
          {/* top */}
          <div
            className="absolute bg-black/65 transition-all duration-150"
            style={{ top: 0, left: 0, width: viewport.w, height: rect.top }}
          />
          {/* bottom */}
          <div
            className="absolute bg-black/65 transition-all duration-150"
            style={{
              top: rect.top + rect.height,
              left: 0,
              width: viewport.w,
              height: Math.max(0, viewport.h - (rect.top + rect.height)),
            }}
          />
          {/* left */}
          <div
            className="absolute bg-black/65 transition-all duration-150"
            style={{ top: rect.top, left: 0, width: rect.left, height: rect.height }}
          />
          {/* right */}
          <div
            className="absolute bg-black/65 transition-all duration-150"
            style={{
              top: rect.top,
              left: rect.left + rect.width,
              width: Math.max(0, viewport.w - (rect.left + rect.width)),
              height: rect.height,
            }}
          />
          {/* halo rosa alrededor del cutout */}
          <div
            className="absolute pointer-events-none rounded-xl ring-4 ring-gloma-rose shadow-2xl transition-all duration-150"
            style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
          />
        </>
      ) : (
        <div className="absolute inset-0 bg-black/65" />
      )}

      {/* Caja flotante con el copy del paso */}
      <div
        className="absolute w-[400px] max-w-[92vw] bg-gloma-cream border border-gloma-brown-light/30 rounded-xl shadow-2xl p-5"
        style={{ top: tipPos.top, left: tipPos.left }}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <div>
            <p className="text-xs uppercase tracking-wider text-gloma-brown/70 font-heading">
              Tutorial · paso {idx + 1} de {steps.length}
            </p>
            <h3 className="text-lg font-heading text-gloma-brown-darker mt-1">{step.title}</h3>
          </div>
          <button
            type="button"
            onClick={() => handleClose(true)}
            className="text-gloma-brown/60 hover:text-gloma-brown-darker text-2xl leading-none px-1"
            aria-label="Cerrar tutorial"
          >
            ×
          </button>
        </div>
        <p className="text-sm text-gloma-brown-dark whitespace-pre-line">{step.body}</p>

        <div className="flex items-center justify-between gap-3 mt-5">
          <button
            type="button"
            onClick={() => handleClose(true)}
            className="text-xs underline text-gloma-brown/70 hover:text-gloma-brown-darker"
          >
            Omitir tutorial
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePrev}
              disabled={idx === 0}
              className="px-3 py-1.5 rounded-md text-sm border border-gloma-brown-light/40 text-gloma-brown-dark disabled:opacity-40"
            >
              Atrás
            </button>
            <button
              type="button"
              onClick={handleNext}
              className="px-4 py-1.5 rounded-md text-sm bg-gloma-brown text-gloma-cream hover:bg-gloma-brown-dark"
            >
              {idx >= steps.length - 1 ? 'Finalizar' : 'Siguiente'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
