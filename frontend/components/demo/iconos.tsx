/**
 * Íconos de línea de la demo (los mismos trazos del wireframe #611 y de
 * `pages/gloma.tsx`). Todos decorativos: `aria-hidden`, el texto va al lado.
 */
import type { ReactNode } from 'react';

function Svg({
  size = 20,
  stroke = 'currentColor',
  width = 2,
  className,
  children,
}: {
  size?: number;
  stroke?: string;
  width?: number;
  className?: string;
  children: ReactNode;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

export const IconoError = ({ size = 16, className = 'shrink-0 mt-px' }: { size?: number; className?: string }) => (
  <Svg size={size} className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v6M12 16.5v.5" />
  </Svg>
);

export const IconoAlerta = ({ size = 20 }: { size?: number }) => (
  <Svg size={size} stroke="#FF9A8F" className="shrink-0">
    <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
  </Svg>
);

export const IconoOk = ({ size = 18 }: { size?: number }) => (
  <Svg size={size} width={2.4}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Svg>
);

export const IconoChat = ({ size = 30 }: { size?: number }) => (
  <Svg size={size} stroke="#4DB6AC" width={1.6}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.6A8 8 0 1 1 21 12zM8 11h8M8 14h5" />
  </Svg>
);

export const IconoChatCerrado = ({ size = 40 }: { size?: number }) => (
  <Svg size={size} stroke="#4DB6AC" width={1.6}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.6A8 8 0 1 1 21 12z" />
    <path d="M9 9l6 6M15 9l-6 6" />
  </Svg>
);

export const IconoInfo = ({ size = 16 }: { size?: number }) => (
  <Svg size={size} stroke="#4DB6AC" className="shrink-0">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </Svg>
);

export const IconoCalendario = ({ size = 14 }: { size?: number }) => (
  <Svg size={size}>
    <rect x="3" y="5" width="18" height="16" rx="3" />
    <path d="M8 3v4M16 3v4M3 10h18" />
  </Svg>
);

export const IconoFlecha = ({ dir, size = 18 }: { dir: 'izq' | 'der' | 'abajo'; size?: number }) => (
  <Svg size={size} width={2.2}>
    <path d={dir === 'izq' ? 'M15 18l-6-6 6-6' : dir === 'der' ? 'M9 18l6-6-6-6' : 'M6 9l6 6 6-6'} />
  </Svg>
);

export const IconoIr = ({ size = 18 }: { size?: number }) => (
  <Svg size={size} width={2.2}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Svg>
);

export const IconoAsesor = ({ size = 22 }: { size?: number }) => (
  <Svg size={size} stroke="#4DB6AC" width={1.8} className="mx-auto mb-1.5">
    <circle cx="9" cy="8" r="3.5" />
    <path d="M3 20v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1M17 8l2 2 3-3" />
  </Svg>
);

/** Íconos de los 4 beneficios de la slide 2, en el orden de `DEMO_COPY`. */
export const ICONOS_BENEFICIOS: ReactNode[] = [
  // Responde aunque no estés
  <Svg key="b1" size={26} stroke="#4DB6AC" width={1.6} className="shrink-0">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3.5 2" />
  </Svg>,
  // Cotiza con tus tarifas
  <Svg key="b2" size={26} stroke="#4DB6AC" width={1.6} className="shrink-0">
    <path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z" />
    <circle cx="7.5" cy="7.5" r="1.5" />
  </Svg>,
  // Tu asesor entra a cerrar
  <Svg key="b3" size={26} stroke="#4DB6AC" width={1.6} className="shrink-0">
    <circle cx="9" cy="8" r="3.5" />
    <path d="M3 20v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1M16 4.5a3.5 3.5 0 0 1 0 7M21 20v-1a5 5 0 0 0-3-4.6" />
  </Svg>,
  // Retoma a los interesados que se fueron
  <Svg key="b4" size={26} stroke="#4DB6AC" width={1.6} className="shrink-0">
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5" />
  </Svg>,
];

/** Ícono de envío de WhatsApp (relleno). */
export const IconoEnviar = () => (
  <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M3.4 20.4 21 12 3.4 3.6l-.01 6.53L16 12 3.39 13.87z" />
  </svg>
);

/** Checks del mensaje saliente. */
export const Check = ({ doble, leido }: { doble: boolean; leido?: boolean }) =>
  doble ? (
    <svg width="18" height="11" viewBox="0 0 18 11" fill="none" stroke={leido ? '#8FD6CE' : 'currentColor'} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 5.8l3 3L10.5 2M7 8.3l.5.5L14 2" />
    </svg>
  ) : (
    <svg width="16" height="11" viewBox="0 0 16 11" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1.5 5.8l3 3L11 2" />
    </svg>
  );
