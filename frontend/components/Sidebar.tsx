import Link from 'next/link';
import { useRouter } from 'next/router';

const menu = [
  { name: 'Mensajes', path: '/mensajes', icon: '💬' },
  { name: 'Campañas', path: '/campanas', icon: '📢' },
  { name: 'Bots', path: '/bots', icon: '🤖' },
  { name: 'Mi Plan', path: '/usuario', icon: '👤' },
];

export default function Sidebar() {
  const router = useRouter();

  return (
    <aside className="bg-green-600 text-white w-24 flex flex-col justify-between items-center py-6 min-h-screen font-sans">
      {/* Logo y nombre */}
      <div className="flex flex-col items-center gap-2 mb-8">
        <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center mb-2 shadow-md">
          <span className="text-3xl text-green-600">💬</span>
        </div>
        <span className="font-bold text-xs tracking-wide">Multiagente</span>
      </div>
      {/* Menú */}
      <nav className="flex flex-col gap-8 flex-1">
        {menu.map((item) => (
          <Link href={item.path} key={item.name} legacyBehavior>
            <a className={`flex flex-col items-center transition-colors ${
              router.pathname === item.path
                ? 'text-white'
                : 'text-green-200 hover:text-white'
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
          <a className="flex flex-col items-center text-green-200 hover:text-white transition-colors">
            <div className="w-10 h-10 bg-green-800 rounded-full flex items-center justify-center">
              <span className="text-xl">🚪</span>
            </div>
            <span className="text-xs mt-1">Salir</span>
          </a>
        </Link>
      </div>
    </aside>
  );
}
