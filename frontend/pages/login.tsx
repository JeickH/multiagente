import { useState } from 'react';
import { useRouter } from 'next/router';

export default function Login() {
  const router = useRouter();
  const [correo, setCorreo] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ correo, password }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Error al iniciar sesión');
      }

      const data = await res.json();
      localStorage.setItem('token', data.access_token);
      router.push('/');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-br from-green-100 to-green-50">
      <div className="flex flex-col items-center mb-6">
        <span className="text-6xl mb-2">💬</span>
        <h2 className="text-2xl font-bold text-green-700">Multiagente</h2>
      </div>
      <div className="bg-green-600 rounded-3xl shadow-2xl px-10 py-10 flex flex-col items-center w-full max-w-md">
        <h1 className="text-white text-3xl font-bold mb-8 text-center drop-shadow">Iniciar Sesión</h1>
        <form className="flex flex-col gap-6 w-full" onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Correo electrónico"
            value={correo}
            onChange={(e) => setCorreo(e.target.value)}
            required
            className="w-full rounded-full px-6 py-3 bg-white text-green-700 font-semibold placeholder-green-300 focus:outline-none focus:ring-2 focus:ring-green-300 text-center shadow"
          />
          <input
            type="password"
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full rounded-full px-6 py-3 bg-white text-green-700 font-semibold placeholder-green-300 focus:outline-none focus:ring-2 focus:ring-green-300 text-center shadow"
          />
          {error && (
            <p className="text-red-200 text-sm text-center">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-full bg-white text-green-600 font-bold text-lg py-3 mt-2 shadow hover:bg-green-50 transition-colors disabled:opacity-50"
          >
            {loading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>
        <a href="/register" className="text-green-200 text-sm mt-4 hover:text-white transition-colors">
          ¿No tienes cuenta? Regístrate
        </a>
      </div>
    </div>
  );
}
