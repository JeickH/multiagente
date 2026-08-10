import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

const menu = [
  { name: 'Mensajes', path: '/mensajes', icon: '💬' },
  { name: 'Campañas', path: '/campanas', icon: '📢' },
  { name: 'Bots', path: '/bots', icon: '🤖' },
  { name: 'Mi Plan', path: '/usuario', icon: '👤' },
];

// Sprint 21 #284/#288: módulos INTERNOS de Gloma, no del producto. Cada uno se
// muestra solo si el backend dice que ESTA sesión puede usarlo
// (`GET /<modulo>/access`), no adivinando por el correo: así el botón aparece
// únicamente en la cuenta donde funciona.
const MODULOS_INTERNOS = [
  { name: 'Citas', path: '/citas', icon: '📅', access: '/api/citas/access' },
  { name: 'Instagram', path: '/instagram', icon: '📸', access: '/api/instagram/access' },
];

export default function Sidebar() {
  const router = useRouter();
  const [internos, setInternos] = useState<typeof MODULOS_INTERNOS>([]);

  useEffect(() => {
    let cancelado = false;
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (!token) return;

    const headers = { Authorization: `Bearer ${token}` };
    Promise.all(
      MODULOS_INTERNOS.map((m) =>
        fetch(m.access, { headers })
          .then((r) => (r.ok ? r.json() : null))
          .then((res) => Boolean(res?.allowed))
          // no-op: si falla, simplemente no se muestra ese módulo interno
          .catch(() => false)
      )
    ).then((permisos) => {
      if (!cancelado) setInternos(MODULOS_INTERNOS.filter((_, i) => permisos[i]));
    });

    return () => {
      cancelado = true;
    };
  }, []);

  const items = [...menu, ...internos];

  return (
    <aside className="bg-gloma-brown text-white w-24 flex flex-col justify-between items-center py-6 min-h-screen font-body">
      {/* Logo Gloma — mismo que la landing, sin texto acompañante */}
      <div className="flex flex-col items-center mb-8">
        <Image
          src="/gloma/logo_blancotrans.png"
          alt="Gloma"
          width={160}
          height={96}
          priority
          className="object-contain h-16 w-auto"
        />
      </div>
      {/* Menú */}
      <nav className="flex flex-col gap-8 flex-1">
        {items.map((item) => (
          <Link href={item.path} key={item.name} legacyBehavior>
            <a className={`flex flex-col items-center transition-colors ${
              router.pathname === item.path
                ? 'text-white'
                : 'text-gloma-rose-soft hover:text-white'
            }`}>
              <span className="text-3xl mb-1">{item.icon}</span>
              <span className="text-xs text-center font-medium">{item.name}</span>
            </a>
          </Link>
        ))}
      </nav>
      {/* Logout */}
      <div className="flex flex-col items-center gap-1 mt-8 mb-2">
        <Link href="/login" legacyBehavior>
          <a className="flex flex-col items-center text-gloma-rose-soft hover:text-white transition-colors">
            <div className="w-10 h-10 bg-gloma-brown-darker rounded-full flex items-center justify-center">
              <span className="text-xl">🚪</span>
            </div>
            <span className="text-xs mt-1">Salir</span>
          </a>
        </Link>
      </div>
    </aside>
  );
}
