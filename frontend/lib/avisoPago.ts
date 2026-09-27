/**
 * Estado de cobro de la cuenta: `GET /pagos/aviso`.
 *
 * Lo leen tres lugares en la misma pantalla —el aviso de arriba, la bandeja y
 * campañas— y no tiene sentido que cada uno haga su propia petición. Se
 * comparte la misma promesa durante un minuto: alcanza para una navegación
 * normal y, después de pagar, el aviso rojo se va solo sin tener que recargar.
 *
 * `pausado` NO es una decisión del frontend. El backend bloquea los envíos
 * con 402 por su cuenta; esto solo sirve para no ofrecerle al usuario un
 * botón que va a fallar, y para decirle por qué.
 */
import { useEffect, useState } from 'react';

import { authedFetch } from './api';
import { haySesion } from './session';

export type AvisoPago = { mostrar: boolean; clave: string | null; pausado: boolean };

const VIGENCIA_MS = 60_000;

let enVuelo: Promise<AvisoPago> | null = null;
let pedidoEn = 0;

export function consultarAvisoPago(): Promise<AvisoPago> {
  if (!enVuelo || Date.now() - pedidoEn > VIGENCIA_MS) {
    pedidoEn = Date.now();
    enVuelo = authedFetch<AvisoPago>('/pagos/aviso').catch((e) => {
      enVuelo = null; // un fallo no se queda cacheado
      throw e;
    });
  }
  return enVuelo;
}

/**
 * ¿La cuenta tiene el servicio pausado? `false` mientras carga o si la
 * consulta falla: en la duda no se bloquea nada en pantalla, y si de verdad
 * está pausada el backend responde 402 con el mensaje.
 */
export function useServicioPausado(): boolean {
  const [pausado, setPausado] = useState(false);

  useEffect(() => {
    // Sin sesión no se pregunta: `authedFetch` cerraría la sesión y mandaría
    // al login, y de eso se encarga el guard de `_app`.
    if (!haySesion()) return;
    let cancelado = false;
    consultarAvisoPago()
      .then((r) => {
        if (!cancelado) setPausado(r.pausado === true);
      })
      .catch(() => {
        /* en silencio: ver arriba */
      });
    return () => {
      cancelado = true;
    };
  }, []);

  return pausado;
}
