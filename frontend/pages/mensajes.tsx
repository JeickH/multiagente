import { useEffect, useRef, useState } from 'react';
import Layout from '../components/Layout';

type Conversation = {
  id: number;
  contact_wa_id: string;
  contact_name: string | null;
  status: string;
  last_message_at: string;
  last_message_preview: string | null;
};

type Message = {
  id: number;
  direction: 'inbound' | 'outbound';
  content: string;
  message_type: string;
  status: string;
  created_at: string;
};

type ConversationDetail = {
  id: number;
  contact_wa_id: string;
  contact_name: string | null;
  status: string;
  last_message_at: string;
  messages: Message[];
};

type TeamMe = {
  team: { id: number; nombre: string; owner_user_id: number };
  member: {
    id: number;
    user_id: number;
    role: string;
    nombre: string | null;
    correo: string | null;
    permissions: Record<string, boolean>;
  };
};

const FILTERS = [
  { key: 'todas', label: 'Todas' },
  { key: 'open', label: 'Abierto' },
  { key: 'pending', label: 'Pendiente' },
  { key: 'closed', label: 'Cerrado' },
];

function authHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function initials(name: string | null, fallback: string): string {
  const src = (name || fallback || '?').trim();
  return src.slice(0, 2).toUpperCase();
}

