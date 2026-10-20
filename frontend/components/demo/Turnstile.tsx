/**
 * Cloudflare Turnstile para el formulario de la demo (#608, M7).
 *
 * Solo existe si hay `NEXT_PUBLIC_TURNSTILE_SITEKEY`: sin ella este
 * componente no pinta nada y el script de Cloudflare no se carga. El token
 * que entrega va en `POST /demo/iniciar` como `turnstile_token`; lo verifica
 * el backend. Es de un solo uso: cada intento de envío llama a `reset` vía
 * `reinicio` para pedir uno nuevo.
 */
import { useEffect, useRef } from 'react';

const SITEKEY = process.env.NEXT_PUBLIC_TURNSTILE_SITEKEY || '';
const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

export const TURNSTILE_ACTIVO = SITEKEY.length > 0;

type TurnstileApi = {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id: string) => void;
  remove: (id: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let cargaScript: Promise<void> | null = null;

function cargarScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (cargaScript) return cargaScript;
  cargaScript = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = SCRIPT_URL;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => {
      cargaScript = null;
      reject(new Error('turnstile'));
    };
    document.head.appendChild(s);
  });
  return cargaScript;
}

export default function Turnstile({
  onToken,
  reinicio,
}: {
  onToken: (token: string | null) => void;
  /** Cambiar este número pide un token nuevo (los tokens son de un solo uso). */
  reinicio: number;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const onTokenRef = useRef(onToken);
  onTokenRef.current = onToken;

  useEffect(() => {
    if (!TURNSTILE_ACTIVO) return;
    let vivo = true;
    cargarScript()
      .then(() => {
        if (!vivo || !contenedor.current || !window.turnstile || widgetId.current) return;
        widgetId.current = window.turnstile.render(contenedor.current, {
          sitekey: SITEKEY,
          theme: 'dark',
          size: 'flexible',
          language: 'es',
          action: 'demo_iniciar',
          callback: (t: string) => onTokenRef.current(t),
          'expired-callback': () => onTokenRef.current(null),
          'error-callback': () => onTokenRef.current(null),
        });
      })
      .catch(() => onTokenRef.current(null));
    return () => {
      vivo = false;
      if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current);
      widgetId.current = null;
    };
  }, []);

  useEffect(() => {
    if (!TURNSTILE_ACTIVO || reinicio === 0) return;
    if (widgetId.current && window.turnstile) {
      onTokenRef.current(null);
      window.turnstile.reset(widgetId.current);
    }
  }, [reinicio]);

  if (!TURNSTILE_ACTIVO) return null;
  return <div ref={contenedor} className="mt-4 min-h-[65px]" />;
}
