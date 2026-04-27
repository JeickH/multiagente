import Image from 'next/image';
import { useState } from 'react';
import { useRouter } from 'next/router';

export default function Register() {
  const router = useRouter();
  const [form, setForm] = useState({
    nombre: '', tipo_documento: '', documento: '', correo: '', password: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Error al registrar');
      }
      router.push('/login');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gloma-cream py-10">
      <div className="flex flex-col items-center mb-6">
        <Image
          src="/gloma/logo_gloma_original_trans.png"
          alt="Gloma"
          width={320}
          height={400}
          priority
          className="object-contain h-32 w-auto"
        />
      </div>
      <div className="bg-gloma-brown rounded-3xl shadow-2xl px-10 py-10 flex flex-col items-center w-full max-w-md">
        <h1 className="font-heading text-white text-3xl font-bold mb-8 text-center drop-shadow">Registro de usuario</h1>
        <form className="flex flex-col gap-4 w-full" onSubmit={handleSubmit}>
          <input type="text" name="nombre" placeholder="Nombre" value={form.nombre} onChange={handleChange} required
            className="w-full rounded-full px-6 py-3 bg-white text-gloma-brown font-semibold placeholder-gloma-brown-light focus:outline-none focus:ring-2 focus:ring-gloma-rose text-center shadow" />
          <input type="text" name="tipo_documento" placeholder="Tipo de documento" value={form.tipo_documento} onChange={handleChange} required
            className="w-full rounded-full px-6 py-3 bg-white text-gloma-brown font-semibold placeholder-gloma-brown-light focus:outline-none focus:ring-2 focus:ring-gloma-rose text-center shadow" />
          <input type="text" name="documento" placeholder="Documento" value={form.documento} onChange={handleChange} required
            className="w-full rounded-full px-6 py-3 bg-white text-gloma-brown font-semibold placeholder-gloma-brown-light focus:outline-none focus:ring-2 focus:ring-gloma-rose text-center shadow" />
          <input type="email" name="correo" placeholder="Correo electrónico" value={form.correo} onChange={handleChange} required
            className="w-full rounded-full px-6 py-3 bg-white text-gloma-brown font-semibold placeholder-gloma-brown-light focus:outline-none focus:ring-2 focus:ring-gloma-rose text-center shadow" />
          <input type="password" name="password" placeholder="Contraseña" value={form.password} onChange={handleChange} required
            className="w-full rounded-full px-6 py-3 bg-white text-gloma-brown font-semibold placeholder-gloma-brown-light focus:outline-none focus:ring-2 focus:ring-gloma-rose text-center shadow" />
          {error && <p className="text-red-200 text-sm text-center">{error}</p>}
          <button type="submit" disabled={loading}
            className="w-full rounded-full bg-gloma-rose text-gloma-brown font-bold text-lg py-3 mt-2 shadow hover:bg-white transition-colors disabled:opacity-50">
            {loading ? 'Registrando...' : 'Registrar'}
          </button>
        </form>
        <a href="/login" className="text-gloma-rose-soft text-sm mt-4 hover:text-white transition-colors">
          ¿Ya tienes cuenta? Inicia sesión
        </a>
      </div>
    </div>
  );
}
