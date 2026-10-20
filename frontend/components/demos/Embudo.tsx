/**
 * Resumen del panel: el embudo (un tronco y una rama, no seis escalones) y
 * dos tarjetas: «Pidieron hablar con Gloma» y «Cómo salieron los bots».
 *
 * Se cuentan demos, no clics. Cada porcentaje dice sobre qué se calcula. Una
 * etapa es un botón: tocarla filtra la lista por esa etapa (y tocarla otra vez
 * quita el filtro). El resumen depende solo del rango y de las internas.
 */
import { pct, type Etapa, type FiltroEstado, type ResumenDemos } from '../../lib/demosAdmin';
import { Esq, Spin } from './piezas';

function Fila({
  etapa,
  activa,
  texto,
  n,
  max,
  nota,
  sangria = false,
  onElegir,
}: {
  etapa: Etapa;
  activa: boolean;
  texto: string;
  n: number;
  max: number;
  nota: string;
  sangria?: boolean;
  onElegir: (e: Etapa) => void;
}) {
  const ancho = max ? Math.max((n / max) * 100, n ? 2 : 0) : 0;
  return (
    <button
      type="button"
      onClick={() => onElegir(etapa)}
      aria-pressed={etapa ? activa : undefined}
      title={`${texto}: ${n} demos. Ver en la lista`}
      className={`group w-full text-left rounded-lg px-2 py-2 grid grid-cols-[1fr_auto] md:grid-cols-[11rem_1fr_14rem] items-center gap-x-3 gap-y-1 hover:bg-gloma-cream ${
        activa ? 'bg-gloma-rose-soft' : ''
      }`}
    >
      <span className={`text-sm text-gloma-brown font-medium ${sangria ? 'md:pl-4' : ''}`}>{texto}</span>
      <b className="md:hidden text-gloma-brown font-heading text-base text-right">{n}</b>
      <span className="col-span-2 md:col-span-1 bg-gloma-rose-soft/60 rounded-r h-3" aria-hidden="true">
        <span
          className="block h-3 rounded-r bg-gloma-brown group-hover:bg-gloma-brown-darker transition-[width] duration-300 motion-reduce:transition-none"
          style={{ width: `${ancho}%` }}
        />
      </span>
      <span className="col-span-2 md:col-span-1 md:text-right">
        <b className="hidden md:inline text-gloma-brown font-heading text-base">{n}</b>{' '}
        <span className="text-xs text-gloma-brown-light">{nota}</span>
      </span>
    </button>
  );
}

