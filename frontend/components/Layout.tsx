import Sidebar from './Sidebar';

/**
 * Marco de la plataforma: menú lateral fijo + contenido.
 *
 * Las tres variantes existen porque hay tres formas distintas de scrollear, y
 * mezclarlas fue justamente el bug: `fullscreen` decía `min-h-screen` y
 * `overflow-hidden` a la vez, que se anulan. El hijo `flex-1 overflow-y-auto`
 * nunca tenía altura acotada, así que crecía en vez de scrollear, la página
 * entera se estiraba y el menú lateral se estiraba con ella.
 *
 *   centered   → una tarjeta centrada (Mi Plan, home).
 *   fullscreen → el ancho completo y la VENTANA scrollea, como cualquier página
 *                web. Es el default para paneles y listados.
 *   app        → altura clavada al viewport y scroll interno de cada panel.
 *                Solo para `/mensajes`, que es un chat de dos columnas donde la
 *                lista y la conversación scrollean por separado.
 *
 * El menú es `sticky` en las tres: se queda quieto mientras el contenido baja.
 */

type LayoutProps = {
  children: React.ReactNode;
  variant?: 'centered' | 'fullscreen' | 'app';
};

export default function Layout({ children, variant = 'centered' }: LayoutProps) {
  const esApp = variant === 'app';
  return (
    <div
      className={`flex bg-gloma-cream ${
        esApp ? 'h-screen overflow-hidden' : 'min-h-screen'
      }`}
    >
      <Sidebar />
      {variant === 'centered' ? (
        <main className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-2xl bg-white rounded-xl shadow-xl border border-gloma-rose p-8 min-h-[60vh] flex flex-col justify-center items-center font-body">
            {children}
          </div>
        </main>
      ) : (
        <main
          className={`flex-1 flex flex-col font-sans min-w-0 ${
            esApp ? 'h-screen overflow-hidden' : ''
          }`}
        >
          {children}
        </main>
      )}
    </div>
  );
}
