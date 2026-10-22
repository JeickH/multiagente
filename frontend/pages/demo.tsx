/**
 * Demo interactiva pública: `glomacx.com/demo` (Sprint 32, #614).
 *
 * Una sola ruta y un solo estado, sin cambiar de URL entre etapas:
 *   formulario → slides (mientras se arma el bot) → chat tipo WhatsApp.
 *
 * - Diseño y estados: wireframe #611 (`ventas/identidad_gloma/diseno_demo.html`).
 * - Textos: `lib/demo_copy.ts` (`DEMO_COPY` de Belfort + `DEMO_UI`).
 * - API: `lib/demoApi.ts` (contrato del Sprint 32; modo simulado con
 *   `NEXT_PUBLIC_DEMO_MOCK=1`).
 *
 * Es pública: está en `PUBLIC_PAGES` de `_app.tsx` y en el allowlist del
 * middleware para los dominios de la marca. NO toca la sesión de la
 * plataforma (`lib/session.ts`): el acceso a la demo es el token propio que
 * devuelve `POST /demo/iniciar`, en `sessionStorage['gloma_demo']`.
 *
 * Sondeo del estado (`GET /demo/{id}/estado`): cada 1,5 s; a los 20 s el
 * aviso de demora; a los 90 s se trata como error y se deja de consultar.
 * Tres fallas de red seguidas → «Reconectando…» con espera creciente. Un 404
 * es «esta demo ya no está disponible». Los tiempos se cuentan desde que se
 * creó la demo, así que recargar no los reinicia.
 */
import Head from 'next/head';
import Image from 'next/image';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import DemoChat from '../components/demo/DemoChat';
import DemoForm, { type AlertaFormulario, type DatosFormulario } from '../components/demo/DemoForm';
import DemoIntro from '../components/demo/DemoIntro';
import DemoNoDisponible from '../components/demo/DemoNoDisponible';
import DemoPremio from '../components/demo/DemoPremio';
import DemoSlides from '../components/demo/DemoSlides';
import AgendarLlamadaModal from '../components/AgendarLlamadaModal';
import type { AccionesAgendar } from '../components/demo/CtaAgendar';
import Turnstile, { TURNSTILE_ACTIVO } from '../components/demo/Turnstile';
import { DEMO_UI, TIPO_OTRO } from '../lib/demo_copy';
import { telefonoE164 } from '../lib/demoFormulario';
import { esTelefonoColombia, formatearE164 } from '../lib/telefonoPais';
import {
  DemoApiError,
  borrarDemo,
  consultarEstado,
  enlaceWhatsapp,
  guardarDemo,
  iniciarDemo,
  leerDemoGuardada,
  registrarEvento,
  type ChatGuardado,
  type DatosIniciar,
  type DemoGuardada,
  type EstadoGeneracion,
  type ProductoDemo,
} from '../lib/demoApi';

// `premio` (#643) va entre el formulario y las slides, una sola vez. No se
// guarda en `gloma_demo` (que ya dice «slides»): al recargar no vuelve.
type Etapa = 'formulario' | 'premio' | 'cargando' | 'slides' | 'chat' | 'no_disponible';

interface Generacion {
  estado: EstadoGeneracion;
  productos: ProductoDemo[];
  mensajeSugerido: string;
}

const GEN_INICIAL: Generacion = { estado: 'generando', productos: [], mensajeSugerido: '' };

const SONDEO_MS = 1500;
const AVISO_DEMORA_MS = 20000;
const CORTE_MS = 90000;
/**
 * Tiempo mínimo de llenado que exige el backend (#608, M7). Con
 * autocompletar una persona real llena el formulario en menos de 3 s, y el
 * backend le responde un 202 falso: terminaba en «Esta demo ya no está
 * disponible» y el lead se perdía (#619). Por eso el front espera lo que
 * falte, con el botón en «Preparando tu demo…», y recién ahí hace el POST.
 */
const LLENADO_MINIMO_MS = 3000;

const FONDO = 'linear-gradient(120deg, #101817 40%, #00362E 100%)';

function primerNombre(nombre: string): string {
  return nombre.trim().split(/\s+/)[0] || '';
}

