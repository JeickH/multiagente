import { useEffect, useMemo, useState } from 'react';
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
  is_premium: boolean;
  status: string;
  channels: string[];
  triggered_count: number;
  completed_steps_count: number;
  finished_count: number;
  created_at: string;
  updated_at: string;
  steps: BotStep[];
};

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

export default function BotDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const [bot, setBot] = useState<BotDetail | null>(null);
  const [error, setError] = useState('');

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
            {bot && (
              <>
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-green-100 text-green-600">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                  </svg>
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              className="px-4 py-1.5 text-sm border border-gray-300 rounded-md text-gray-500 bg-white disabled:cursor-not-allowed"
              title="La edición llegará en un próximo sprint"
            >
              Guardar
            </button>
            <button
              type="button"
              disabled
              className="px-4 py-1.5 text-sm bg-green-600 text-white rounded-md font-semibold opacity-60 cursor-not-allowed flex items-center gap-2"
            >
              ▶ Probar Chatbot
            </button>
            <button
              type="button"
              disabled
              className="px-2 py-1.5 text-gray-400 border border-gray-200 rounded-md bg-white cursor-not-allowed"
              title="Más opciones"
            >
              ⋯
            </button>
            <button
              type="button"
              disabled
              className="px-2 py-1.5 text-gray-400 border border-gray-200 rounded-md bg-white cursor-not-allowed"
              title="Compartir"
            >
              ⤴
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-auto relative" style={{
          backgroundImage:
            'linear-gradient(to right, #e5e7eb 1px, transparent 1px), linear-gradient(to bottom, #e5e7eb 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}>
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
                  <marker
                    id="arrowhead"
                    markerWidth="10"
                    markerHeight="8"
                    refX="9"
                    refY="4"
                    orient="auto"
                  >
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
      </div>
    </>
  );
}
