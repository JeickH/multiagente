import { useEffect, useMemo, useRef, useState } from 'react';
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
  type: 'say' | 'say_media' | 'ask' | 'pause' | 'end';
  payload: Record<string, any>;
};

type SimulateResponse = {
  actions: BotAction[];
  next_state: { current_step_id: number | null; variables: Record<string, any> } | null;
  finished: boolean;
};

type ChatBubble =
  | { role: 'bot'; kind: 'text'; text: string }
  | { role: 'bot'; kind: 'media'; caption: string; media_type: string }
  | { role: 'bot'; kind: 'ask'; prompt: string; options: string[] }
  | { role: 'bot'; kind: 'pause'; seconds: number }
  | { role: 'bot'; kind: 'end'; text: string }
  | { role: 'user'; text: string };

const NODE_W = 260;
const NODE_H = 200;
const GAP_X = 80;
const PAD_X = 60;
const PAD_Y = 120;

const STEP_STYLE: Record<string, { accent: string; icon: string; badge: string }> = {
  send_text:    { accent: 'border-blue-400',   icon: '💬', badge: 'bg-blue-50 text-blue-700' },
  send_template:{ accent: 'border-indigo-400', icon: '📋', badge: 'bg-indigo-50 text-indigo-700' },
  send_media:   { accent: 'border-purple-400', icon: '🖼️', badge: 'bg-purple-50 text-purple-700' },
  wait_input:   { accent: 'border-amber-400',  icon: '⌨️', badge: 'bg-amber-50 text-amber-700' },
  delay:        { accent: 'border-slate-400',  icon: '⏱️', badge: 'bg-slate-100 text-slate-700' },
  condition:    { accent: 'border-orange-400', icon: '🔀', badge: 'bg-orange-50 text-orange-700' },
  end:          { accent: 'border-rose-400',   icon: '🏁', badge: 'bg-rose-50 text-rose-700' },
};

