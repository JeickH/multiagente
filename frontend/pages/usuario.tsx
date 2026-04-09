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
}

export default function Usuario() {
  const [user, setUser] = useState<UserData | null>(null);
  const [meta, setMeta] = useState<MetaAccountStatus | null>(null);
  const [loading, setLoading] = useState(true);

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
                  Sin cuenta de Meta registrada. Contacta al administrador para
                  conectar un número de WhatsApp Business.
                </p>
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
    </Layout>
  );
}
