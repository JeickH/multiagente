import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';

type BotStep = {
  id: number;
  position: number;
  step_type: string;
  label: string;
  config: Record<string, any> | null;
  next_step_id: number | null;
};

type BotDetail = {
  id: number;
  name: string;
  description?: string | null;
  status: string;
  channels: string[];
  engine?: 'flow' | 'llm';
  trigger_type: 'default' | 'keyword' | 'manual';
  trigger_config: Record<string, any> | null;
  triggered_count: number;
  completed_steps_count: number;
  finished_count: number;
  created_at: string;
  updated_at: string;
  steps: BotStep[];
};

type BotAction = {
  type: 'say' | 'say_media' | 'say_catalog' | 'ask' | 'pause' | 'end' | 'handoff';
  payload: Record<string, any>;
};

type SimulateResponse = {
  actions: BotAction[];
  // Estado opaco del motor: bots de flujo guardan {current_step_id, variables};
  // bots LLM (Sprint 19) guardan {history}. El cliente solo lo devuelve tal cual.
  next_state: Record<string, any> | null;
  finished: boolean;
  // Camino que tomó la IA en este turno (solo bots LLM) — se muestra como chip.
  camino?: string | null;
};

type ChatBubble =
  | { role: 'bot'; kind: 'text'; text: string; time: string }
  | { role: 'bot'; kind: 'media'; caption: string; media_type: string; url: string; time: string }
  | { role: 'bot'; kind: 'ask'; prompt: string; options: string[]; time: string }
  | { role: 'bot'; kind: 'pause'; seconds: number; time: string }
  | { role: 'bot'; kind: 'end'; text: string; time: string }
  | { role: 'bot'; kind: 'handoff'; assignee: string; text: string; time: string }
  | { role: 'bot'; kind: 'camino'; camino: string; time: string }
  | { role: 'bot'; kind: 'catalog'; titulo: string; cuerpo: string; time: string }
  | { role: 'user'; text: string; time: string };

const nowHHMM = (): string =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

