import '../styles/globals.css';
import type { AppProps } from 'next/app';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

const publicPages = ['/login', '/register'];

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token && !publicPages.includes(router.pathname)) {
      router.replace('/login');
    } else {
      setReady(true);
    }
  }, [router.pathname]);

  if (!ready && !publicPages.includes(router.pathname)) {
    return null;
  }

  return <Component {...pageProps} />;
}
