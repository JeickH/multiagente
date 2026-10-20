/**
 * Formulario de la demo (etapa 1). Una columna, validación al salir del campo
 * y al enviar; una vez marcado un error se revalida mientras se escribe.
 *
 * Controles de #608 que viven aquí: el honeypot `sitio_web` (fuera de
 * pantalla, fuera del orden de tabulación y oculto a lectores de pantalla),
 * los dos consentimientos SIN marcar y el enlace a `/privacidad`. El tiempo de
 * llenado lo mide `DemoPage`; Turnstile llega como `turnstile` (slot).
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { DEMO_UI, TIPOS_EMPRESA, TIPO_OTRO } from '../../lib/demo_copy';
import {
  FORMULARIO_VACIO,
  ORDEN_CAMPOS as ORDEN,
  validarCampo,
  type AlertaFormulario,
  type Campo,
  type DatosFormulario,
} from '../../lib/demoFormulario';
import { PAISES_TELEFONO, PAIS_OTRO, paisPorIso } from '../../lib/telefonoPais';
import CtaAgendar, { type AccionesAgendar } from './CtaAgendar';
import { IconoAlerta, IconoError } from './iconos';

const E = DEMO_UI.form.errores;

/** Mapea un campo que el backend rechazó (422) a un campo del formulario. */
function campoDelServidor(c: string): Campo | null {
  if (c === 'tipo_otro') return 'tipo_empresa';
  return (ORDEN as string[]).includes(c) ? (c as Campo) : null;
}

const CLASE_INPUT =
  'w-full px-[14px] py-3 rounded-xl text-[15px] bg-white/[0.03] text-gloma-ink-text border border-white/40 ' +
  'placeholder:text-white/45 transition-[border-color,box-shadow] duration-150 ' +
  'focus:outline-none focus:border-gloma-mint focus:ring-[3px] focus:ring-gloma-mint/30 ' +
  'aria-[invalid=true]:border-gloma-ink-err aria-[invalid=true]:focus:ring-gloma-ink-err/25 ' +
  'disabled:opacity-60';

function MensajeError({ id, texto }: { id: string; texto: string }) {
  return (
    // Clase en vez del atributo `hidden`: `flex` le ganaría al atributo y
    // quedaría el ícono solo. El nodo existe siempre por el `aria-describedby`.
    <p id={id} className={texto ? 'flex gap-1.5 items-start text-[13px] text-gloma-ink-err mt-1.5' : 'hidden'}>
      <IconoError />
      <span>{texto}</span>
    </p>
  );
}

export type { AlertaFormulario, DatosFormulario };

