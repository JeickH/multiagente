/**
 * Filtro global del panel: el rango de fechas (manda sobre el resumen y la
 * lista) y «Ocultar pruebas de Gloma» (activado por defecto).
 */
import { type PresetRango } from '../../lib/demosAdmin';

const PRESETS: { clave: PresetRango; texto: string }[] = [
  { clave: 'hoy', texto: 'Hoy' },
  { clave: '7', texto: '7 días' },
  { clave: '30', texto: '30 días' },
  { clave: 'custom', texto: 'Personalizado' },
];

export const chip = (activo: boolean) =>
  `px-3 py-1.5 rounded-full text-xs font-medium border whitespace-nowrap transition-colors ${
    activo
      ? 'bg-gloma-brown text-white border-gloma-brown'
      : 'bg-white text-gloma-brown border-gloma-rose hover:bg-gloma-rose-soft'
  }`;

export const campo =
  'border border-gloma-rose rounded-[10px] px-2.5 py-1.5 text-[13px] text-gloma-brown bg-white focus:outline-none focus:border-gloma-mint focus:ring-[3px] focus:ring-gloma-mint/25';

export default function FiltroRango({
  preset,
  desde,
  hasta,
  hoy,
  ocultarInternas,
  errorRango,
  onPreset,
  onDesde,
  onHasta,
  onOcultarInternas,
}: {
  preset: PresetRango;
  desde: string;
  hasta: string;
  hoy: string;
  ocultarInternas: boolean;
  errorRango: string | null;
  onPreset: (p: PresetRango) => void;
  onDesde: (v: string) => void;
  onHasta: (v: string) => void;
  onOcultarInternas: (v: boolean) => void;
}) {
  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Rango de fechas">
        {PRESETS.map((p) => (
          <button
            key={p.clave}
            type="button"
            className={chip(preset === p.clave)}
            aria-pressed={preset === p.clave}
            onClick={() => onPreset(p.clave)}
          >
            {p.texto}
          </button>
        ))}
        {preset === 'custom' && (
          <span className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-gloma-brown-light">
              Desde{' '}
              <input type="date" className={`${campo} ml-1`} value={desde} max={hoy} onChange={(e) => onDesde(e.target.value)} />
            </label>
            <label className="text-xs text-gloma-brown-light">
              Hasta{' '}
              <input type="date" className={`${campo} ml-1`} value={hasta} max={hoy} onChange={(e) => onHasta(e.target.value)} />
            </label>
          </span>
        )}
        <label className="ml-auto inline-flex items-center gap-2 text-xs text-gloma-brown cursor-pointer select-none">
          <input
            type="checkbox"
            className="w-4 h-4 accent-gloma-brown"
            checked={ocultarInternas}
            onChange={(e) => onOcultarInternas(e.target.checked)}
          />
          Ocultar pruebas de Gloma
        </label>
      </div>
      {errorRango && (
        <p className="mt-2 text-xs text-red-700" role="alert">
          {errorRango}
        </p>
      )}
    </div>
  );
}