function StepNode({ step, isFirst }: { step: BotStep; isFirst: boolean }) {
  const style = STEP_STYLE[step.step_type] || STEP_STYLE.send_text;
  const cfg = step.config || {};
  const renderBody = () => {
    switch (step.step_type) {
      case 'send_text':
      case 'end':
        return <p className="text-sm text-gray-700">{cfg.text || '—'}</p>;
      case 'send_media':
        return (
          <div>
            <div className="bg-gray-100 rounded h-20 flex items-center justify-center text-gray-400 text-3xl mb-2">
              {cfg.media_type === 'image' ? '🖼️' : '📎'}
            </div>
            <p className="text-xs text-gray-600 line-clamp-2">{cfg.caption || '—'}</p>
          </div>
        );
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
      className={`absolute bg-white rounded-xl border-t-4 ${style.accent} border border-gray-200 shadow-sm p-4 flex flex-col`}
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
  const scrollRef = useRef<HTMLDivElement>(null);

  const getToken = () =>
    typeof window !== 'undefined' ? localStorage.getItem('token') : null;

  const appendActionsAsBubbles = (actions: BotAction[]) => {
    const newBubbles: ChatBubble[] = actions.map((a): ChatBubble => {
      if (a.type === 'say') return { role: 'bot', kind: 'text', text: a.payload.text || '' };
      if (a.type === 'say_media')
        return {
          role: 'bot',
          kind: 'media',
          caption: a.payload.caption || '',
          media_type: a.payload.media_type || 'image',
        };
      if (a.type === 'ask')
        return {
          role: 'bot',
          kind: 'ask',
          prompt: a.payload.prompt || '',
          options: a.payload.options || [],
        };
      if (a.type === 'pause')
        return { role: 'bot', kind: 'pause', seconds: a.payload.seconds || 0 };
      return { role: 'bot', kind: 'end', text: a.payload.text || '' };
    });
    setBubbles((prev) => [...prev, ...newBubbles]);
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
      appendActionsAsBubbles(data.actions);
      setState(data.next_state);
      setFinished(data.finished);
      const lastAction = data.actions[data.actions.length - 1];
      setWaitingInput(!data.finished && lastAction?.type === 'ask');
    } catch (err: any) {
      setBubbles((prev) => [
        ...prev,
        { role: 'bot', kind: 'text', text: `⚠️ Error en simulación: ${err.message}` },
      ]);
    } finally {
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

  const handleSend = async () => {
    const value = input.trim();
    if (!value || sending) return;
    setBubbles((prev) => [...prev, { role: 'user', text: value }]);
    setInput('');
    setWaitingInput(false);
    await turn(value);
  };

  const handleReset = () => {
    setBubbles([]);
    setState(null);
    setFinished(false);
    setWaitingInput(false);
    setInput('');
    // Disparar primer turno
    setTimeout(() => turn(null), 0);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md h-[600px] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-gray-200 px-4 py-3 flex items-center justify-between bg-green-600 text-white rounded-t-xl">
          <div className="flex items-center gap-2">
            <span className="text-lg">🤖</span>
            <div>
              <div className="font-semibold text-sm">{botName}</div>
              <div className="text-[11px] text-green-100">Simulación — no se envían mensajes reales</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleReset}
              className="text-white/80 hover:text-white text-xs px-2 py-1 rounded hover:bg-green-700"
              title="Reiniciar conversación"
            >
              ↻
            </button>
            <button
              type="button"
              onClick={onClose}
              className="text-white/80 hover:text-white text-lg leading-none"
              title="Cerrar"
            >
              ×
            </button>
          </div>
        </div>

        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-4 py-4 space-y-3"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.9), rgba(255,255,255,0.9)), url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22%3E%3Ccircle cx=%2250%22 cy=%2250%22 r=%221%22 fill=%22%23d1fae5%22/%3E%3C/svg%3E")',
            backgroundColor: '#f0fdf4',
          }}
        >
          {bubbles.map((b, i) => {
            if (b.role === 'user') {
              return (
                <div key={i} className="flex justify-end">
                  <div className="bg-green-500 text-white rounded-2xl rounded-br-sm px-3 py-2 max-w-[75%] text-sm shadow-sm">
                    {b.text}
                  </div>
                </div>
              );
            }
            if (b.kind === 'text') {
              return (
                <div key={i} className="flex justify-start">
                  <div className="bg-white text-gray-800 rounded-2xl rounded-bl-sm px-3 py-2 max-w-[75%] text-sm shadow-sm border border-gray-100">
                    {b.text}
                  </div>
                </div>
              );
            }
            if (b.kind === 'media') {
              return (
                <div key={i} className="flex justify-start">
                  <div className="bg-white text-gray-800 rounded-2xl rounded-bl-sm px-3 py-2 max-w-[75%] text-sm shadow-sm border border-gray-100">
                    <div className="bg-gray-100 rounded h-24 flex items-center justify-center text-3xl text-gray-400 mb-2">
                      {b.media_type === 'image' ? '🖼️' : '📎'}
                    </div>
                    {b.caption && <div className="text-xs text-gray-600">{b.caption}</div>}
                  </div>
                </div>
              );
            }
            if (b.kind === 'ask') {
              return (
                <div key={i} className="flex justify-start">
                  <div className="bg-white text-gray-800 rounded-2xl rounded-bl-sm px-3 py-2 max-w-[75%] text-sm shadow-sm border border-gray-100">
                    <div>{b.prompt}</div>
                    {b.options.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {b.options.map((opt, j) => (
                          <li key={j} className="text-xs bg-gray-50 rounded px-2 py-1 text-gray-600">
                            {opt}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              );
            }
            if (b.kind === 'pause') {
              return (
                <div key={i} className="flex justify-center">
                  <span className="text-[11px] text-gray-400 italic">
                    …pausa de {b.seconds}s omitida en simulación…
                  </span>
                </div>
              );
            }
            return (
              <div key={i} className="flex justify-start">
                <div className="bg-rose-50 text-rose-700 rounded-2xl rounded-bl-sm px-3 py-2 max-w-[75%] text-sm shadow-sm border border-rose-200">
                  <div className="flex items-center gap-1 mb-1">
                    <span>🏁</span>
                    <span className="text-[11px] uppercase tracking-wide">Fin del flujo</span>
                  </div>
                  {b.text}
                </div>
              </div>
            );
          })}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-white rounded-2xl rounded-bl-sm px-3 py-2 text-gray-400 text-sm shadow-sm border border-gray-100">
                <span className="inline-block animate-pulse">● ● ●</span>
              </div>
            </div>
          )}
          {finished && !sending && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={handleReset}
                className="text-xs text-green-700 hover:text-green-800 underline"
              >
                Reiniciar simulación
              </button>
            </div>
          )}
        </div>

        <div className="border-t border-gray-200 px-4 py-3 bg-white rounded-b-xl">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSend();
              }}
              disabled={!waitingInput || sending}
              placeholder={
                waitingInput
                  ? 'Escribe tu respuesta…'
                  : finished
                  ? 'Conversación terminada. Reinicia para probar de nuevo.'
                  : 'Esperando al bot…'
              }
              className="flex-1 text-sm px-3 py-2 border border-gray-200 rounded-full focus:outline-none focus:border-green-500 disabled:bg-gray-50 disabled:text-gray-400"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!waitingInput || sending || input.trim() === ''}
              className="bg-green-500 text-white rounded-full w-10 h-10 flex items-center justify-center hover:bg-green-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              ➤
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
    if (!bot) return { nodes: [], edges: [], width: 0, height: 0 };
    const nodes = bot.steps.map((step, idx) => ({
      step,
      x: PAD_X + idx * (NODE_W + GAP_X),
      y: PAD_Y,
    }));
    const edges = bot.steps
      .map((step) => {
        if (!step.next_step_id) return null;
        const from = nodes.find((n) => n.step.id === step.id);
        const to = nodes.find((n) => n.step.id === step.next_step_id);
        if (!from || !to) return null;
        return {
          id: `${step.id}-${step.next_step_id}`,
          x1: from.x + NODE_W,
          y1: from.y + NODE_H / 2,
          x2: to.x,
          y2: to.y + NODE_H / 2,
        };
      })
      .filter(Boolean) as { id: string; x1: number; y1: number; x2: number; y2: number }[];
    const width = PAD_X + bot.steps.length * (NODE_W + GAP_X);
    const height = PAD_Y + NODE_H + 80;
    return { nodes, edges, width, height };
  }, [bot]);

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
              disabled={!bot || bot.steps.length === 0}
              className="px-4 py-1.5 text-sm bg-green-600 text-white rounded-md font-semibold hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
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

          {bot && (
            <div
              className="relative"
              style={{
                width: Math.max(layout.width, 1000),
                height: Math.max(layout.height, 500),
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
                  const d = `M ${edge.x1} ${edge.y1} C ${midX} ${edge.y1}, ${midX} ${edge.y2}, ${edge.x2} ${edge.y2}`;
                  return (
                    <path
                      key={edge.id}
                      d={d}
                      stroke="#9ca3af"
                      strokeWidth="2"
                      strokeDasharray="5,5"
                      fill="none"
                      markerEnd="url(#arrowhead)"
                    />
                  );
                })}
              </svg>
              {layout.nodes.map(({ step, x, y }, idx) => (
                <div key={step.id} style={{ position: 'absolute', left: x, top: y }}>
                  <StepNode step={step} isFirst={idx === 0} />
                </div>
              ))}
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