// Renderiza el markdown de WhatsApp: *negrita*, _cursiva_, ~tachado~.
// Mantiene los saltos de línea (el contenedor usa whitespace-pre-wrap).
function formatWa(text: string): ReactNode[] {
  if (!text) return [text];
  const parts: ReactNode[] = [];
  const regex = /(\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    const inner = tok.slice(1, -1);
    if (tok[0] === '*') parts.push(<strong key={key++}>{inner}</strong>);
    else if (tok[0] === '_') parts.push(<em key={key++}>{inner}</em>);
    else parts.push(<s key={key++}>{inner}</s>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

const NODE_W = 260;
const NODE_H = 200;
const GAP_X = 80;
const PAD_X = 60;
const PAD_Y = 120;

// #265: cada tipo de bloque tiene un fondo pastel propio para resaltar del
// fondo blanco del lienzo (pedido CEO).
const STEP_STYLE: Record<string, { accent: string; icon: string; badge: string; bg: string }> = {
  send_text:    { accent: 'border-blue-400',   icon: '💬', badge: 'bg-blue-100 text-blue-700',       bg: 'bg-blue-50' },
  send_template:{ accent: 'border-indigo-400', icon: '📋', badge: 'bg-indigo-100 text-indigo-700',   bg: 'bg-indigo-50' },
  send_media:   { accent: 'border-purple-400', icon: '🖼️', badge: 'bg-purple-100 text-purple-700',   bg: 'bg-purple-50' },
  wait_input:   { accent: 'border-amber-400',  icon: '⌨️', badge: 'bg-amber-100 text-amber-700',     bg: 'bg-amber-50' },
  llm:          { accent: 'border-fuchsia-400',icon: '🤖', badge: 'bg-fuchsia-100 text-fuchsia-700', bg: 'bg-fuchsia-50' },
  delay:        { accent: 'border-slate-400',  icon: '⏱️', badge: 'bg-slate-200 text-slate-700',     bg: 'bg-slate-50' },
  condition:    { accent: 'border-orange-400', icon: '🔀', badge: 'bg-orange-100 text-orange-700',   bg: 'bg-orange-50' },
  handoff:      { accent: 'border-emerald-400',icon: '👤', badge: 'bg-emerald-100 text-emerald-700', bg: 'bg-emerald-50' },
  end:          { accent: 'border-rose-400',   icon: '🏁', badge: 'bg-rose-100 text-rose-700',       bg: 'bg-rose-50' },
};

function StepNode({ step, isFirst }: { step: BotStep; isFirst: boolean }) {
  const style = STEP_STYLE[step.step_type] || STEP_STYLE.send_text;
  const cfg = step.config || {};
  const renderBody = () => {
    switch (step.step_type) {
      case 'send_text':
      case 'end':
        return <p className="text-sm text-gray-700">{cfg.text || '—'}</p>;
      case 'send_media': {
        const items: any[] = Array.isArray(cfg.items) && cfg.items.length
          ? cfg.items
          : [{ media_type: cfg.media_type, url: cfg.url, caption: cfg.caption }];
        return (
          <div>
            <div className="flex gap-1 mb-2">
              {items.slice(0, 3).map((it: any, idx: number) =>
                it.url ? (
                  it.media_type === 'video' ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <div key={idx} className="flex-1 bg-black rounded h-20 flex items-center justify-center text-white text-2xl">
                      ▶︎
                    </div>
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img key={idx} src={it.url} alt="" className="flex-1 rounded h-20 object-cover min-w-0" />
                  )
                ) : (
                  <div key={idx} className="flex-1 bg-gray-100 rounded h-20 flex items-center justify-center text-gray-400 text-3xl">
                    {it.media_type === 'image' ? '🖼️' : '📎'}
                  </div>
                )
              )}
            </div>
            <p className="text-xs text-gray-600 line-clamp-2">{cfg.caption || items[0]?.caption || '—'}</p>
          </div>
        );
      }
      case 'wait_input':
        return (
          <div>
            <p className="text-sm text-gray-700 mb-2">{cfg.prompt || '—'}</p>
            {Array.isArray(cfg.options) && (
              <ul className="space-y-1">
                {cfg.options.slice(0, 3).map((opt: string, i: number) => (
                  <li key={i} className="text-xs bg-gray-100 rounded px-2 py-1 text-gray-600">
                    {opt}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      case 'condition':
        return (
          <div>
            <p className="text-sm text-gray-700 mb-2">{cfg.prompt || '—'}</p>
            {cfg.branches && (
              <div className="flex flex-wrap gap-1">
                {Object.entries(cfg.branches as Record<string, string>).map(([k, v]) => (
                  <span key={k} className="text-[10px] bg-orange-50 text-orange-700 rounded px-2 py-0.5">
                    {k}: {v}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      case 'llm': {
        const isExtract = cfg.mode === 'extract';
        // Sprint 19 #256: bloque de ACCIÓN LLM — el mensaje al cliente lo
        // redacta la IA; la información sale de la fuente integrada indicada.
        if (cfg.mode === 'accion') {
          // Feedback CEO #256: el bloque muestra el MENSAJE base (copy real,
          // como los bloques de siempre); la IA lo adapta al conversar.
          return (
            <div>
              <p className="text-sm text-gray-700">{cfg.mensaje || cfg.descripcion || '—'}</p>
              <div className="flex flex-wrap gap-1 mt-1">
                <span className="inline-block text-[10px] bg-fuchsia-50 text-fuchsia-700 rounded px-2 py-0.5">
                  ✨ la IA adapta este mensaje
                </span>
                {cfg.fuente && (
                  <span className="inline-block text-[10px] bg-indigo-50 text-indigo-700 rounded px-2 py-0.5">
                    fuente: {cfg.fuente}
                  </span>
                )}
              </div>
            </div>
          );
        }
        return (
          <div>
            <span className="inline-block text-[10px] bg-fuchsia-50 text-fuchsia-700 rounded px-2 py-0.5 mb-1">
              {isExtract ? `extrae → {${cfg.variable || 'valor'}}` : 'interpreta y enruta'}
            </span>
            <p className="text-sm text-gray-700">
              {isExtract
                ? 'Extrae un dato del mensaje del cliente con IA.'
                : 'Lee el mensaje del cliente y decide la mejor respuesta.'}
            </p>
            {!isExtract && Array.isArray(cfg.intents) && (
              <div className="flex flex-wrap gap-1 mt-1">
                {cfg.intents.slice(0, 6).map((it: any, idx: number) => (
                  <span key={idx} className="text-[10px] bg-fuchsia-50 text-fuchsia-700 rounded px-2 py-0.5">
                    {(it.keywords && it.keywords[0]) || 'intent'}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      }
      case 'handoff':
        return (
          <div>
            <p className="text-sm text-gray-700 mb-1">
              Pasa el chat a <span className="font-semibold">{cfg.assignee || 'asesor_1'}</span>.
            </p>
            {cfg.text && <p className="text-xs text-gray-500 line-clamp-2">"{cfg.text}"</p>}
          </div>
        );
      case 'delay':
        return (
          <p className="text-sm text-gray-700">
            Esperar <span className="font-mono font-semibold">{cfg.seconds ?? '?'}s</span>
          </p>
        );
      case 'send_template':
        return (
          <p className="text-sm text-gray-700">
            Plantilla: <span className="font-mono">{cfg.template_name || '—'}</span>
          </p>
        );
      default:
        return <p className="text-sm text-gray-500">Bloque sin vista previa</p>;
    }
  };

  return (
    <div
      className={`absolute ${style.bg} rounded-xl border-t-4 ${style.accent} border border-gray-200 shadow-sm p-4 flex flex-col`}
      style={{ width: NODE_W, minHeight: NODE_H }}
    >
      {isFirst && (
        <div className="absolute -top-7 left-1/2 -translate-x-1/2 bg-gray-800 text-white text-[11px] font-medium px-2 py-0.5 rounded">
          Paso inicial
        </div>
      )}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center justify-center w-7 h-7 rounded ${style.badge}`}>
            <span className="text-sm">{style.icon}</span>
          </span>
          <div>
            <div className="text-[11px] text-gray-400 uppercase tracking-wide">
              {step.step_type.replace('_', ' ')}
            </div>
            <div className="text-sm font-semibold text-gray-800">{step.label}</div>
          </div>
        </div>
        <span className="text-gray-300 text-lg leading-none">⋮</span>
      </div>
      <div className="flex-1 overflow-hidden">{renderBody()}</div>
    </div>
  );
}

function SimulatorModal({
  botId,
  botName,
  onClose,
}: {
  botId: number;
  botName: string;
  onClose: () => void;
}) {
  const [bubbles, setBubbles] = useState<ChatBubble[]>([]);
  const [state, setState] = useState<SimulateResponse['next_state']>(null);
  const [finished, setFinished] = useState(false);
  const [waitingInput, setWaitingInput] = useState(false);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [typing, setTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const getToken = () =>
    typeof window !== 'undefined' ? localStorage.getItem('token') : null;

  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  // Delay base entre mensajes del bot (simula "escribiendo…"). Se hace
  // proporcional al largo del texto para que mensajes cortos no esperen
  // demasiado y mensajes largos se sientan naturales.
  const typingDelayFor = (action: BotAction): number => {
    const text =
      action.type === 'say'
        ? String(action.payload.text || '')
        : action.type === 'say_media'
        ? String(action.payload.caption || '')
        : action.type === 'ask'
        ? String(action.payload.prompt || '')
        : '';
    const base = 600;
    const perChar = 18;
    return Math.min(base + text.length * perChar, 2200);
  };

  const actionToBubble = (a: BotAction): ChatBubble => {
    const time = nowHHMM();
    if (a.type === 'say') return { role: 'bot', kind: 'text', text: a.payload.text || '', time };
    if (a.type === 'say_media')
      return {
        role: 'bot',
        kind: 'media',
        caption: a.payload.caption || '',
        media_type: a.payload.media_type || 'image',
        url: a.payload.url || '',
        time,
      };
    if (a.type === 'say_catalog')
      return {
        role: 'bot',
        kind: 'catalog',
        titulo: a.payload.titulo || 'Catálogo',
        cuerpo: a.payload.cuerpo || '',
        time,
      };
    if (a.type === 'ask')
      return {
        role: 'bot',
        kind: 'ask',
        prompt: a.payload.prompt || '',
        options: a.payload.options || [],
        time,
      };
    if (a.type === 'pause')
      return { role: 'bot', kind: 'pause', seconds: a.payload.seconds || 0, time };
    if (a.type === 'handoff')
      return {
        role: 'bot',
        kind: 'handoff',
        assignee: a.payload.assignee || 'asesor_1',
        text: a.payload.text || '',
        time,
      };
    return { role: 'bot', kind: 'end', text: a.payload.text || '', time };
  };

  const renderActionsProgressively = async (actions: BotAction[]) => {
    for (const action of actions) {
      if (action.type === 'pause') {
        // Respeta el delay del bot, capeado a 5s para que la simulación
        // no se sienta congelada.
        const secs = Number(action.payload.seconds) || 0;
        setBubbles((prev) => [...prev, actionToBubble(action)]);
        const wait = Math.min(secs * 1000, 5000);
        if (wait > 0) await sleep(wait);
        continue;
      }
      // Muestra indicador "escribiendo…" antes de cada burbuja del bot
      setTyping(true);
      await sleep(typingDelayFor(action));
      setTyping(false);
      setBubbles((prev) => [...prev, actionToBubble(action)]);
      // Pequeña respiración entre burbujas consecutivas
      await sleep(180);
    }
  };

  const turn = async (userInput: string | null) => {
    const token = getToken();
    if (!token) return;
    setSending(true);
    try {
      const res = await fetch(`/api/bots/${botId}/simulate`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ state, user_input: userInput }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: SimulateResponse = await res.json();
      setState(data.next_state);
      await renderActionsProgressively(data.actions);
      if (data.camino) {
        setBubbles((prev) => [
          ...prev,
          { role: 'bot', kind: 'camino', camino: data.camino!, time: nowHHMM() },
        ]);
      }
      setFinished(data.finished);
      // Regla del CEO: entre bloque y bloque siempre se espera respuesta del
      // usuario. Habilitamos el input mientras el bot no haya terminado, sin
      // depender de que la última acción sea 'ask'.
      setWaitingInput(!data.finished);
    } catch (err: any) {
      setBubbles((prev) => [
        ...prev,
        { role: 'bot', kind: 'text', text: `⚠️ Error en simulación: ${err.message}`, time: nowHHMM() },
      ]);
    } finally {
      setTyping(false);
      setSending(false);
    }
  };

  // Arranque: primer turno sin input
  useEffect(() => {
    turn(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [bubbles]);

  const sendValue = async (raw: string) => {
    const value = raw.trim();
    if (!value || sending || typing) return;
    setBubbles((prev) => [...prev, { role: 'user', text: value, time: nowHHMM() }]);
    setInput('');
    setWaitingInput(false);
    await turn(value);
  };

  const handleSend = () => sendValue(input);

  const handleReset = () => {
    setBubbles([]);
    setState(null);
    setFinished(false);
    setWaitingInput(false);
    setTyping(false);
    setInput('');
    // Disparar primer turno
    setTimeout(() => turn(null), 0);
  };

  // Wallpaper SVG de WhatsApp (doodle pattern, beige clásico)
  const waWallpaper =
    'url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22120%22 height=%22120%22 viewBox=%220 0 120 120%22%3E%3Cg fill=%22%23d4c8b8%22 fill-opacity=%220.4%22%3E%3Cpath d=%22M20 20h6v6h-6zm12 12h6v6h-6zm-30 30h6v6H2zm60 0h6v6h-6zm30 30h6v6h-6zm-15-60h6v6h-6zm-45 90h6v6h-6zm75 0h6v6h-6z%22/%3E%3Ccircle cx=%2280%22 cy=%2225%22 r=%223%22/%3E%3Ccircle cx=%2225%22 cy=%2275%22 r=%223%22/%3E%3Ccircle cx=%22100%22 cy=%2295%22 r=%223%22/%3E%3C/g%3E%3C/svg%3E")';

  const Tick = () => (
    <svg viewBox="0 0 16 11" className="w-4 h-3 inline-block fill-current">
      <path d="M11.071 0.653a.5.5 0 0 0-.707.024l-5.04 5.43-2.33-2.33a.5.5 0 1 0-.707.707l2.694 2.694a.5.5 0 0 0 .72-.013l5.397-5.815a.5.5 0 0 0-.027-.697zm4 0a.5.5 0 0 0-.707.024l-5.04 5.43-.93-.93a.5.5 0 1 0-.707.707l1.294 1.294a.5.5 0 0 0 .72-.013l5.397-5.815a.5.5 0 0 0-.027-.697z" />
    </svg>
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      {/* Frame de celular */}
      <div
        className="relative bg-black rounded-[2.5rem] shadow-2xl p-3"
        onClick={(e) => e.stopPropagation()}
        style={{ width: '380px', height: '720px' }}
      >
        {/* Notch */}
        <div className="absolute top-3 left-1/2 -translate-x-1/2 w-32 h-6 bg-black rounded-b-2xl z-20" />
        {/* Botones laterales decorativos */}
        <div className="absolute -left-1 top-24 w-1 h-16 bg-gray-800 rounded-l" />
        <div className="absolute -left-1 top-44 w-1 h-10 bg-gray-800 rounded-l" />
        <div className="absolute -right-1 top-32 w-1 h-20 bg-gray-800 rounded-r" />

        {/* Pantalla */}
        <div className="relative w-full h-full rounded-[2rem] overflow-hidden flex flex-col bg-white">
          {/* Status bar simulada */}
          <div className="h-8 bg-[#075E54] flex items-center justify-between px-6 pt-1 text-white text-[11px] font-medium">
            <span>{nowHHMM()}</span>
            <div className="flex items-center gap-1">
              <span>●●●●</span>
              <span>📶</span>
              <span>🔋</span>
            </div>
          </div>

          {/* Header WhatsApp */}
          <div className="bg-[#075E54] text-white px-3 py-2 flex items-center justify-between shadow-md">
            <div className="flex items-center gap-3 min-w-0">
              <button
                type="button"
                onClick={onClose}
                className="text-white/90 hover:text-white text-lg leading-none px-1"
                title="Cerrar"
              >
                ←
              </button>
              <div className="w-9 h-9 rounded-full bg-gloma-rose-soft text-gloma-brown flex items-center justify-center text-base shrink-0">
                🤖
              </div>
              <div className="min-w-0">
                <div className="font-semibold text-sm leading-tight truncate">{botName}</div>
                <div className="text-[11px] text-white/80 leading-tight">
                  {sending || typing ? 'escribiendo…' : 'en línea'}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 text-white/90">
              <button
                type="button"
                onClick={handleReset}
                className="hover:text-white text-base"
                title="Reiniciar conversación"
              >
                ↻
              </button>
              <span className="text-base" title="Videollamada">📹</span>
              <span className="text-base" title="Llamada">📞</span>
            </div>
          </div>

          {/* Banner de simulación */}
          <div className="bg-yellow-50 border-b border-yellow-200 px-3 py-1 text-[10px] text-yellow-800 text-center">
            Simulación — no se envían mensajes reales
          </div>

          {/* Chat body */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto px-3 py-3 space-y-1.5"
            style={{
              backgroundImage: waWallpaper,
              backgroundColor: '#ECE5DD',
            }}
          >
            {bubbles.map((b, i) => {
              if (b.role === 'user') {
                return (
                  <div key={i} className="flex justify-end">
                    <div className="relative bg-[#DCF8C6] text-gray-800 rounded-lg rounded-tr-none px-2 py-1 max-w-[78%] text-sm shadow-sm">
                      <div className="whitespace-pre-wrap break-words pr-12">{b.text}</div>
                      <div className="absolute bottom-1 right-2 flex items-center gap-0.5 text-[10px] text-gray-500">
                        <span>{b.time}</span>
                        <span className="text-[#34B7F1]">
                          <Tick />
                        </span>
                      </div>
                    </div>
                  </div>
                );
              }
              if (b.kind === 'text') {
                return (
                  <div key={i} className="flex justify-start">
                    <div className="relative bg-white text-gray-800 rounded-lg rounded-tl-none px-2 py-1 max-w-[78%] text-sm shadow-sm">
                      <div className="whitespace-pre-wrap break-words pr-10">{formatWa(b.text)}</div>
                      <div className="absolute bottom-1 right-2 text-[10px] text-gray-400">
                        {b.time}
                      </div>
                    </div>
                  </div>
                );
              }
              if (b.kind === 'media') {
                return (
                  <div key={i} className="flex justify-start">
                    <div className="relative bg-white text-gray-800 rounded-lg rounded-tl-none p-1 max-w-[78%] text-sm shadow-sm">
                      {b.url ? (
                        b.media_type === 'video' ? (
                          <video
                            src={b.url}
                            controls
                            className="rounded w-full max-h-56 object-cover bg-black"
                          />
                        ) : (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={b.url}
                            alt={b.caption || 'media'}
                            className="rounded w-full max-h-56 object-cover"
                          />
                        )
                      ) : (
                        <div className="bg-gray-200 rounded h-32 flex items-center justify-center text-4xl text-gray-400">
                          {b.media_type === 'image' ? '🖼️' : '📎'}
                        </div>
                      )}
                      {b.caption && (
                        <div className="text-xs text-gray-700 px-1 pt-1 pr-10 whitespace-pre-wrap break-words">
                          {formatWa(b.caption)}
                        </div>
                      )}
                      <div className="absolute bottom-1 right-2 text-[10px] text-gray-400">
                        {b.time}
                      </div>
                    </div>
                  </div>
                );
              }
              if (b.kind === 'ask') {
                const isLatestAsk =
                  waitingInput &&
                  bubbles
                    .slice(i + 1)
                    .every((nb) => nb.role !== 'bot' || nb.kind !== 'ask');
                return (
                  <div key={i} className="flex flex-col items-start gap-0.5">
                    <div className="flex justify-start w-full">
                      <div className="relative bg-white text-gray-800 rounded-lg rounded-tl-none px-2 py-1 max-w-[78%] text-sm shadow-sm">
                        <div className="whitespace-pre-wrap break-words pr-10">{formatWa(b.prompt)}</div>
                        <div className="absolute bottom-1 right-2 text-[10px] text-gray-400">
                          {b.time}
                        </div>
                      </div>
                    </div>
                    {b.options.length > 0 && (
                      <div className="w-full max-w-[78%] mt-0.5 bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden">
                        {b.options.map((opt, j) => (
                          <button
                            key={j}
                            type="button"
                            onClick={() => sendValue(opt)}
                            disabled={!isLatestAsk}
                            className="w-full text-center text-sm text-[#0099FF] font-medium px-3 py-2 border-t border-gray-100 first:border-t-0 hover:bg-blue-50 active:bg-blue-100 disabled:text-gray-400 disabled:cursor-not-allowed disabled:hover:bg-white transition"
                          >
                            {opt}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              }
              if (b.kind === 'pause') {
                return (
                  <div key={i} className="flex justify-center py-1">
                    <span className="bg-white/80 text-[10px] text-gray-500 italic px-2 py-0.5 rounded-full shadow-sm">
                      …pausa de {b.seconds}s…
                    </span>
                  </div>
                );
              }
              if (b.kind === 'catalog') {
                // #264: catálogo de WhatsApp — en el teléfono real es el
                // mensaje nativo de productos; aquí se representa como tarjeta.
                return (
                  <div key={i} className="flex justify-start w-full">
                    <div className="bg-white rounded-lg rounded-tl-none shadow-sm max-w-[78%] overflow-hidden">
                      <div className="bg-gradient-to-r from-fuchsia-100 to-rose-100 px-3 py-3 flex items-center gap-2">
                        <span className="text-2xl">🛍️</span>
                        <div>
                          <div className="text-sm font-semibold text-gray-800">{b.titulo}</div>
                          <div className="text-[10px] text-gray-500">Catálogo de WhatsApp</div>
                        </div>
                      </div>
                      {b.cuerpo && (
                        <div className="px-3 py-2 text-sm text-gray-800 whitespace-pre-wrap break-words">
                          {formatWa(b.cuerpo)}
                        </div>
                      )}
                      <div className="border-t border-gray-100 text-center text-sm text-[#0099FF] font-medium py-2">
                        Ver artículos
                      </div>
                      <div className="text-right text-[10px] text-gray-400 px-2 pb-1">{b.time}</div>
                    </div>
                  </div>
                );
              }
              if (b.kind === 'camino') {
                // Sprint 19 #255: ruta que tomó la IA en este turno (solo lectura).
                return (
                  <div key={i} className="flex justify-center py-0.5">
                    <span className="bg-fuchsia-50 text-fuchsia-700 text-[10px] px-2 py-0.5 rounded-full shadow-sm border border-fuchsia-100">
                      🧭 camino: {b.camino}
                    </span>
                  </div>
                );
              }
              if (b.kind === 'handoff') {
                return (
                  <div key={i} className="flex flex-col items-start gap-1 w-full">
                    {b.text && (
                      <div className="flex justify-start w-full">
                        <div className="relative bg-white text-gray-800 rounded-lg rounded-tl-none px-2 py-1 max-w-[78%] text-sm shadow-sm">
                          <div className="whitespace-pre-wrap break-words pr-10">{formatWa(b.text)}</div>
                          <div className="absolute bottom-1 right-2 text-[10px] text-gray-400">
                            {b.time}
                          </div>
                        </div>
                      </div>
                    )}
                    <div className="flex justify-center w-full py-1">
                      <span className="bg-emerald-50 text-emerald-700 text-[11px] font-medium px-3 py-1 rounded-full shadow-sm border border-emerald-100">
                        👤 Conversación asignada a {b.assignee}
                      </span>
                    </div>
                  </div>
                );
              }
              return null;
            })}
            {(sending || typing) && (
              <div className="flex justify-start">
                <div className="bg-white rounded-lg rounded-tl-none px-3 py-2 text-gray-400 text-sm shadow-sm">
                  <span className="inline-block animate-pulse">● ● ●</span>
                </div>
              </div>
            )}
            {finished && !sending && !typing && (
              <div className="flex justify-center pt-2">
                <button
                  type="button"
                  onClick={handleReset}
                  className="bg-white/90 text-[11px] text-gloma-brown hover:text-gloma-brown-dark px-3 py-1 rounded-full shadow-sm border border-gray-200"
                >
                  ↻ Reiniciar simulación
                </button>
              </div>
            )}
          </div>

          {/* Footer estilo WhatsApp */}
          <div className="bg-[#F0F0F0] px-2 py-2 flex items-end gap-2">
            <div className="flex-1 bg-white rounded-3xl shadow-sm flex items-center px-3 py-1.5 gap-2">
              <span className="text-gray-400 text-lg leading-none">😊</span>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSend();
                }}
                disabled={!waitingInput || sending || typing}
                placeholder={
                  waitingInput
                    ? 'Mensaje'
                    : finished
                    ? 'Conversación terminada'
                    : 'Esperando al bot…'
                }
                className="flex-1 text-sm bg-transparent focus:outline-none disabled:text-gray-400 placeholder-gray-400"
              />
              <span className="text-gray-400 text-base leading-none">📎</span>
              <span className="text-gray-400 text-base leading-none">📷</span>
            </div>
            <button
              type="button"
              onClick={handleSend}
              disabled={!waitingInput || sending || typing || input.trim() === ''}
              className="bg-[#075E54] text-white rounded-full w-10 h-10 flex items-center justify-center shadow-md hover:bg-[#054C44] disabled:bg-gray-400 disabled:cursor-not-allowed shrink-0"
              title={input.trim() === '' ? 'Mantén para grabar audio (deshabilitado)' : 'Enviar'}
            >
              {input.trim() === '' ? '🎤' : '➤'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function BotDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [bot, setBot] = useState<BotDetail | null>(null);
  const [error, setError] = useState('');
  const [simulatorOpen, setSimulatorOpen] = useState(false);
  // #265: zoom del visualizador. null = aún sin calcular; al cargar el bot se
  // ajusta automáticamente para VER EL ESQUEMA COMPLETO (vista por defecto).
  const [zoom, setZoom] = useState<number | null>(null);

  useEffect(() => {
    if (!id || typeof id !== 'string') return;
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (!token) {
      router.replace('/login');
      return;
    }
    fetch(`/api/bots/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (res.status === 401) {
          localStorage.removeItem('token');
          router.replace('/login');
          return;
        }
        if (res.status === 404) throw new Error('Bot no encontrado');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as BotDetail;
        setBot(data);
      })
      .catch((err) => setError(err.message || 'Error cargando bot'));
  }, [id, router]);

  const layout = useMemo(() => {
    if (!bot || bot.steps.length === 0) {
      return { nodes: [], edges: [], width: 0, height: 0 };
    }
    const stepsById = new Map(bot.steps.map((s) => [s.id, s] as const));

    // Salidas (edges) de un step: branches por opción + default si no la cubre.
    const outsOf = (
      s: BotStep,
    ): { target: number; label?: string }[] => {
      const cfg = (s.config as any) || {};
      const list: { target: number; label?: string }[] = [];
      const covered = new Set<number>();
      const add = (tgt: unknown, label?: string) => {
        if (typeof tgt === 'number' && stepsById.has(tgt) && !covered.has(tgt)) {
          list.push({ target: tgt, label });
          covered.add(tgt);
        }
      };
      // wait_input/condition: branches por opción ({opcion: step_id})
      const branches = cfg.branches;
      if (branches && typeof branches === 'object') {
        for (const [key, tgt] of Object.entries(branches)) add(tgt, key);
      }
      // llm en modo route: cada intent (keyword -> step_id) + default
      if (Array.isArray(cfg.intents)) {
        for (const intent of cfg.intents) {
          const label = intent?.keywords?.[0];
          add(intent?.step_id, label);
        }
      }
      add(cfg.default_step_id, 'otro');
      // salida por defecto (flujo lineal)
      add(s.next_step_id, list.length > 0 ? 'otro' : undefined);
      return list;
    };

    // BFS para asignar niveles (columnas, x). Tomamos el max para evitar
    // que un nodo retroceda si llega por dos caminos de distinto largo.
    const levelOf = new Map<number, number>();
    const root = bot.steps[0].id;
    levelOf.set(root, 0);
    const queue = [root];
    while (queue.length > 0) {
      const id = queue.shift()!;
      const lvl = levelOf.get(id)!;
      const s = stepsById.get(id)!;
      for (const { target } of outsOf(s)) {
        // Primera visita gana (BFS shortest-path). Imprescindible para flujos
        // con CICLOS (ej. bloques que vuelven al menú): si actualizáramos el
        // nivel en cada back-edge, un ciclo provocaría un loop infinito que
        // congela el editor.
        if (!levelOf.has(target)) {
          levelOf.set(target, lvl + 1);
          queue.push(target);
        }
      }
    }
    // Steps huérfanos (no alcanzables): los apilamos al final
    let maxLvl = 0;
    for (const v of levelOf.values()) if (v > maxLvl) maxLvl = v;
    for (const s of bot.steps) {
      if (!levelOf.has(s.id)) {
        maxLvl += 1;
        levelOf.set(s.id, maxLvl);
      }
    }

    // Agrupar por nivel y posicionar
    const byLevel = new Map<number, BotStep[]>();
    for (const s of bot.steps) {
      const lvl = levelOf.get(s.id)!;
      if (!byLevel.has(lvl)) byLevel.set(lvl, []);
      byLevel.get(lvl)!.push(s);
    }

    const ROW_GAP = 50;
    const nodes: { step: BotStep; x: number; y: number }[] = [];
    let maxRows = 0;
    // Altura de la columna más alta: las demás se CENTRAN verticalmente
    // respecto a ella para que las flechas se abran en abanico simétrico
    // (feedback CEO #256: "que se repartan mejor").
    let maxColHeight = 0;
    for (const steps of byLevel.values()) {
      const h = steps.length * NODE_H + (steps.length - 1) * ROW_GAP;
      if (h > maxColHeight) maxColHeight = h;
    }
    for (const [lvl, steps] of byLevel.entries()) {
      if (steps.length > maxRows) maxRows = steps.length;
      const colHeight = steps.length * NODE_H + (steps.length - 1) * ROW_GAP;
      const startY = PAD_Y + (maxColHeight - colHeight) / 2;
      steps.forEach((s, i) => {
        nodes.push({
          step: s,
          x: PAD_X + lvl * (NODE_W + GAP_X),
          y: startY + i * (NODE_H + ROW_GAP),
        });
      });
    }

    // Construir edges con label opcional por branch
    type Edge = {
      id: string;
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      label?: string;
    };
    const edges: Edge[] = [];
    for (const s of bot.steps) {
      const from = nodes.find((n) => n.step.id === s.id);
      if (!from) continue;
      const outs = outsOf(s);
      outs.forEach((o, k) => {
        const to = nodes.find((n) => n.step.id === o.target);
        if (!to) return;
        // Feedback CEO #256: TODAS las flechas de un bloque salen del MISMO
        // punto — la mitad de su lado derecho (sin offset por salida).
        edges.push({
          id: `${s.id}-${o.target}-${k}`,
          x1: from.x + NODE_W,
          y1: from.y + NODE_H / 2,
          x2: to.x,
          y2: to.y + NODE_H / 2,
          label: o.label,
        });
      });
    }

    const width = PAD_X * 2 + (maxLvl + 1) * NODE_W + maxLvl * GAP_X;
    const height = PAD_Y + maxRows * NODE_H + (maxRows - 1) * ROW_GAP + 80;
    return { nodes, edges, width, height };
  }, [bot]);

  // #265: escala "ver todo" — el esquema completo cabe en el viewport.
  const fitZoom = () => {
    if (typeof window === 'undefined' || layout.width === 0) return 1;
    const availW = window.innerWidth - 48;
    const availH = window.innerHeight - 140; // header + margen
    return Math.min(availW / Math.max(layout.width, 1000), availH / Math.max(layout.height, 500), 1);
  };

  useEffect(() => {
    if (zoom === null && layout.width > 0) {
      setZoom(Math.max(fitZoom(), 0.15));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);

  const z = zoom ?? 1;
  const zoomIn = () => setZoom(Math.min(z * 1.25, 2));
  const zoomOut = () => setZoom(Math.max(z / 1.25, 0.15));
  const zoomFit = () => setZoom(Math.max(fitZoom(), 0.15));

  return (
    <>
      <Head>
        <title>{bot ? `${bot.name} — Multiagente` : 'Cargando bot…'}</title>
      </Head>
      <div className="flex flex-col min-h-screen bg-white">
        <header className="border-b border-gray-200 px-6 py-3 flex items-center justify-between bg-white sticky top-0 z-10">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => window.close()}
              className="text-gray-500 hover:text-gray-700 text-xl leading-none"
              title="Cerrar pestaña"
            >
              ←
            </button>
            <h1 className="text-lg font-semibold text-gray-800">
              {bot?.name || (error ? 'Error' : 'Cargando…')}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSimulatorOpen(true)}
              disabled={!bot || (bot.engine !== 'llm' && bot.steps.length === 0)}
              className="px-4 py-1.5 text-sm bg-gloma-brown text-white rounded-md font-semibold hover:bg-gloma-brown-dark disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              ▶ Probar Chatbot
            </button>
          </div>
        </header>

        <main
          className="flex-1 overflow-auto relative"
          style={{
            backgroundImage:
              'linear-gradient(to right, #e5e7eb 1px, transparent 1px), linear-gradient(to bottom, #e5e7eb 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        >
          {error && (
            <div className="max-w-md mx-auto mt-16 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
              {error}
            </div>
          )}

          {bot && bot.engine === 'llm' && bot.steps.length === 0 && (
            <div className="max-w-lg mx-auto mt-16 bg-white border border-gloma-rose-soft rounded-xl shadow-sm px-6 py-8 text-center">
              <div className="text-4xl mb-3">🤖✨</div>
              <h2 className="text-lg font-semibold text-gray-800 mb-2">Bot conversacional con IA</h2>
              <p className="text-sm text-gray-600">
                Este bot no usa un diagrama de pasos: cada mensaje lo interpreta
                una IA (Claude) con el contexto de tu negocio y decide la mejor
                respuesta — puede enviar imágenes o videos, consultar tus pedidos
                y transferir el chat a un asesor humano cuando haga falta.
              </p>
              <p className="text-sm text-gray-500 mt-3">
                Pruébalo con el botón <span className="font-semibold">▶ Probar Chatbot</span>.
              </p>
            </div>
          )}

          {bot && bot.engine === 'llm' && bot.steps.length > 0 && (
            <div className="sticky left-0 mx-4 mt-4 max-w-2xl bg-fuchsia-50 border border-fuchsia-200 text-fuchsia-800 rounded-lg px-4 py-2 text-xs">
              🤖 <span className="font-semibold">Bot con motor de IA:</span> cada
              mensaje lo interpreta la IA y elige uno de estos caminos. Los bloques
              de acción indican qué hace y de dónde saca la información; el texto
              final al cliente siempre lo redacta la IA.
            </div>
          )}

          {bot && (bot.engine !== 'llm' || bot.steps.length > 0) && (
          <div
            style={{
              width: Math.max(layout.width, 1000) * z,
              height: Math.max(layout.height, 500) * z,
            }}
          >
            <div
              className="relative"
              style={{
                width: Math.max(layout.width, 1000),
                height: Math.max(layout.height, 500),
                transform: `scale(${z})`,
                transformOrigin: 'top left',
              }}
            >
              <svg
                className="absolute top-0 left-0 pointer-events-none"
                width={Math.max(layout.width, 1000)}
                height={Math.max(layout.height, 500)}
              >
                <defs>
                  <marker id="arrowhead" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
                    <polygon points="0 0, 10 4, 0 8" fill="#9ca3af" />
                  </marker>
                </defs>
                {layout.edges.map((edge) => {
                  const midX = (edge.x1 + edge.x2) / 2;
                  const midY = (edge.y1 + edge.y2) / 2;
                  const d = `M ${edge.x1} ${edge.y1} C ${midX} ${edge.y1}, ${midX} ${edge.y2}, ${edge.x2} ${edge.y2}`;
                  const labelText = edge.label
                    ? edge.label.length > 22
                      ? edge.label.slice(0, 22) + '…'
                      : edge.label
                    : null;
                  return (
                    <g key={edge.id}>
                      <path
                        d={d}
                        stroke="#9ca3af"
                        strokeWidth="2"
                        strokeDasharray="5,5"
                        fill="none"
                        markerEnd="url(#arrowhead)"
                      />
                      {labelText && (
                        <g>
                          <rect
                            x={midX - Math.max(labelText.length * 4, 30)}
                            y={midY - 10}
                            width={Math.max(labelText.length * 8, 60)}
                            height="20"
                            rx="10"
                            fill="white"
                            stroke="#d1d5db"
                            strokeWidth="1"
                          />
                          <text
                            x={midX}
                            y={midY + 4}
                            textAnchor="middle"
                            fontSize="11"
                            fill="#4b5563"
                            fontFamily="system-ui, -apple-system, sans-serif"
                          >
                            {labelText}
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}
              </svg>
              {layout.nodes.map(({ step, x, y }, idx) => (
                <div key={step.id} style={{ position: 'absolute', left: x, top: y }}>
                  <StepNode step={step} isFirst={idx === 0} />
                </div>
              ))}
            </div>
          </div>
          )}

          {bot && (bot.engine !== 'llm' || bot.steps.length > 0) && (
            <div className="fixed bottom-5 right-5 z-20 flex flex-col gap-2">
              <button
                type="button"
                onClick={zoomIn}
                title="Acercar zoom"
                className="w-11 h-11 rounded-full bg-white border border-gray-300 shadow-md text-gray-700 text-xl font-bold hover:bg-gray-50 active:bg-gray-100"
              >
                +
              </button>
              <button
                type="button"
                onClick={zoomFit}
                title="Ver el esquema completo (vista por defecto)"
                className="w-11 h-11 rounded-full bg-white border border-gray-300 shadow-md text-gray-700 text-lg hover:bg-gray-50 active:bg-gray-100"
              >
                ⤢
              </button>
              <button
                type="button"
                onClick={zoomOut}
                title="Alejar zoom"
                className="w-11 h-11 rounded-full bg-white border border-gray-300 shadow-md text-gray-700 text-xl font-bold hover:bg-gray-50 active:bg-gray-100"
              >
                −
              </button>
            </div>
          )}
        </main>

        {simulatorOpen && bot && (
          <SimulatorModal
            botId={bot.id}
            botName={bot.name}
            onClose={() => setSimulatorOpen(false)}
          />
        )}
      </div>
    </>
  );
}
