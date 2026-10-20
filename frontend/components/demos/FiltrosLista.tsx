/**
 * Filtros de la lista (no tocan el resumen): búsqueda con espera de 300 ms,
 * tipo de empresa, estado de generación y etapa (selección única).
 */
import { useEffect, useRef, useState } from 'react';

import { TIPOS_EMPRESA } from '../../lib/demo_copy';
import type { Etapa, FiltroEstado } from '../../lib/demosAdmin';
import { campo, chip } from './FiltroRango';

export const ETAPAS: { clave: Etapa; texto: string }[] = [
  { clave: '', texto: 'Todas' },
  { clave: 'conversaron', texto: 'Conversaron' },
  { clave: 'traspaso', texto: 'Llegaron al traspaso' },
  { clave: 'whatsapp', texto: 'Clic en WhatsApp' },
  { clave: 'llamada_abierta', texto: 'Abrieron el agendador' },
  { clave: 'llamada_agendada', texto: 'Agendaron llamada' },
  { clave: 'pidieron_hablar', texto: 'Pidieron hablar' },
];

export default function FiltrosLista({
  q,
  tipo,
  estado,
  etapa,
  onQ,
  onTipo,
  onEstado,
  onEtapa,
}: {
  q: string;
  tipo: string;
  estado: FiltroEstado;
  etapa: Etapa;
  onQ: (v: string) => void;
  onTipo: (v: string) => void;
  onEstado: (v: FiltroEstado) => void;
  onEtapa: (v: Etapa) => void;
}) {
  // La búsqueda se escribe local y se manda 300 ms después de la última tecla.
  const [texto, setTexto] = useState(q);
  const espera = useRef<number | undefined>(undefined);
  useEffect(() => setTexto(q), [q]);

  const alEscribir = (v: string) => {
    setTexto(v);
    window.clearTimeout(espera.current);
    espera.current = window.setTimeout(() => onQ(v), 300);
  };
  useEffect(() => () => window.clearTimeout(espera.current), []);

  return (
    <div className="flex flex-col gap-3 mb-4">
      <div className="flex flex-col sm:flex-row gap-2">
        <label className="sr-only" htmlFor="demos-q">
          Buscar
        </label>
        <input
          id="demos-q"
          type="search"
          className={`${campo} flex-1 min-w-0`}
          placeholder="Buscar por nombre, empresa o correo"
          autoComplete="off"
          maxLength={100}
          value={texto}
          onChange={(e) => alEscribir(e.target.value)}
        />
        <label className="sr-only" htmlFor="demos-tipo">
          Tipo de empresa
        </label>
        <select id="demos-tipo" className={campo} value={tipo} onChange={(e) => onTipo(e.target.value)}>
          <option value="">Todos los tipos</option>
          {TIPOS_EMPRESA.map((t) => (
            <option key={t.clave} value={t.clave}>
              {t.etiqueta}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="demos-estado">
          Estado
        </label>
        <select
          id="demos-estado"
          className={campo}
          value={estado}
          onChange={(e) => onEstado(e.target.value as FiltroEstado)}
        >
          <option value="">Todos los estados</option>
          <option value="modelo">Lista · productos del modelo</option>
          <option value="respaldo">Lista · productos de respaldo</option>
          <option value="generando">Generando</option>
          <option value="error">Con error</option>
        </select>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Hasta dónde llegó">
        {ETAPAS.map((e) => (
          <button
            key={e.clave || 'todas'}
            type="button"
            className={chip(etapa === e.clave)}
            aria-pressed={etapa === e.clave}
            onClick={() => onEtapa(e.clave)}
          >
            {e.texto}
          </button>
        ))}
      </div>
    </div>
  );
}
