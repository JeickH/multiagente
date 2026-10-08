import Link from 'next/link';
import { fechaHoraLarga } from '../../lib/fechas';
import {
  Interesado,
  haceTexto,
  msRestantes,
  nivelVentana,
  nombreVisible,
  textoInteres,
  textoMotivo,
  textoSenal,
  SENALES,
} from '../../lib/interesados';
import MenuDescartar from './MenuDescartar';
import RelojVentana, { ESTILO_NIVEL } from './RelojVentana';

type Props = {
  it: Interesado;
  ahoraServidor: number;
  puedeTomar: boolean;
  ocupado: boolean;
  /** Los `data-tour` del tutorial van solo en la primera tarjeta. */
  primera?: boolean;
  onTomar: (it: Interesado) => void;
  onContactado: (it: Interesado) => void;
  onDescartar: (it: Interesado, motivo: string) => void;
  onReabrir: (it: Interesado) => void;
};

const BTN_SEC =
  'min-h-[44px] md:min-h-[34px] px-3 rounded-lg border border-gray-300 hover:border-gloma-brown ' +
  'text-xs font-medium flex items-center justify-center bg-white disabled:opacity-50 ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-gloma-mint';
const BTN_PRI =
  'min-h-[44px] md:min-h-[38px] px-4 rounded-lg bg-gloma-brown hover:bg-gloma-brown-dark text-white ' +
  'text-sm font-semibold flex items-center justify-center disabled:opacity-60 ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-gloma-mint';

function Tiempo({ iso, ahora }: { iso: string | null; ahora: number }) {
  if (!iso) return null;
  return (
    <time dateTime={iso} title={fechaHoraLarga(iso)}>
      {haceTexto(iso, ahora)}
    </time>
  );
}

/**
 * Una persona con intención de compra. Lo que más pesa es el reloj (arriba a la
 * izquierda), después quién es, después la señal con la frase del cliente: esa
 * frase es lo que le deja a la asesora escribir algo concreto y no un saludo
 * genérico.
 *
 * Seguridad: el fragmento y el resumen son texto que escribió un tercero (el
 * cliente) o el modelo. Se pintan como texto plano de React — nada de
 * `dangerouslySetInnerHTML`, ni el formato de WhatsApp, ni autolinks.
 */
