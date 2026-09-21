/**
 * El recuadro amarillo de pagos pendientes.
 *
 * Aparece cuando la cuenta lleva 7 días o más con una factura vencida, y lo
 * ve **cualquier miembro**: asesores y administradores por igual. Si la cuenta
 * se pausa por mora, el que se queda sin bandeja es quien atiende, así que
 * enterarse le sirve.
 *
 * Lo que el aviso NO dice
 * -----------------------
 * Ni cuánto se debe, ni cuántas facturas hay, ni desde cuándo. El backend
 * responde a `/pagos/aviso` con un booleano y un hash opaco, y eso es todo lo
 * que este componente tiene para pintar: un asesor no tiene por qué conocer
 * las finanzas de su empleador. El listado con los valores vive en `/pagos` y
 * es de administrador — ahí el backend responde 403 a quien no lo sea.
 *
 * Quién decide si hay mora
 * ------------------------
 * El servidor. Acá no se calculan días ni se lee el rol del JWT (regla 7: del
 * token solo sale `exp`, y lo verifica el backend). Este componente pregunta y
 * pinta.
 *
 * La X y por qué el aviso vuelve
 * ------------------------------
 * Cerrarlo guarda la `clave` —un hash de las facturas vencidas que lo
 * provocaron— en `localStorage`. Mientras la deuda sea la misma, el aviso
 * queda oculto; cuando cambia (se paga una, se vence otra), la clave cambia y
 * el aviso vuelve a salir. Un aviso que se apaga para siempre con un clic
 * sirve una sola vez.
 */
import { useEffect, useState } from 'react';

import { authedFetch } from '../lib/api';
import { haySesion } from '../lib/session';

type Aviso = { mostrar: boolean; clave: string | null };

/** Dónde se recuerda cuál aviso cerró el usuario. No es la sesión: es UX. */
const CLAVE_DESCARTADA = 'gloma_aviso_pagos_descartado';

function descartadaGuardada(): string | null {
  try {
    return localStorage.getItem(CLAVE_DESCARTADA);
  } catch {
    return null; // localStorage bloqueado: el aviso simplemente no se recuerda
  }
}

export default function AvisoPagosPendientes() {
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [descartada, setDescartada] = useState<string | null>(null);

  useEffect(() => {
    // Sin sesión no se pregunta: `authedFetch` cerraría la sesión y mandaría al
    // login, y este componente no tiene por qué provocar eso — de la redirección
    // se encarga el guard de `_app`.
    if (!haySesion()) return;

    let cancelado = false;
    setDescartada(descartadaGuardada());

    authedFetch<Aviso>('/pagos/aviso')
      .then((r) => {
        if (!cancelado) setAviso(r);
      })
      .catch(() => {
        // En silencio y a propósito: que no se pueda consultar el estado de
        // cobro no es algo que el usuario pueda resolver, y un error rojo
        // encima de cada pantalla asusta más de lo que informa.
      });

    return () => {
      cancelado = true;
    };
  }, []);

  if (!aviso?.mostrar) return null;
  if (aviso.clave && aviso.clave === descartada) return null;

  const cerrar = () => {
    try {
      if (aviso.clave) localStorage.setItem(CLAVE_DESCARTADA, aviso.clave);
    } catch {
      /* no-op */
    }
    setDescartada(aviso.clave);
  };

  return (
    <div
      role="status"
      className="shrink-0 bg-amber-100 border-b border-amber-300 px-4 py-3 md:px-6 font-body"
    >
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="text-lg leading-tight">
          ⚠️
        </span>
        <p className="flex-1 text-sm text-amber-900 leading-snug">
          <strong className="font-semibold">Tienes pagos pendientes.</strong>{' '}
          Por favor haz el pago para evitar pausas en el servicio.
        </p>
        <button
          type="button"
          onClick={cerrar}
          aria-label="Cerrar el aviso"
          title="Cerrar"
          className="shrink-0 -mt-0.5 h-7 w-7 rounded-md text-amber-700 hover:bg-amber-200 hover:text-amber-900 transition-colors text-lg leading-none"
        >
          ×
        </button>
      </div>
    </div>
  );
}
