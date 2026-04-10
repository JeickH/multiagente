import Layout from '../components/Layout';
import { useEffect, useState } from 'react';

interface UserData {
  id: number;
  nombre: string;
  correo: string;
  tipo_documento: string;
  documento: string;
}

interface MetaAccountStatus {
  registered: boolean;
  display_phone?: string | null;
  verified_name?: string | null;
  phone_number_id?: string | null;
  waba_id?: string | null;
  is_active?: boolean | null;
  status?: string | null;
  last_validated_at?: string | null;
  validation_error?: string | null;
  can_manage_meta_account?: boolean;
}

export default function Usuario() {
  const [user, setUser] = useState<UserData | null>(null);
  const [meta, setMeta] = useState<MetaAccountStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    phone_number_id: '',
    waba_id: '',
    access_token: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  const openConnectModal = () => {
    setForm({ phone_number_id: '', waba_id: '', access_token: '' });
    setFormError(null);
    setShowModal(true);
  };

  const closeConnectModal = () => {
    if (submitting) return;
    // Limpieza defensiva: no dejar el token en memoria del componente
    setForm({ phone_number_id: '', waba_id: '', access_token: '' });
    setFormError(null);
    setShowModal(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);

    const token = localStorage.getItem('token');
    if (!token) {
      setFormError('Sesión expirada. Inicia sesión de nuevo.');
      setSubmitting(false);
      return;
    }

    try {
      const res = await fetch('/api/usuario/me/meta-account', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(form),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setFormError(data.detail || 'No se pudo conectar. Revisa tus credenciales.');
        setSubmitting(false);
        return;
      }

      const data: MetaAccountStatus = await res.json();
      setMeta(data);
      // Limpieza inmediata del formulario tras éxito
      setForm({ phone_number_id: '', waba_id: '', access_token: '' });
      setShowModal(false);
    } catch {
      setFormError('Error de red. Intenta de nuevo.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDisconnect = async () => {
    const ok = window.confirm(
      '¿Seguro que quieres desconectar la cuenta de WhatsApp? Tendrás que volver a pegar el token para reconectar.'
    );
    if (!ok) return;

    const token = localStorage.getItem('token');
    if (!token) return;

    setDisconnecting(true);
    try {
      const res = await fetch('/api/usuario/me/meta-account', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setMeta({ registered: false, can_manage_meta_account: true });
      }
    } catch {
      // silencioso
    } finally {
      setDisconnecting(false);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }

    const headers = { Authorization: `Bearer ${token}` };

    Promise.all([
      fetch('/api/usuario/me', { headers }).then((res) =>
        res.ok ? res.json() : Promise.reject()
      ),
      fetch('/api/usuario/me/meta-account', { headers })
        .then((res) => (res.ok ? res.json() : { registered: false }))
        .catch(() => ({ registered: false })),
    ])
      .then(([userData, metaData]) => {
        setUser(userData);
        setMeta(metaData);
      })
      .catch(() => {
        setUser(null);
        setMeta(null);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout>
      <div className="text-center w-full">
        <span className="text-5xl mb-4 block">👤</span>
        <h1 className="text-2xl font-semibold text-gray-800 mb-6">Mi Plan y Datos</h1>

        {loading ? (
          <p className="text-gray-400">Cargando...</p>
        ) : user ? (
          <div className="text-left max-w-md mx-auto space-y-4">
            <div className="bg-green-50 rounded-lg p-4 border border-green-200">
              <h2 className="text-sm font-medium text-green-600 mb-1">Plan Actual</h2>
              <p className="text-lg font-semibold text-gray-800">Plan Básico</p>
              <p className="text-sm text-gray-500">WhatsApp Business API - 10 usuarios</p>
            </div>

            {/* Cuenta de WhatsApp (Meta) */}
            <div
              className={`rounded-lg p-4 border ${
                meta?.registered
                  ? 'bg-emerald-50 border-emerald-200'
                  : 'bg-gray-50 border-gray-200'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-medium text-gray-600">
                  Cuenta de WhatsApp Business
                </h2>
                {meta?.registered ? (
                  <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                    Conectada
                  </span>
                ) : (
                  <span className="text-xs font-semibold text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
                    No registrada
                  </span>
                )}
              </div>

              {meta?.registered ? (
                <div className="space-y-1">
                  <p className="text-lg font-semibold text-gray-800">
                    {meta.verified_name || 'Sin nombre visible'}
                  </p>
                  <p className="text-sm text-gray-600">{meta.display_phone}</p>
                  {meta.is_active === false && (
                    <p className="text-xs text-red-500">
                      La cuenta está marcada como inactiva
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  Aún no has conectado una cuenta de WhatsApp Business.
                </p>
              )}

              {meta?.registered && meta?.can_manage_meta_account && (
                <div className="mt-3 pt-3 border-t border-emerald-200">
                  <button
                    onClick={handleDisconnect}
                    disabled={disconnecting}
                    className="text-xs text-red-600 hover:text-red-800 font-medium disabled:opacity-50"
                  >
                    {disconnecting ? 'Desconectando...' : 'Desconectar cuenta'}
                  </button>
                </div>
              )}

              {!meta?.registered && (
                <div className="mt-2">
                  {meta?.can_manage_meta_account ? (
                    <button
                      onClick={openConnectModal}
                      className="w-full bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium py-2 px-3 rounded-lg transition-colors"
                    >
                      Conectar WhatsApp
                    </button>
                  ) : (
                    <p className="text-xs text-gray-500 mt-1">
                      Pide al propietario del equipo que conecte la cuenta de WhatsApp Business.
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-sm text-gray-500">Nombre</label>
                <p className="text-gray-800 font-medium">{user.nombre}</p>
              </div>
              <div>
                <label className="text-sm text-gray-500">Correo</label>
                <p className="text-gray-800 font-medium">{user.correo}</p>
              </div>
              <div>
                <label className="text-sm text-gray-500">Documento</label>
                <p className="text-gray-800 font-medium">
                  {user.tipo_documento}: {user.documento}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-gray-400">Inicia sesión para ver tus datos</p>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-2">
              Conectar WhatsApp Business
            </h2>
            <p className="text-xs text-gray-500 mb-4">
              Pega los 3 datos de tu cuenta de Meta. El token se cifrará antes de guardarse
              y no se mostrará nunca más.
            </p>

            <form onSubmit={handleSubmit} className="space-y-3" autoComplete="off">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Phone Number ID
                </label>
                <input
                  type="text"
                  value={form.phone_number_id}
                  onChange={(e) => setForm({ ...form, phone_number_id: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="1057839004082880"
                  required
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  WABA ID
                </label>
                <input
                  type="text"
                  value={form.waba_id}
                  onChange={(e) => setForm({ ...form, waba_id: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="1272393681746114"
                  required
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Access Token (permanente)
                </label>
                <input
                  type="password"
                  value={form.access_token}
                  onChange={(e) => setForm({ ...form, access_token: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="EAA..."
                  required
                  autoComplete="off"
                  spellCheck={false}
                  data-lpignore="true"
                  data-form-type="other"
                />
              </div>

              {formError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg p-2">
                  {formError}
                </div>
              )}

              <div className="bg-blue-50 border border-blue-200 text-blue-700 text-xs rounded-lg p-2">
                🔒 Tu token se cifrará con Fernet antes de guardarse en la base de datos.
                No se mostrará nunca más. Si necesitas cambiarlo, tendrás que desconectar
                y volver a conectar.
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeConnectModal}
                  disabled={submitting}
                  className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium py-2 px-3 rounded-lg transition-colors disabled:opacity-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium py-2 px-3 rounded-lg transition-colors disabled:opacity-50"
                >
                  {submitting ? 'Validando...' : 'Conectar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Layout>
  );
}
