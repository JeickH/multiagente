import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Layout from '../components/Layout';

type BotListItem = {
  id: number;
  name: string;
  is_premium: boolean;
  status: string;
  channels: string[];
  triggered_count: number;
  completed_steps_count: number;
  finished_count: number;
  created_at: string;
  updated_at: string;
};

function relativeTime(iso: string): string {
  const now = new Date();
  const then = new Date(iso);
  const diffMs = now.getTime() - then.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'hace segundos';
  if (diffMin < 60) return `${diffMin} min hace`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} h hace`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 30) return `${diffD} d hace`;
  const diffMo = Math.floor(diffD / 30);
  if (diffMo < 12) return `${diffMo} mes${diffMo === 1 ? '' : 'es'} hace`;
  const diffY = Math.floor(diffMo / 12);
  return `${diffY} año${diffY === 1 ? '' : 's'} hace`;
}

function ChannelIcon({ channel }: { channel: string }) {
  const base = 'inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold text-white';
  if (channel === 'whatsapp') {
    return <span className={`${base} bg-green-500`} title="WhatsApp">W</span>;
  }
  if (channel === 'instagram') {
    return (
      <span
        className={`${base} bg-gradient-to-tr from-pink-500 via-red-500 to-yellow-400`}
        title="Instagram"
      >
        I
      </span>
    );
  }
  if (channel === 'messenger') {
    return <span className={`${base} bg-blue-500`} title="Messenger">M</span>;
  }
  return null;
}

function PremiumBadge() {
  return (
    <span className="inline-flex items-center text-yellow-500" title="Bot Premium">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2l3 7h7l-5.5 4.5L18 22l-6-4-6 4 1.5-8.5L2 9h7z" />
      </svg>
    </span>
  );
}

function ActionIcon({ label, children, danger }: { label: string; children: React.ReactNode; danger?: boolean }) {
  return (
    <button
      type="button"
      disabled
      aria-label={label}
      title={`${label} (solo lectura por ahora)`}
      className={`inline-flex items-center justify-center w-8 h-8 rounded-md border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 disabled:cursor-not-allowed ${
        danger ? 'hover:text-red-500 hover:border-red-200' : ''
      }`}
    >
      {children}
    </button>
  );
}

export default function BotsPage() {
  const router = useRouter();
  const [bots, setBots] = useState<BotListItem[] | null>(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (!token) {
      router.push('/login');
      return;
    }
    fetch('/api/bots', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (res.status === 401) {
          localStorage.removeItem('token');
          router.push('/login');
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as BotListItem[];
        setBots(data);
      })
      .catch((err) => setError(err.message || 'Error cargando bots'));
  }, [router]);

  const filtered = (bots || []).filter((b) =>
    search.trim() === '' ? true : b.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Layout variant="fullscreen">
      <div className="p-8 w-full">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Chatbot</h1>
            <p className="text-gray-500 text-sm mt-1">
              Selecciona un chatbot a continuación y hazlo tuyo personalizándolo.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              className="px-3 py-2 border border-gray-300 rounded-md text-gray-500 text-sm bg-white disabled:cursor-not-allowed"
              title="Importar (próximamente)"
            >
              ⤓
            </button>
            <button
              type="button"
              disabled
              className="px-4 py-2 bg-green-600 text-white rounded-md text-sm font-semibold opacity-60 cursor-not-allowed"
              title="La creación de bots llegará en el próximo sprint"
            >
              + Agregar chatbot
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between border-b border-gray-200 mb-4">
          <div className="flex gap-6">
            <button
              type="button"
              className="py-2 px-1 border-b-[3px] border-green-500 text-gray-800 font-semibold text-sm flex items-center gap-2"
            >
              Tus bots
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-green-500 text-white text-[10px] font-bold">
                {bots?.length ?? 0}
              </span>
            </button>
            <button
              type="button"
              disabled
              className="py-2 px-1 text-gray-400 font-medium text-sm cursor-not-allowed"
            >
              Plantillas
            </button>
          </div>
          <input
            type="text"
            placeholder="Buscar tus bots..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-sm px-3 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:border-green-500 w-56"
          />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded mb-4 text-sm">
            {error}
          </div>
        )}

        {bots === null && !error && (
          <p className="text-gray-400 text-sm">Cargando bots…</p>
        )}

        {bots !== null && filtered.length === 0 && (
          <p className="text-gray-400 text-sm py-8 text-center">
            No tienes bots configurados. Contáctanos para que te armemos el primero.
          </p>
        )}

        {filtered.length > 0 && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr className="text-sm text-gray-600">
                  <th className="text-left py-3 px-4 font-semibold">Nombre</th>
                  <th className="text-center py-3 px-4 font-semibold">Disparado</th>
                  <th className="text-center py-3 px-4 font-semibold">Pasos terminados</th>
                  <th className="text-center py-3 px-4 font-semibold">Terminada</th>
                  <th className="text-left py-3 px-4 font-semibold">Modificado el</th>
                  <th className="text-center py-3 px-4 font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((bot) => {
                  const isZero = (n: number) => (n === 0 ? 'text-gray-300' : 'text-gray-800');
                  return (
                    <tr
                      key={bot.id}
                      className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                    >
                      <td className="py-4 px-4">
                        <div className="flex items-center gap-2">
                          <a
                            href={`/bots/${bot.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-800 hover:underline font-medium"
                          >
                            {bot.name}
                          </a>
                          <div className="flex items-center gap-1">
                            {bot.channels.map((c) => (
                              <ChannelIcon key={c} channel={c} />
                            ))}
                            {bot.is_premium && <PremiumBadge />}
                          </div>
                        </div>
                      </td>
                      <td className={`text-center py-4 px-4 font-mono ${isZero(bot.triggered_count)}`}>
                        {bot.triggered_count}
                      </td>
                      <td
                        className={`text-center py-4 px-4 font-mono ${isZero(
                          bot.completed_steps_count
                        )}`}
                      >
                        {bot.completed_steps_count}
                      </td>
                      <td className={`text-center py-4 px-4 font-mono ${isZero(bot.finished_count)}`}>
                        {bot.finished_count}
                      </td>
                      <td className="py-4 px-4 text-sm text-gray-600">
                        <div>Creado {relativeTime(bot.created_at)}</div>
                        <div className="text-xs text-gray-400">
                          Actualizar {relativeTime(bot.updated_at)}
                        </div>
                      </td>
                      <td className="py-4 px-4">
                        <div className="flex items-center justify-center gap-2">
                          <ActionIcon label="Duplicar">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <rect x="9" y="9" width="13" height="13" rx="2" />
                              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                            </svg>
                          </ActionIcon>
                          <ActionIcon label="Editar">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                            </svg>
                          </ActionIcon>
                          <ActionIcon label="Eliminar" danger>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6l-2 14a2 2 0 01-2 2H9a2 2 0 01-2-2L5 6" />
                              <path d="M10 11v6M14 11v6" />
                              <path d="M9 6V4a2 2 0 012-2h2a2 2 0 012 2v2" />
                            </svg>
                          </ActionIcon>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
}