export default function TarjetaInteresado({
  it,
  ahoraServidor,
  puedeTomar,
  ocupado,
  primera,
  onTomar,
  onContactado,
  onDescartar,
  onReabrir,
}: Props) {
  const ms = msRestantes(it.ventana_cierra_at, ahoraServidor);
  const nivel = nivelVentana(ms);
  const estilo = ESTILO_NIVEL[nivel];
  const cerrada = nivel === 'cerrada';
  const gestionado = it.estado !== 'por_contactar';
  const interes = textoInteres(it.interes);
  const [principal, ...otras] = it.tipos || [];
  const tituloId = `interesado-${it.id}`;
  const tel = `tel:+${it.telefono}`;
  const chat = `/mensajes?conversacion=${it.conversation_id}`;
  const tour = (nombre: string) => (primera ? { 'data-tour': nombre } : {});

  // En Contactados / Descartados la tarjeta es más corta: ya no corre reloj.
  if (gestionado) {
    const etiqueta =
      it.estado === 'contactado'
        ? ['Contactado', haceTexto(it.gestionado_at, ahoraServidor), it.gestionado_por]
        : ['Descartado', textoMotivo(it.motivo_descarte).toLowerCase(), it.gestionado_por];
    return (
      <article
        aria-labelledby={tituloId}
        className={`bg-white rounded-xl border border-gray-200 p-4 ${
          it.estado === 'descartado' ? 'opacity-80' : ''
        }`}
      >
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h4 id={tituloId} className="font-body font-semibold text-base text-gloma-brown-darker break-words">
            {nombreVisible(it)}
          </h4>
          {it.contacto?.trim() ? (
            <a href={tel} className="text-sm text-gloma-brown hover:underline whitespace-nowrap">
              +{it.telefono}
            </a>
          ) : (
            <span className="text-xs text-gray-400">Sin nombre</span>
          )}
        </div>
        <p
          className={`mt-2 inline-flex px-2.5 py-1 rounded-full text-xs font-semibold ${
            it.estado === 'contactado'
              ? 'bg-gloma-soft-mint text-gloma-forest'
              : 'bg-gray-100 text-gray-600'
          }`}
        >
          {etiqueta.filter(Boolean).join(' · ')}
        </p>
        {principal && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 text-xs">
              {[textoSenal(principal), interes].filter(Boolean).join(' · ')}
            </span>
          </div>
        )}
        {it.estado === 'contactado' && (
          <p className="mt-2 text-xs text-gray-500">
            Lo sigue atendiendo 🤖 {it.bot?.nombre || 'el bot'}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Link href={chat} className={BTN_SEC}>
            Ver chat
          </Link>
          <button type="button" disabled={ocupado} onClick={() => onReabrir(it)} className={BTN_SEC}>
            Volver a &quot;Por contactar&quot;
          </button>
        </div>
      </article>
    );
  }

  return (
    <article
      aria-labelledby={tituloId}
      className={`bg-white rounded-xl border border-gray-200 border-l-4 ${estilo.borde} p-4 md:p-5`}
    >
      <div className="flex flex-col md:flex-row md:items-start gap-3 md:gap-5">
        <div className="md:w-44 shrink-0" {...tour('interesados-reloj')}>
          <RelojVentana ms={ms} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            {it.contacto?.trim() ? (
              <>
                <h4 id={tituloId} className="font-body font-semibold text-base text-gloma-brown-darker break-words">
                  {it.contacto}
                </h4>
                <a href={tel} className="text-sm text-gloma-brown hover:underline whitespace-nowrap">
                  +{it.telefono}
                </a>
              </>
            ) : (
              <>
                {/* Sin nombre, el teléfono es el título: en el celular, tocar = marcar. */}
                <h4 id={tituloId} className="font-body font-semibold text-base">
                  <a href={tel} className="text-gloma-brown-darker hover:underline whitespace-nowrap">
                    +{it.telefono}
                  </a>
                </h4>
                <span className="text-xs text-gray-400">Sin nombre</span>
              </>
            )}
          </div>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {principal && (
              <span className="px-2 py-0.5 rounded-full bg-gloma-soft-mint text-gloma-forest text-xs font-semibold">
                {textoSenal(principal)}
              </span>
            )}
            {otras.length > 0 && (
              <span
                className="px-2 py-0.5 rounded-full bg-white border border-gloma-soft-mint text-gloma-forest text-xs"
                title={`También: ${otras.map((t) => SENALES[t]?.texto ?? t).join(', ')}`}
              >
                +{otras.length} {otras.length === 1 ? 'señal' : 'señales'}
                <span className="sr-only">: {otras.map((t) => SENALES[t]?.texto ?? t).join(', ')}</span>
              </span>
            )}
            <span
              className={`px-2 py-0.5 rounded-full bg-gray-100 text-xs ${
                interes ? 'text-gray-700' : 'text-gray-500'
              }`}
            >
              {interes || 'Plan sin definir'}
            </span>
          </div>

          {it.fragmento && (
            <blockquote
              className={`mt-2 text-sm text-gray-700 border-l-2 pl-3 line-clamp-2 md:line-clamp-none break-words ${
                cerrada ? 'border-gray-300' : 'border-gloma-mint'
              }`}
              {...tour('interesados-fragmento')}
            >
              «{it.fragmento}»
            </blockquote>
          )}
          {it.resumen && (
            <p className="mt-2 text-xs text-gray-600 line-clamp-2 md:line-clamp-3 break-words">
              <span className="font-semibold text-gray-500">Resumen del bot (no verificado): </span>
              {it.resumen}
            </p>
          )}

          <p className="mt-2 text-xs text-gray-500">
            Detectado <Tiempo iso={it.detectado_at} ahora={ahoraServidor} /> · Primer mensaje{' '}
            <Tiempo iso={it.conversacion_inicio_at} ahora={ahoraServidor} />
            {it.bot && <> · Lo atiende 🤖 {it.bot.nombre}</>}
          </p>
        </div>

        <div className="flex flex-col gap-2 md:w-48 shrink-0" {...tour('interesados-acciones')}>
          {/* Con la ventana cerrada la acción principal es LLAMAR: tomar el chat
              no deja escribir texto libre. */}
          {cerrada ? (
            <a href={tel} className={BTN_PRI}>
              Llamar
            </a>
          ) : (
            puedeTomar && (
              <button type="button" disabled={ocupado} onClick={() => onTomar(it)} className={BTN_PRI}>
                Tomar conversación
              </button>
            )
          )}
          <div className="grid grid-cols-[repeat(auto-fit,minmax(84px,1fr))] md:grid-cols-1 gap-2">
            <Link href={chat} className={BTN_SEC}>
              Ver chat
            </Link>
            <button type="button" disabled={ocupado} onClick={() => onContactado(it)} className={BTN_SEC}>
              Ya lo contacté
            </button>
            <MenuDescartar
              disabled={ocupado}
              onElegir={(m) => onDescartar(it, m)}
              className={BTN_SEC}
            />
          </div>
        </div>
      </div>
    </article>
  );
}