export default function Mensajes() {
  const [me, setMe] = useState<TeamMe | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [filter, setFilter] = useState<string>('todas');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [newPhone, setNewPhone] = useState('');
  const [newName, setNewName] = useState('');
  const [newTemplate, setNewTemplate] = useState('plantilla_prueba_1');
  const [newLang, setNewLang] = useState('es_CO');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Cargar /teams/me
  useEffect(() => {
    fetch('/api/teams/me', { headers: authHeaders() })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: TeamMe) => setMe(data))
      .catch((err) => setMeError(err.message || 'Error cargando equipo'));
  }, []);

  // Cargar conversaciones (poll cada 8s)
  useEffect(() => {
    if (!me) return;
    let active = true;
    const load = () =>
      fetch('/api/mensajes/conversaciones', { headers: authHeaders() })
        .then((res) => (res.ok ? res.json() : []))
        .then((data: Conversation[]) => {
          if (active) setConversations(data);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 8000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [me]);

  // Cargar detalle al seleccionar (poll cada 5s)
  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    let active = true;
    const load = () =>
      fetch(`/api/mensajes/conversaciones/${selectedId}`, { headers: authHeaders() })
        .then((res) => (res.ok ? res.json() : null))
        .then((data: ConversationDetail | null) => {
          if (active && data) setDetail(data);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [selectedId]);

  // Auto-scroll al final cuando llegan mensajes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [detail?.messages?.length]);

  const canReply = me?.member.permissions?.can_reply_messages === true;

  const filteredConversations = conversations.filter((c) => {
    if (filter !== 'todas' && c.status !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      const hay = `${c.contact_name || ''} ${c.contact_wa_id} ${c.last_message_preview || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const sendMessage = async () => {
    if (!detail || !draft.trim() || !canReply) return;
    setSending(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`/api/mensajes/conversaciones/${detail.id}/enviar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ content: draft.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${res.status}`);
      }
      setDraft('');
      const r2 = await fetch(`/api/mensajes/conversaciones/${detail.id}`, { headers: authHeaders() });
      if (r2.ok) setDetail(await r2.json());
    } catch (e: any) {
      setErrorMsg(e.message || 'Error enviando mensaje');
    } finally {
      setSending(false);
    }
  };

  const startNewConversation = async () => {
    if (!newPhone || !newTemplate) return;
    setSending(true);
    setErrorMsg(null);
    try {
      const res = await fetch('/api/mensajes/conversaciones/nueva', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          contact_wa_id: newPhone.replace(/\D/g, ''),
          contact_name: newName || null,
          template_name: newTemplate,
          language_code: newLang,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${res.status}`);
      }
      setShowNew(false);
      setNewPhone('');
      setNewName('');
      const r2 = await fetch('/api/mensajes/conversaciones', { headers: authHeaders() });
      if (r2.ok) {
        const list: Conversation[] = await r2.json();
        setConversations(list);
        const found = list.find((c) => c.contact_wa_id === newPhone.replace(/\D/g, ''));
        if (found) setSelectedId(found.id);
      }
    } catch (e: any) {
      setErrorMsg(e.message || 'Error iniciando conversación');
    } finally {
      setSending(false);
    }
  };

  return (
    <Layout variant="fullscreen">
      {/* Header del módulo */}
      <header className="bg-white border-b border-green-200 px-8 py-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-2xl">💬</span>
          <h1 className="text-xl font-semibold text-gray-800">Bandeja de entrada</h1>
        </div>
        <div className="flex items-center gap-4">
          {me && (
            <div className="text-right">
              <div className="text-xs text-gray-500">Conectado como</div>
              <div className="text-sm font-medium text-green-700">{me.member.nombre || me.member.correo}</div>
            </div>
          )}
          <div className="w-10 h-10 rounded-full bg-green-600 text-white flex items-center justify-center font-semibold">
            {initials(me?.member.nombre || null, me?.member.correo || 'U')}
          </div>
        </div>
      </header>

      {/* Body: lista + panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Lista de conversaciones */}
        <aside className="w-96 bg-white border-r border-green-100 flex flex-col">
          <div className="px-4 py-3 border-b border-green-100">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-gray-800">Chats activos</h2>
              <button
                onClick={() => setShowNew(true)}
                className="w-8 h-8 rounded-full bg-green-600 text-white flex items-center justify-center hover:bg-green-700 transition-colors"
                title="Nueva conversación"
              >
                +
              </button>
            </div>
            <div className="text-xs text-gray-500 mb-2">
              {conversations.length} {conversations.length === 1 ? 'charla' : 'charlas'}
            </div>
            <input
              type="text"
              placeholder="Buscar..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-green-500"
            />
            <div className="flex gap-2 mt-3 flex-wrap">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    filter === f.key
                      ? 'bg-green-600 text-white border-green-600'
                      : 'text-gray-600 border-gray-200 hover:border-green-400'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {meError && (
              <div className="p-4 text-sm text-red-600">Error cargando equipo: {meError}</div>
            )}
            {filteredConversations.length === 0 ? (
              <div className="p-8 text-center text-gray-400 text-sm">
                {conversations.length === 0
                  ? 'Sin conversaciones todavía. Inicia una con el botón + arriba.'
                  : 'No hay resultados con el filtro actual.'}
              </div>
            ) : (
              filteredConversations.map((c) => {
                const selected = c.id === selectedId;
                return (
                  <button
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    className={`w-full text-left px-4 py-3 flex gap-3 border-b border-gray-50 transition-colors ${
                      selected ? 'bg-green-50' : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className="w-10 h-10 rounded-full bg-green-100 text-green-700 flex items-center justify-center font-semibold flex-shrink-0">
                      {initials(c.contact_name, c.contact_wa_id)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm text-gray-800 truncate">
                          {c.contact_name || `+${c.contact_wa_id}`}
                        </span>
                        <span className="text-xs text-gray-400 ml-2 flex-shrink-0">
                          {formatTime(c.last_message_at)}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {c.last_message_preview || '(sin mensajes)'}
                      </div>
                      <span
                        className={`inline-block mt-1 px-2 py-0.5 text-[10px] rounded-full ${
                          c.status === 'open'
                            ? 'bg-green-100 text-green-700'
                            : c.status === 'pending'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        {/* Panel de chat */}
        <section className="flex-1 flex flex-col bg-green-50">
          {detail ? (
            <>
              <div className="bg-white border-b border-green-100 px-6 py-3 flex items-center gap-3 shadow-sm">
                <div className="w-10 h-10 rounded-full bg-green-100 text-green-700 flex items-center justify-center font-semibold">
                  {initials(detail.contact_name, detail.contact_wa_id)}
                </div>
                <div>
                  <div className="font-semibold text-gray-800">
                    {detail.contact_name || `+${detail.contact_wa_id}`}
                  </div>
                  <div className="text-xs text-gray-500">+{detail.contact_wa_id}</div>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-3">
                {detail.messages.length === 0 ? (
                  <div className="text-center text-gray-400 text-sm mt-12">
                    Sin mensajes en esta conversación.
                  </div>
                ) : (
                  detail.messages.map((m) => (
                    <div
                      key={m.id}
                      className={`flex ${m.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-md px-4 py-2 rounded-2xl shadow-sm ${
                          m.direction === 'outbound'
                            ? 'bg-green-600 text-white rounded-br-sm'
                            : 'bg-white text-gray-800 rounded-bl-sm border border-gray-100'
                        }`}
                      >
                        <div className="text-sm whitespace-pre-wrap break-words">{m.content}</div>
                        <div
                          className={`text-[10px] mt-1 ${
                            m.direction === 'outbound' ? 'text-green-100' : 'text-gray-400'
                          }`}
                        >
                          {formatTime(m.created_at)}
                          {m.status === 'failed' && ' • falló'}
                        </div>
                      </div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Composer */}
              <div className="bg-white border-t border-green-100 p-4">
                {errorMsg && (
                  <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                    {errorMsg}
                  </div>
                )}
                {canReply ? (
                  <div className="flex gap-2">
                    <textarea
                      rows={2}
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          sendMessage();
                        }
                      }}
                      placeholder="Escribe un mensaje (Enter para enviar)..."
                      className="flex-1 px-3 py-2 border border-gray-200 rounded-lg resize-none focus:outline-none focus:border-green-500 text-sm"
                    />
                    <button
                      onClick={sendMessage}
                      disabled={sending || !draft.trim()}
                      className="px-5 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {sending ? '...' : 'Enviar'}
                    </button>
                  </div>
                ) : (
                  <div className="text-center text-sm text-gray-500 py-3">
                    No tienes permiso para responder mensajes en este equipo.
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="text-6xl mb-4">💬</div>
                <div className="text-lg font-semibold text-gray-700">Ninguna conversación seleccionada</div>
                <div className="text-sm text-gray-500 mt-2">Selecciona un chat de la lista o inicia uno nuevo</div>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Modal nueva conversación */}
      {showNew && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-1">Nueva conversación</h3>
            <p className="text-xs text-gray-500 mb-4">
              Para iniciar conversación con un contacto nuevo, Meta exige enviar un template aprobado.
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500">Número (con código país, sin +)</label>
                <input
                  type="text"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  placeholder="573150764000"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-green-500"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">Nombre (opcional)</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-green-500"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">Nombre del template</label>
                <input
                  type="text"
                  value={newTemplate}
                  onChange={(e) => setNewTemplate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-green-500"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">Idioma</label>
                <input
                  type="text"
                  value={newLang}
                  onChange={(e) => setNewLang(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-green-500"
                />
              </div>
            </div>
            {errorMsg && (
              <div className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                {errorMsg}
              </div>
            )}
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => {
                  setShowNew(false);
                  setErrorMsg(null);
                }}
                className="flex-1 px-4 py-2 border border-gray-200 rounded-lg text-gray-700 hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={startNewConversation}
                disabled={sending || !newPhone || !newTemplate}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                {sending ? 'Enviando...' : 'Enviar template'}
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}