export default function Embudo({
  resumen,
  cargando,
  rangoTexto,
  etapa,
  onEtapa,
  onEstado,
  onVer30,
}: {
  resumen: ResumenDemos | null;
  cargando: boolean;
  rangoTexto: string;
  etapa: Etapa;
  onEtapa: (e: Etapa) => void;
  onEstado: (e: FiltroEstado) => void;
  onVer30: () => void;
}) {
  const r = resumen;
  const elegir = (e: Etapa) => onEtapa(e && e === etapa ? '' : e);

  let cuerpo: React.ReactNode;
  if (!r && cargando) {
    cuerpo = (
      <div className="space-y-3 py-1" aria-hidden="true">
        {[90, 75, 60, 45, 35, 25].map((w) => (
          <div key={w} className="flex items-center gap-3 px-2">
            <Esq className="h-3 w-36 shrink-0" />
            <span className="block h-3 rounded-md bg-gloma-rose-soft animate-pulse motion-reduce:animate-none" style={{ width: `${w}%` }} />
          </div>
        ))}
      </div>
    );
  } else if (!r || r.demos === 0) {
    cuerpo = (
      <div className="py-8 text-center text-gloma-brown-light">
        <p className="text-sm font-medium text-gloma-brown">Ninguna demo en este rango</p>
        <button
          type="button"
          onClick={onVer30}
          className="mt-3 px-4 py-2 rounded-full text-xs font-semibold border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft"
        >
          Ver los últimos 30 días
        </button>
      </div>
    );
  } else {
    cuerpo = (
      <>
        <Fila etapa="" activa={false} texto="Demos creadas" n={r.demos} max={r.demos} nota="100 %" onElegir={elegir} />
        <Fila etapa="conversaron" activa={etapa === 'conversaron'} texto="Conversaron" n={r.conversaron} max={r.demos} nota={`${pct(r.conversaron, r.demos)} de las creadas`} onElegir={elegir} />
        <Fila etapa="traspaso" activa={etapa === 'traspaso'} texto="Llegaron al traspaso" n={r.traspaso} max={r.demos} nota={`${pct(r.traspaso, r.conversaron)} de las que conversaron`} onElegir={elegir} />
        <div className="flex items-center gap-2 mt-3 mb-1 px-2">
          <span className="text-[11px] uppercase tracking-wider font-semibold text-gloma-brown-light">Pidieron hablar con Gloma</span>
          <span className="flex-1 h-px bg-gloma-rose-soft" />
        </div>
        <Fila etapa="whatsapp" activa={etapa === 'whatsapp'} texto="Clic en WhatsApp" n={r.clic_whatsapp} max={r.demos} nota={`${pct(r.clic_whatsapp, r.demos)} de las creadas`} onElegir={elegir} />
        <Fila etapa="llamada_abierta" activa={etapa === 'llamada_abierta'} texto="Abrieron el agendador" n={r.abrieron_llamada} max={r.demos} nota={`${pct(r.abrieron_llamada, r.demos)} de las creadas`} onElegir={elegir} />
        <Fila
          etapa="llamada_agendada"
          activa={etapa === 'llamada_agendada'}
          texto="↳ Agendaron llamada"
          n={r.agendaron_llamada}
          max={r.demos}
          nota={`${pct(r.agendaron_llamada, r.abrieron_llamada)} de las que lo abrieron`}
          sangria
          onElegir={elegir}
        />
      </>
    );
  }

  const salud: { clave: Exclude<FiltroEstado, ''>; icono: React.ReactNode; texto: string; clase: string }[] = [
    { clave: 'modelo', icono: '✓', texto: 'Con productos del modelo', clase: 'text-gloma-brown' },
    { clave: 'respaldo', icono: '◐', texto: 'Con productos de respaldo', clase: 'text-amber-700' },
    { clave: 'generando', icono: <Spin />, texto: 'Generando ahora', clase: 'text-gloma-brown-light' },
    { clave: 'error', icono: '⚠', texto: 'Con error', clase: 'text-red-700' },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 bg-white rounded-xl border border-gloma-rose p-4 md:p-5">
        <div className="flex items-baseline justify-between gap-2 mb-3">
          <h2 className="font-heading font-bold text-gloma-brown text-lg">Embudo</h2>
          <span className="text-xs text-gloma-brown-light">{rangoTexto}</span>
        </div>
        {cuerpo}
        <p className="text-[11px] text-gloma-brown-light mt-3">
          Se cuentan <b>demos</b>, no clics: una demo con 3 clics en WhatsApp suma 1. Toca una etapa para ver esas demos en la
          lista. «Agendaron» lo reporta el navegador del prospecto: puede quedarse corto.
        </p>
      </div>
      <div className="flex flex-col gap-4">
        <div className="bg-white rounded-xl border border-gloma-rose px-5 py-4">
          <button type="button" onClick={() => elegir('pidieron_hablar')} aria-pressed={etapa === 'pidieron_hablar'} className="w-full text-left">
            <span className="block text-xs text-gloma-brown-light">Pidieron hablar con Gloma</span>
            <span className="flex items-baseline gap-2 mt-1">
              {r ? (
                <span className="text-4xl font-heading font-bold text-gloma-brown">{r.pidieron_hablar}</span>
              ) : (
                <Esq className="h-8 w-12" />
              )}
              {r && r.demos > 0 && <span className="text-sm text-gloma-brown-light">{pct(r.pidieron_hablar, r.demos)} de las creadas</span>}
            </span>
          </button>
          <p className="text-[11px] text-gloma-brown-light mt-1">WhatsApp o agendador, sin contar dos veces a la misma demo.</p>
        </div>
        <div className="bg-white rounded-xl border border-gloma-rose px-5 py-4">
          <div className="text-xs text-gloma-brown-light mb-2">Cómo salieron los bots</div>
          <ul className="space-y-1.5 text-sm">
            {salud.map((s) => (
              <li key={s.clave}>
                <button
                  type="button"
                  onClick={() => onEstado(s.clave)}
                  className="w-full flex items-center gap-2 rounded px-1 -mx-1 hover:bg-gloma-cream"
                >
                  <span className={`${s.clase} w-5 text-center`} aria-hidden="true">
                    {s.icono}
                  </span>
                  <span className="flex-1 text-left text-gloma-brown">{s.texto}</span>
                  <b className="text-gloma-brown">{r ? r.por_estado[s.clave] : '·'}</b>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
