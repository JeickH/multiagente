import Layout from '../components/Layout';
import { useEffect, useState } from 'react';

interface UserData {
  id: number;
  nombre: string;
  correo: string;
  tipo_documento: string;
  documento: string;
}

export default function Usuario() {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }

    fetch('/api/usuario/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.ok ? res.json() : Promise.reject())
      .then((data) => setUser(data))
      .catch(() => setUser(null))
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
                <p className="text-gray-800 font-medium">{user.tipo_documento}: {user.documento}</p>
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