export default function DemoPage() {
  const [etapa, setEtapa] = useState<Etapa>('formulario');
  const [demo, setDemo] = useState<DemoGuardada | null>(null);
  const [gen, setGen] = useState<Generacion>(GEN_INICIAL);
  const [lento, setLento] = useState(false);
  const [reconectando, setReconectando] = useState(false);
  const [animarListo, setAnimarListo] = useState(false);
  const [chatInicial, setChatInicial] = useState<ChatGuardado | undefined>(undefined);
  const [noDisponibleEnChat, setNoDisponibleEnChat] = useState(false);
  /** Lo que muestra la pantalla de premio; solo en memoria (no va a sessionStorage). */
  const [premio, setPremio] = useState<{ correo: string; telefono: string; colombia: boolean } | null>(null);

  const [enviando, setEnviando] = useState(false);
  const [alerta, setAlerta] = useState<AlertaFormulario>(null);
  const [camposRechazados, setCamposRechazados] = useState<string[]>([]);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [turnstileReinicio, setTurnstileReinicio] = useState(0);

  const ultimosDatos = useRef<DatosFormulario | null>(null);
  const formAbiertoMs = useRef<number>(0);
  const demoRef = useRef<DemoGuardada | null>(null);
  demoRef.current = demo;
  const etapaRef = useRef<Etapa>(etapa);
  etapaRef.current = etapa;

  // Al montar: el reloj del formulario y, si hay una demo en curso en esta
  // pestaña, retomarla.
  useEffect(() => {
    formAbiertoMs.current = Date.now();
    const guardada = leerDemoGuardada();
    if (!guardada) return;
    setDemo(guardada);
    setChatInicial(guardada.chat);
    setEtapa('cargando');
  }, []);

  const empresa = demo?.empresa || '';
  const whatsappDemo = useMemo(() => enlaceWhatsapp(empresa, DEMO_UI.agendar), [empresa]);
  // Tope (429) o error al armar el bot: la persona no alcanzó a probar la demo,
  // así que el texto prellenado no dice «acabo de probar».
  const whatsappSinDemo = useMemo(() => enlaceWhatsapp(null, DEMO_UI.agendar), []);

  // ------------------------------------------------------------------
  // «Agendar una llamada» (Cal.com) y «Hablar con un asesor» (#625, #634)
  // ------------------------------------------------------------------
  const [calAbierto, setCalAbierto] = useState(false);
  // A quién se le suman los clics: solo a una demo con token que siga viva.
  // Tras un 404 el token ya no sirve (el backend respondería 404 igual).
  const demoEventos =
    demo && etapa !== 'no_disponible' && !noDisponibleEnChat ? { id: demo.id, token: demo.token } : null;
  const demoEventosRef = useRef(demoEventos);
  demoEventosRef.current = demoEventos;

  const acciones = useCallback(
    (enlace: string): AccionesAgendar => ({
      abrirLlamada: () => {
        setCalAbierto(true);
        registrarEvento(demoEventosRef.current, 'llamada_abierta');
      },
      enlaceWhatsapp: enlace,
      alClicWhatsapp: () => registrarEvento(demoEventosRef.current, 'whatsapp'),
    }),
    [],
  );
  const accionesDemo = useMemo(() => acciones(whatsappDemo), [acciones, whatsappDemo]);
  const accionesSinDemo = useMemo(() => acciones(whatsappSinDemo), [acciones, whatsappSinDemo]);
  const alAgendarLlamada = useCallback(() => registrarEvento(demoEventosRef.current, 'llamada_agendada'), []);

  // ------------------------------------------------------------------
  // POST /demo/iniciar
  // ------------------------------------------------------------------
  const iniciar = useCallback(
    async (datos: DatosFormulario) => {
      if (enviando) return;
      ultimosDatos.current = datos;
      setAlerta(null);
      setCamposRechazados([]);
      if (TURNSTILE_ACTIVO && !turnstileToken) {
        setAlerta('verificacion');
        if (etapaRef.current === 'slides') setEtapa('formulario');
        return;
      }

      const cuerpo: DatosIniciar = {
        nombre: datos.nombre.trim(),
        empresa: datos.empresa.trim(),
        // E.164 (`+573001234567`); el formulario ya lo validó.
        telefono: telefonoE164(datos) ?? datos.telefono.trim(),
        correo: datos.correo.trim(),
        tipo_empresa: datos.tipo_empresa,
        acepta_contacto: true,
        acepta_promociones: datos.acepta_promociones,
        sitio_web: datos.sitio_web,
        form_ms: 0, // se mide justo antes del POST
      };
      if (datos.tipo_empresa === TIPO_OTRO.clave && datos.tipo_otro.trim()) {
        cuerpo.tipo_otro = datos.tipo_otro.trim();
      }
      if (TURNSTILE_ACTIVO && turnstileToken) cuerpo.turnstile_token = turnstileToken;

      setEnviando(true);
      try {
        const falta = LLENADO_MINIMO_MS - (Date.now() - formAbiertoMs.current);
        if (falta > 0) await new Promise((r) => setTimeout(r, falta));
        cuerpo.form_ms = Math.max(0, Date.now() - formAbiertoMs.current);
        const out = await iniciarDemo(cuerpo);
        const nueva: DemoGuardada = {
          v: 1,
          id: out.demo_id,
          token: out.token,
          nombre: primerNombre(datos.nombre),
          empresa: cuerpo.empresa,
          creadoMs: Date.now(),
          etapa: 'slides',
        };
        guardarDemo(nueva);
        setDemo(nueva);
        setGen(GEN_INICIAL);
        setLento(false);
        setReconectando(false);
        setAnimarListo(false);
        setChatInicial(undefined);
        setNoDisponibleEnChat(false);
        // La pantalla de premio sale solo desde el formulario; un reintento
        // desde las slides (error al armar el bot) vuelve directo a ellas.
        if (etapaRef.current === 'formulario') {
          const e164 = cuerpo.telefono;
          setPremio({
            correo: cuerpo.correo,
            telefono: formatearE164(e164, datos.telefono_pais, datos.telefono_indicativo),
            colombia: esTelefonoColombia(e164),
          });
          setEtapa('premio');
        } else {
          setEtapa('slides');
        }
      } catch (e) {
        const status = e instanceof DemoApiError ? e.status : 0;
        if (status === 429) setAlerta('tope');
        else if (status === 422) {
          const campos = e instanceof DemoApiError ? e.campos : [];
          setCamposRechazados(campos);
          if (campos.length === 0) setAlerta('red');
        } else if (TURNSTILE_ACTIVO && (status === 400 || status === 403)) setAlerta('verificacion');
        else setAlerta('red');
        // Un reintento fallido desde las slides vuelve al formulario, donde
        // están el aviso y los datos.
        if (etapaRef.current === 'slides') setEtapa('formulario');
      } finally {
        setEnviando(false);
        // Los tokens de Turnstile son de un solo uso.
        if (TURNSTILE_ACTIVO) setTurnstileReinicio((n) => n + 1);
      }
    },
    [enviando, turnstileToken],
  );

  // ------------------------------------------------------------------
  // Sondeo de GET /demo/{id}/estado
  // ------------------------------------------------------------------
  const consultando =
    demo !== null && gen.estado === 'generando' && (etapa === 'cargando' || etapa === 'premio' || etapa === 'slides');

  useEffect(() => {
    if (!consultando || !demo) return;
    let cancelado = false;
    let timer: number | undefined;
    let fallos = 0;

    const marcarNoDisponible = () => {
      borrarDemo();
      setEtapa('no_disponible');
    };

    const tick = async () => {
      const transcurrido = Date.now() - demo.creadoMs;
      try {
        const r = await consultarEstado(demo.id, demo.token);
        if (cancelado) return;
        fallos = 0;
        setReconectando(false);
        if (r.estado === 'lista') {
          setGen({ estado: 'lista', productos: r.productos.slice(0, 3), mensajeSugerido: r.mensaje_sugerido || '' });
          if (etapaRef.current === 'slides') setAnimarListo(true);
          if (etapaRef.current === 'cargando') {
            setEtapa(demo.etapa === 'chat' ? 'chat' : 'slides');
          }
          return;
        }
        if (r.estado === 'error') {
          setGen((g) => ({ ...g, estado: 'error' }));
          if (etapaRef.current === 'cargando') setEtapa('slides');
          return;
        }
        if (etapaRef.current === 'cargando') setEtapa('slides');
      } catch (e) {
        if (cancelado) return;
        if (e instanceof DemoApiError && e.status === 404) {
          marcarNoDisponible();
          return;
        }
        fallos += 1;
        if (fallos >= 3) setReconectando(true);
      }
      if (transcurrido >= CORTE_MS) {
        // A los 90 s se trata como error y se deja de consultar.
        setGen((g) => ({ ...g, estado: 'error' }));
        if (etapaRef.current === 'cargando') setEtapa('slides');
        return;
      }
      setLento(transcurrido >= AVISO_DEMORA_MS);
      const espera = fallos >= 3 ? Math.min(SONDEO_MS * 2 ** (fallos - 2), 10000) : SONDEO_MS;
      timer = window.setTimeout(tick, espera);
    };

    void tick();
    return () => {
      cancelado = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [consultando, demo]);

  // ------------------------------------------------------------------
  // Transiciones
  // ------------------------------------------------------------------
  const entrarAlChat = useCallback(() => {
    const d = demoRef.current;
    if (!d) return;
    const actualizada: DemoGuardada = { ...d, etapa: 'chat' };
    guardarDemo(actualizada);
    setDemo(actualizada);
    setEtapa('chat');
  }, []);

  const persistirChat = useCallback((chat: ChatGuardado) => {
    const d = demoRef.current;
    if (!d) return;
    guardarDemo({ ...d, etapa: 'chat', chat });
  }, []);

  const nuevaDemo = useCallback(() => {
    borrarDemo();
    setDemo(null);
    setGen(GEN_INICIAL);
    setLento(false);
    setReconectando(false);
    setAnimarListo(false);
    setChatInicial(undefined);
    setNoDisponibleEnChat(false);
    setAlerta(null);
    setCamposRechazados([]);
    formAbiertoMs.current = Date.now();
    setEtapa('formulario');
    window.scrollTo(0, 0);
  }, []);

  const reintentar = useCallback(() => {
    if (ultimosDatos.current) void iniciar(ultimosDatos.current);
    else nuevaDemo(); // tras una recarga no tenemos los datos del formulario
  }, [iniciar, nuevaDemo]);

  const chatNoDisponible = useCallback(() => {
    borrarDemo();
    setNoDisponibleEnChat(true);
  }, []);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  const conFormulario = etapa === 'formulario' || etapa === 'premio' || etapa === 'slides';

  return (
    <>
      <Head>
        <title>Prueba tu agente de IA · Gloma</title>
        <meta
          name="description"
          content="Arma en un minuto un agente de IA de ejemplo para tu empresa de turismo y escríbele como si fueras un cliente."
        />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <meta name="theme-color" content="#101817" />
      </Head>

      <style jsx global>{`
        html,
        body {
          background-color: #101817;
        }
        .demo-root {
          font-family: 'Inter', system-ui, sans-serif;
          -webkit-font-smoothing: antialiased;
        }
        .demo-root h1,
        .demo-root h2,
        .demo-root h3 {
          font-family: 'Syne', system-ui, sans-serif;
        }
        .demo-root :focus-visible {
          outline: 2px solid #4db6ac;
          outline-offset: 2px;
        }
        /* Títulos que reciben el foco por código (slides, «no disponible»): sin anillo. */
        .demo-root [tabindex='-1']:focus-visible {
          outline: none;
        }
        .demo-root ::selection {
          background: #4db6ac;
          color: #101817;
        }
        .demo-btn-primario {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          min-height: 48px;
          padding: 0 24px;
          border-radius: 9999px;
          background: #4db6ac;
          color: #101817;
          font-weight: 600;
          font-size: 15px;
          transition: opacity 0.15s;
        }
        .demo-btn-primario:hover {
          opacity: 0.92;
        }
        .demo-btn-primario[disabled] {
          opacity: 0.8;
          cursor: progress;
        }
        .demo-btn-primario.demo-btn-espera,
        .demo-btn-primario[aria-disabled='true'] {
          background: rgba(255, 255, 255, 0.1);
          color: #c9d3d1;
          cursor: not-allowed;
          opacity: 1;
        }
        .demo-select {
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%234DB6AC' stroke-width='2' stroke-linecap='round'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E");
          background-repeat: no-repeat;
          background-position: right 14px center;
        }
        .demo-select option {
          color: #e6efee;
          background: #0b1413;
        }
        .demo-spin {
          width: 16px;
          height: 16px;
          border-radius: 9999px;
          border: 2px solid currentColor;
          border-right-color: transparent;
          display: inline-block;
          animation: demoGirar 0.8s linear infinite;
          flex-shrink: 0;
        }
        @keyframes demoGirar {
          to {
            transform: rotate(360deg);
          }
        }
        .demo-barra {
          height: 3px;
          background: rgba(77, 182, 172, 0.18);
          border-radius: 9999px;
          overflow: hidden;
          position: relative;
        }
        .demo-barra::after {
          content: '';
          position: absolute;
          top: 0;
          bottom: 0;
          left: 0;
          width: 35%;
          background: #4db6ac;
          border-radius: 9999px;
          animation: demoBarrido 1.6s ease-in-out infinite;
        }
        @keyframes demoBarrido {
          0% {
            left: -35%;
          }
          100% {
            left: 100%;
          }
        }
        .demo-esqueleto {
          display: inline-block;
          background: linear-gradient(90deg, rgba(255, 255, 255, 0.05) 0, rgba(77, 182, 172, 0.18) 40px, rgba(255, 255, 255, 0.05) 80px);
          background-size: 400px 100%;
          animation: demoBrillo 1.4s linear infinite;
        }
        @keyframes demoBrillo {
          0% {
            background-position: -200px 0;
          }
          100% {
            background-position: 200px 0;
          }
        }
        .demo-pulso {
          animation: demoPulso 2s ease-out infinite;
        }
        .demo-pulso-1 {
          animation: demoPulso 1.6s ease-out 2;
        }
        @keyframes demoPulso {
          0% {
            box-shadow: 0 0 0 0 rgba(77, 182, 172, 0.6);
          }
          70% {
            box-shadow: 0 0 0 14px rgba(77, 182, 172, 0);
          }
          100% {
            box-shadow: 0 0 0 0 rgba(77, 182, 172, 0);
          }
        }
        .demo-entra {
          animation: demoEntra 0.28s cubic-bezier(0.22, 0.61, 0.36, 1) both;
        }
        @keyframes demoEntra {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: none;
          }
        }
        .demo-pista {
          transition: transform 0.38s cubic-bezier(0.22, 0.61, 0.36, 1);
        }
        .demo-punto {
          width: 8px;
          height: 8px;
          border-radius: 9999px;
          background: rgba(230, 239, 238, 0.35);
          transition: width 0.2s, background 0.2s;
        }
        .demo-punto-activo {
          width: 24px;
          background: #4db6ac;
        }
        .demo-tecleo span {
          width: 7px;
          height: 7px;
          border-radius: 9999px;
          background: #a3afad;
          display: inline-block;
          animation: demoTecleo 1.2s ease-in-out infinite;
        }
        .demo-tecleo span:nth-child(2) {
          animation-delay: 0.18s;
        }
        .demo-tecleo span:nth-child(3) {
          animation-delay: 0.36s;
        }
        @keyframes demoTecleo {
          0%,
          60%,
          100% {
            opacity: 0.25;
            transform: none;
          }
          30% {
            opacity: 1;
            transform: translateY(-3px);
          }
        }
        .demo-fondo-chat {
          background-color: #0b1413;
          background-image: radial-gradient(rgba(77, 182, 172, 0.07) 1px, transparent 1px);
          background-size: 18px 18px;
        }
        .demo-b-in {
          background: #1a2725;
          color: #e6efee;
          border-radius: 4px 14px 14px 14px;
        }
        .demo-b-out {
          background: #004d40;
          color: #ffffff;
          border-radius: 14px 4px 14px 14px;
        }
        .demo-b-meta {
          font-size: 11px;
          color: rgba(230, 239, 238, 0.68);
          display: inline-flex;
          align-items: center;
          gap: 3px;
          float: right;
          margin: 6px 0 -4px 10px;
          white-space: nowrap;
        }
        .demo-chip-sis {
          background: #1a2725;
          color: #c9d3d1;
          border: 1px solid rgba(77, 182, 172, 0.22);
        }
        @media (prefers-reduced-motion: reduce) {
          .demo-pista,
          .demo-entra,
          .demo-pulso,
          .demo-pulso-1,
          .demo-esqueleto,
          .demo-barra::after,
          .demo-tecleo span {
            animation: none !important;
            transition: none !important;
          }
          .demo-spin {
            animation-duration: 2.4s;
          }
        }
      `}</style>

      <div className="demo-root min-h-[100dvh] text-gloma-ink-text" style={{ background: FONDO }}>
        {conFormulario && (
          <div className="relative min-h-[100dvh] overflow-hidden" inert={etapa !== 'formulario'} aria-hidden={etapa !== 'formulario' ? true : undefined}>
            {/* La ventanilla del logo en contorno, como el hero de gloma.tsx. */}
            <svg
              className="absolute inset-0 w-full h-full pointer-events-none"
              aria-hidden="true"
              viewBox="0 0 100 60"
              preserveAspectRatio="xMaxYMid slice"
            >
              <rect x="66" y="-4" width="40" height="68" rx="20" fill="none" stroke="#4DB6AC" strokeOpacity="0.22" strokeWidth="0.45" />
              <rect x="70" y="2" width="32" height="56" rx="16" fill="none" stroke="#4DB6AC" strokeOpacity="0.12" strokeWidth="0.38" />
            </svg>

            <nav className="relative max-w-6xl mx-auto px-4 md:px-10 pt-4 md:pt-6 flex items-center justify-between">
              <a href="https://glomacx.com/" aria-label="Gloma, ir al inicio">
                <Image
                  src="/gloma/logo_blancotrans.png"
                  alt="Gloma"
                  width={320}
                  height={192}
                  priority
                  className="h-14 md:h-20 w-auto object-contain"
                />
              </a>
              <a href="https://glomacx.com/" className="text-sm text-white/85 hover:text-white underline-offset-4 hover:underline min-h-[44px] inline-flex items-center">
                {DEMO_UI.nav.conocer}
              </a>
            </nav>

            <main className="relative max-w-6xl mx-auto px-4 md:px-10 pt-2 pb-10 md:py-12 grid md:grid-cols-[1fr_440px] gap-6 md:gap-14 items-start">
              <DemoIntro />
              <DemoForm
                onIniciar={iniciar}
                enviando={enviando}
                alerta={alerta}
                camposRechazados={camposRechazados}
                acciones={accionesSinDemo}
                inicial={ultimosDatos.current}
                turnstile={<Turnstile onToken={setTurnstileToken} reinicio={turnstileReinicio} />}
              />
            </main>
          </div>
        )}

        {etapa === 'premio' && demo && premio && (
          <DemoPremio
            nombre={demo.nombre}
            correo={premio.correo}
            telefono={premio.telefono}
            colombia={premio.colombia}
            onContinuar={() => setEtapa('slides')}
          />
        )}

        {etapa === 'slides' && demo && (
          <DemoSlides
            nombre={demo.nombre}
            empresa={demo.empresa}
            estado={gen.estado}
            lento={lento}
            reconectando={reconectando}
            productos={gen.productos}
            animarListo={animarListo}
            onProbar={entrarAlChat}
            onReintentar={reintentar}
            reintentando={enviando}
            acciones={accionesSinDemo}
          />
        )}

        {etapa === 'cargando' && (
          <div className="min-h-[100dvh] flex flex-col items-center justify-center gap-3 text-sm text-gloma-ink-muted" role="status">
            <span className="demo-spin text-gloma-mint" aria-hidden="true" />
            {DEMO_UI.cargando}
          </div>
        )}

        {etapa === 'chat' && demo && (
          <div className="h-[100dvh]">
            <DemoChat
              demoId={demo.id}
              token={demo.token}
              empresa={demo.empresa}
              productos={gen.productos}
              mensajeSugerido={gen.mensajeSugerido}
              inicial={chatInicial}
              onPersistir={persistirChat}
              noDisponible={noDisponibleEnChat}
              onNoDisponible={chatNoDisponible}
              onNuevaDemo={nuevaDemo}
              acciones={accionesDemo}
            />
          </div>
        )}

        {etapa === 'no_disponible' && (
          <div className="min-h-[100dvh] flex items-center justify-center px-4">
            <DemoNoDisponible onNuevaDemo={nuevaDemo} acciones={accionesDemo} />
          </div>
        )}

        {/* Nombre y correo para prellenar Cal: solo de la memoria de React (lo
            que se escribió en esta carga de la página), nunca de sessionStorage. */}
        <AgendarLlamadaModal
          abierto={calAbierto}
          onCerrar={() => setCalAbierto(false)}
          nombre={ultimosDatos.current?.nombre}
          correo={ultimosDatos.current?.correo}
          onAgendada={alAgendarLlamada}
        />
      </div>
    </>
  );
}
