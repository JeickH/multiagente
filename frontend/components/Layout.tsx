import Sidebar from './Sidebar';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-gradient-to-br from-green-50 to-white">
      <Sidebar />
      <main className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-2xl bg-white rounded-xl shadow-xl border border-green-600 p-8 min-h-[60vh] flex flex-col justify-center items-center font-sans">
          {children}
        </div>
      </main>
    </div>
  );
}
