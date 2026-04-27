import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Layout from '../components/Layout';

type BotListItem = {
  id: number;
  name: string;
  status: string;
  channels: string[];
  trigger_type: 'default' | 'keyword' | 'manual';
  trigger_config: Record<string, any> | null;
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

function TriggerBadge({ bot }: { bot: BotListItem }) {
  if (bot.trigger_type === 'default') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gloma-rose-soft/30 text-gloma-brown border border-gloma-rose-soft">
        <span>⭐</span> Default
      </span>
    );
  }
  if (bot.trigger_type === 'keyword') {
    const keywords: string[] = bot.trigger_config?.keywords || [];
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
        <span>🔑</span>
        {keywords.length > 0 ? keywords.join(', ') : 'Keyword'}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-50 text-gray-600 border border-gray-200">
      <span>🔗</span> Manual
    </span>
  );
}

export default function BotsPage() {
  const router = useRouter();
  const [bots, setBots] = useState<BotListItem[] | null>(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [downloading, setDownloading] = useState(false);

  const getToken = () =>
    typeof window !== 'undefined' ? localStorage.getItem('token') : null;

  useEffect(() => {
    const token = getToken();
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

  const handleDownload = async () => {
    const token = getToken();
    if (!token) return;
    setDownloading(true);
    try {
      const res = await fetch('/api/bots/export', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const cd = res.headers.get('content-disposition') || '';
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : `bots-export-${Date.now()}.json`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message || 'Error descargando');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Layout variant="fullscreen">
      <div className="p-8 w-full">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Chatbot</h1>
            <p className="text-gray-500 text-sm mt-1">
              Listado de los bots configurados para tu cuenta.
            </p>
          </div>
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading || !bots || bots.length === 0}
            className="px-3 py-2 border border-gray-300 rounded-md text-gray-700 text-sm bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            title="Descargar todos los bots en formato JSON"
          >
            <span>⤓</span>
            {downloading ? 'Descargando…' : 'Descargar JSON'}
          </button>
        </div>

        <div className="flex items-center justify-between border-b border-gray-200 mb-4">
          <div className="flex gap-6">
            <button
              type="button"
              className="py-2 px-1 border-b-[3px] border-gloma-rose text-gray-800 font-semibold text-sm flex items-center gap-2"
            >
              Tus bots
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-gloma-rose-soft/300 text-white text-[10px] font-bold">
                {bots?.length ?? 0}
              </span>
            </button>
          </div>
          <input
            type="text"
            placeholder="Buscar tus bots..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-sm px-3 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:border-gloma-rose w-56"
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
                  <th className="text-left py-3 px-4 font-semibold">Activación</th>
                  <th className="text-center py-3 px-4 font-semibold">Disparado</th>
                  <th className="text-left py-3 px-4 font-semibold">Modificado el</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((bot) => (
                  <tr
                    key={bot.id}
                    className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                  >
                    <td className="py-4 px-4">
                      <a
                        href={`/bots/${bot.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:text-blue-800 hover:underline font-medium"
                      >
                        {bot.name}
                      </a>
                    </td>
                    <td className="py-4 px-4">
                      <TriggerBadge bot={bot} />
                    </td>
                    <td className={`text-center py-4 px-4 font-mono ${bot.triggered_count === 0 ? 'text-gray-300' : 'text-gray-800'}`}>
                      {bot.triggered_count}
                    </td>
                    <td className="py-4 px-4 text-sm text-gray-600">
                      <div>Creado {relativeTime(bot.created_at)}</div>
                      <div className="text-xs text-gray-400">
                        Actualizado {relativeTime(bot.updated_at)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
}
