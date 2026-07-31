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

// Sprint 21 #284: "Citas" es un módulo interno de Gloma (las demos que agenda
// su bot institucional). El backend ya bloquea `/citas` con 403 para las demás
// cuentas; esto solo evita mostrar una pestaña que no les sirve.
const CITAS_ITEM = { name: 'Citas', path: '/citas', icon: '📅' };
const GLOMA_DOMAIN = '@glomabeauty.com';

export default function Sidebar() {
  const router = useRouter();
  const [esGloma, setEsGloma] = useState(false);

  useEffect(() => {
    let cancelado = false;
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (!token) return;
    fetch('/api/usuario/me', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => {
        if (!cancelado && u?.correo) {
          setEsGloma(String(u.correo).toLowerCase().endsWith(GLOMA_DOMAIN));
        }
      })
      .catch(() => {
        /* no-op: si falla, simplemente no se muestra el módulo interno */
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const items = esGloma ? [...menu, CITAS_ITEM] : menu;

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