export default function DemoForm({
  onIniciar,
  enviando,
  alerta,
  camposRechazados,
  acciones,
  turnstile,
  inicial,
}: {
  onIniciar: (datos: DatosFormulario) => void;
  enviando: boolean;
  alerta: AlertaFormulario;
  /** Campos que el backend rechazó en el último 422. */
  camposRechazados: string[];
  /** Agendar una llamada / WhatsApp, para el aviso de tope (429). */
  acciones: AccionesAgendar;
  turnstile: ReactNode;
  /** Datos del último intento (al volver de una demo); los consentimientos se piden de nuevo. */
  inicial?: DatosFormulario | null;
}) {
  const [d, setD] = useState<DatosFormulario>(() =>
    inicial ? { ...inicial, acepta_contacto: false, acepta_promociones: false, sitio_web: '' } : FORMULARIO_VACIO,
  );
  const [errores, setErrores] = useState<Partial<Record<Campo, string>>>({});
  const tocados = useRef<Set<Campo>>(new Set());
  const refs = useRef<Partial<Record<Campo, HTMLInputElement | HTMLSelectElement | null>>>({});
  const t = DEMO_UI.form;

  // Errores que vienen del backend (422): se pintan en su campo con un texto
  // genérico hasta que la persona edite ese campo.
  const [servidor, setServidor] = useState<Set<Campo>>(new Set());
  useEffect(() => {
    const s = new Set<Campo>();
    camposRechazados.forEach((c) => {
      const campo = campoDelServidor(c);
      if (campo) s.add(campo);
    });
    setServidor(s);
  }, [camposRechazados]);
  const errorDe = (c: Campo) => errores[c] || (servidor.has(c) ? E.generico : '');

  const validar = (c: Campo, datos: DatosFormulario) => {
    const msg = validarCampo(c, datos);
    setErrores((prev) => ({ ...prev, [c]: msg }));
    return msg;
  };

  const cambiar = <K extends keyof DatosFormulario>(campo: K, valor: DatosFormulario[K]) => {
    const sig = { ...d, [campo]: valor };
    // «Otro» se oculta y se BORRA si se elige otro tipo: no se manda.
    if (campo === 'tipo_empresa' && valor !== TIPO_OTRO.clave) sig.tipo_otro = '';
    if (campo === 'telefono_pais' && valor !== PAIS_OTRO) sig.telefono_indicativo = '';
    setD(sig);
    // El país y el indicativo son parte del teléfono: se revalida ese campo.
    const c = (campo === 'telefono_pais' || campo === 'telefono_indicativo' ? 'telefono' : campo) as Campo;
    if (!ORDEN.includes(c)) return;
    tocados.current.add(c);
    if (servidor.has(c)) {
      setServidor((prev) => {
        const s = new Set(prev);
        s.delete(c);
        return s;
      });
    }
    // Revalida mientras se escribe solo si el campo ya estaba en error, o si
    // es un select/checkbox (ahí el cambio es la interacción completa).
    const esSelector = c === 'tipo_empresa' || c === 'acepta_contacto' || (c === 'telefono' && campo !== 'telefono' && Boolean(sig.telefono.trim()));
    if (errores[c] || esSelector) validar(c, sig);
  };

  const alSalir = (c: Campo) => {
    const valor = d[c];
    if ((typeof valor === 'string' && valor.trim()) || tocados.current.has(c)) validar(c, d);
  };

  const enviar = (e: React.FormEvent) => {
    e.preventDefault();
    if (enviando) return; // bloquea el doble envío: cada intento gasta cupo
    const nuevos: Partial<Record<Campo, string>> = {};
    ORDEN.forEach((c) => {
      nuevos[c] = validarCampo(c, d);
      tocados.current.add(c);
    });
    setErrores(nuevos);
    const primero = ORDEN.find((c) => nuevos[c]);
    if (primero) {
      refs.current[primero]?.focus();
      return;
    }
    onIniciar(d);
  };

  const otro = d.tipo_empresa === TIPO_OTRO.clave;
  const pais = paisPorIso(d.telefono_pais);
  const bloqueado = enviando || alerta === 'tope';

  const props = (c: Campo, extraDescr = '') => ({
    'aria-invalid': errorDe(c) ? true : undefined,
    'aria-describedby': `${extraDescr} e-${c}`.trim(),
    onBlur: () => alSalir(c),
  });

  return (
    <form
      noValidate
      onSubmit={enviar}
      aria-labelledby="t-form"
      className="relative rounded-3xl p-5 md:p-7 bg-gloma-ink/80 backdrop-blur border border-gloma-mint/20 shadow-2xl"
    >
      <h2 id="t-form" className="font-heading font-bold text-xl text-white">
        {t.titulo}
      </h2>
      <p className="text-xs text-gloma-ink-muted mt-1 mb-5">{t.obligatorios}</p>

      <fieldset disabled={bloqueado} className="space-y-4">
        <legend className="sr-only">Tus datos para la demo</legend>

        <div>
          <label htmlFor="f-nombre" className="block text-sm font-medium text-gloma-ink-text mb-1.5">
            {t.nombre}
          </label>
          <input
            id="f-nombre"
            ref={(el) => {
              refs.current.nombre = el;
            }}
            className={CLASE_INPUT}
            autoComplete="given-name"
            maxLength={80}
            value={d.nombre}
            onChange={(e) => cambiar('nombre', e.target.value)}
            {...props('nombre')}
          />
          <MensajeError id="e-nombre" texto={errorDe('nombre')} />
        </div>

        <div>
          <label htmlFor="f-empresa" className="block text-sm font-medium text-gloma-ink-text mb-1.5">
            {t.empresa}
          </label>
          <input
            id="f-empresa"
            ref={(el) => {
              refs.current.empresa = el;
            }}
            className={CLASE_INPUT}
            autoComplete="organization"
            maxLength={80}
            value={d.empresa}
            onChange={(e) => cambiar('empresa', e.target.value)}
            {...props('empresa', 'h-empresa')}
          />
          <p id="h-empresa" className="text-xs text-gloma-ink-muted mt-1.5">
            {t.empresaAyuda}
          </p>
          <MensajeError id="e-empresa" texto={errorDe('empresa')} />
        </div>

        <div>
          <label htmlFor="f-tipo" className="block text-sm font-medium text-gloma-ink-text mb-1.5">
            {t.tipo}
          </label>
          <select
            id="f-tipo"
            ref={(el) => {
              refs.current.tipo_empresa = el;
            }}
            className={`${CLASE_INPUT} demo-select appearance-none pr-10 bg-gloma-ink-alt`}
            value={d.tipo_empresa}
            onChange={(e) => cambiar('tipo_empresa', e.target.value)}
            {...props('tipo_empresa')}
          >
            <option value="" disabled>
              {t.tipoPlaceholder}
            </option>
            {TIPOS_EMPRESA.map((tipo) => (
              <option key={tipo.clave} value={tipo.clave}>
                {tipo.etiqueta}
              </option>
            ))}
          </select>
          <MensajeError id="e-tipo_empresa" texto={errorDe('tipo_empresa')} />
        </div>

        {otro && (
          <div className="demo-entra pl-3 border-l-2 border-gloma-mint/40">
            <label htmlFor="f-otro" className="block text-sm font-medium text-gloma-ink-text mb-1.5">
              {TIPO_OTRO.label} <span className="font-normal text-gloma-ink-muted">{t.opcional}</span>
            </label>
            <input
              id="f-otro"
              className={CLASE_INPUT}
              maxLength={TIPO_OTRO.maxCaracteres}
              placeholder={TIPO_OTRO.placeholder}
              aria-describedby="h-otro"
              value={d.tipo_otro}
              onChange={(e) => cambiar('tipo_otro', e.target.value)}
            />
            <p id="h-otro" className="text-xs text-gloma-ink-muted mt-1.5">
              {d.tipo_otro.length}/{TIPO_OTRO.maxCaracteres}
            </p>
          </div>
        )}

        <div>
          <label htmlFor="f-tel" className="block text-sm font-medium text-gloma-ink-text mb-1.5">
            {t.telefono}
          </label>
          <div className="flex gap-2">
            {/* Selector de país: un <select> nativo transparente encima de una
                caja que muestra solo la bandera y el indicativo. En celular abre
                el selector del sistema con los nombres completos; el lector de
                pantalla lee «País del teléfono, Colombia (+57)». */}
            <div className="relative shrink-0 group rounded-xl focus-within:ring-[3px] focus-within:ring-gloma-mint/30">
              <label htmlFor="f-tel-pais" className="sr-only">
                {t.telefonoPais}
              </label>
              <div
                aria-hidden="true"
                className="h-full min-h-[48px] flex items-center gap-1.5 pl-3 pr-8 rounded-xl border border-white/40 bg-white/[0.03] text-[15px] text-gloma-ink-text demo-select whitespace-nowrap group-focus-within:border-gloma-mint"
              >
                <span className="text-lg leading-none">{pais.bandera}</span>
                {/* En «Otro» el indicativo va en su propio campo: aquí solo el globo. */}
                {pais.iso !== PAIS_OTRO && <span className="tabular-nums">+{pais.indicativo}</span>}
              </div>
              <select
                id="f-tel-pais"
                value={d.telefono_pais}
                onChange={(e) => cambiar('telefono_pais', e.target.value)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer rounded-xl"
              >
                {PAISES_TELEFONO.map((p) => (
                  <option key={p.iso} value={p.iso}>
                    {p.bandera} {p.nombre}
                    {p.indicativo ? ` (+${p.indicativo})` : ''}
                  </option>
                ))}
              </select>
            </div>
            {pais.iso === PAIS_OTRO && (
              <div className="relative w-[4.75rem] shrink-0">
                <label htmlFor="f-tel-ind" className="sr-only">
                  {t.telefonoIndicativo}
                </label>
                <span aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-gloma-ink-muted">
                  +
                </span>
                <input
                  id="f-tel-ind"
                  inputMode="numeric"
                  autoComplete="tel-country-code"
                  maxLength={4}
                  className={`${CLASE_INPUT} pl-6`}
                  placeholder="1"
                  value={d.telefono_indicativo}
                  onChange={(e) => cambiar('telefono_indicativo', e.target.value.replace(/\D/g, ''))}
                  aria-describedby="h-tel-otro"
                />
              </div>
            )}
            <input
              id="f-tel"
              ref={(el) => {
                refs.current.telefono = el;
              }}
              type="tel"
              inputMode="tel"
              className={`${CLASE_INPUT} min-w-0 flex-1`}
              autoComplete="tel-national"
              maxLength={20}
              placeholder={pais.ejemplo}
              value={d.telefono}
              onChange={(e) => cambiar('telefono', e.target.value)}
              {...props('telefono', pais.iso === PAIS_OTRO ? 'h-tel-otro' : '')}
            />
          </div>
          {pais.iso === PAIS_OTRO && (
            <p id="h-tel-otro" className="text-xs text-gloma-ink-muted mt-1.5">
              {t.telefonoAyudaOtro}
            </p>
          )}
          <MensajeError id="e-telefono" texto={errorDe('telefono')} />
        </div>

        <div>
          <label htmlFor="f-correo" className="block text-sm font-medium text-gloma-ink-text mb-1.5">
            {t.correo}
          </label>
          <input
            id="f-correo"
            ref={(el) => {
              refs.current.correo = el;
            }}
            type="email"
            inputMode="email"
            className={CLASE_INPUT}
            autoComplete="email"
            maxLength={254}
            value={d.correo}
            onChange={(e) => cambiar('correo', e.target.value)}
            {...props('correo')}
          />
          <MensajeError id="e-correo" texto={errorDe('correo')} />
        </div>

        {/* Honeypot (#608, M7). Una persona no lo ve ni llega a él con Tab;
            un bot que llena todo lo marca. No usa `display:none` porque
            algunos bots se saltan los campos ocultos así. */}
        <div aria-hidden="true" className="absolute -left-[10000px] top-auto w-px h-px overflow-hidden">
          <label htmlFor="f-sitio-web">Sitio web</label>
          <input
            id="f-sitio-web"
            name="sitio_web"
            type="text"
            tabIndex={-1}
            autoComplete="off"
            value={d.sitio_web}
            onChange={(e) => setD((prev) => ({ ...prev, sitio_web: e.target.value }))}
          />
        </div>

        <div className="pt-1">
          <label className="flex gap-3 items-start text-[13px] leading-normal text-[#C9D3D1] cursor-pointer py-1.5">
            <input
              type="checkbox"
              ref={(el) => {
                refs.current.acepta_contacto = el;
              }}
              className="w-5 h-5 mt-px shrink-0 accent-gloma-mint"
              checked={d.acepta_contacto}
              onChange={(e) => cambiar('acepta_contacto', e.target.checked)}
              aria-invalid={errorDe('acepta_contacto') ? true : undefined}
              aria-describedby="e-acepta_contacto"
            />
            <span>
              {t.checkContacto}{' '}
              <a
                href="/privacidad"
                target="_blank"
                rel="noopener noreferrer"
                className="underline text-gloma-mint hover:text-gloma-rose"
              >
                {t.linkPrivacidad}
                <span className="sr-only">{t.nuevaPestana}</span>
              </a>
              .
            </span>
          </label>
          <div className="ml-8">
            <MensajeError id="e-acepta_contacto" texto={errorDe('acepta_contacto')} />
          </div>
          <label className="flex gap-3 items-start text-[13px] leading-normal text-[#C9D3D1] cursor-pointer py-1.5">
            <input
              type="checkbox"
              className="w-5 h-5 mt-px shrink-0 accent-gloma-mint"
              checked={d.acepta_promociones}
              onChange={(e) => cambiar('acepta_promociones', e.target.checked)}
            />
            <span>
              {t.checkPromos} <span className="text-gloma-ink-muted">{t.opcional}</span>
            </span>
          </label>
        </div>
      </fieldset>

      {turnstile}

      {(alerta === 'red' || alerta === 'verificacion') && (
        <div
          role="alert"
          className="mt-4 rounded-2xl border border-gloma-ink-err/50 bg-gloma-ink-err/10 p-3 text-sm text-gloma-ink-text flex gap-3"
        >
          <IconoAlerta />
          <p>{alerta === 'red' ? t.errorRed : t.errorVerificacion}</p>
        </div>
      )}

      {alerta === 'tope' ? (
        <div role="alert" className="mt-4 rounded-2xl border border-gloma-mint/40 bg-gloma-mint/10 p-4 text-sm text-gloma-ink-text">
          <p className="font-heading font-bold text-base text-white">{t.topeTitulo}</p>
          <p className="mt-1 text-gloma-ink-muted">{t.topeTexto}</p>
          <CtaAgendar acciones={acciones} variante="bloque" className="mt-3" />
        </div>
      ) : (
        <div className="mt-5">
          <button type="submit" className="demo-btn-primario w-full" aria-busy={enviando} disabled={enviando}>
            {enviando && <span className="demo-spin" aria-hidden="true" />}
            <span>{enviando ? t.botonEnviando : t.boton}</span>
          </button>
        </div>
      )}
    </form>
  );
}
