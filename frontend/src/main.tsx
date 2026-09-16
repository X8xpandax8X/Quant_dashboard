import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import './styles/tokens.css';
import type { Auth } from './api/types';
import { api, ApiError } from './api/client';
import { Shell } from './components/Shell';
import { Button, ToastProvider } from './components/ui';
import { MarketsPage } from './pages/Markets';
import { StockPage } from './pages/Stock';
import { FundamentalsPage } from './pages/Fundamentals';
import { PortfolioPage } from './pages/Portfolio';

import { AuthContext, useAuth } from './auth';

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: true, retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2 } } });

function Login() {
  const { setAuth } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const demo = async () => { setBusy(true); setError(''); try { setAuth(await api.demo()); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Demo sign-in is unavailable.'); } finally { setBusy(false); } };
  return <div className="login"><section className="panel"><h1>Private investment research</h1><p className="note">This workspace is limited to the approved team.</p>{error && <p className="notice error" role="alert">{error}</p>}<div className="toolbar" style={{ marginTop: 20 }}><a className="btn primary" href="/oauth2/start">Sign in with Google</a><Button onClick={demo} disabled={busy}>{busy ? 'Opening demo…' : 'Explore demo'}</Button></div><p className="note">Demo is available only when this deployment enables illustrative data.</p></section></div>;
}

function Gate({ children }: { children: ReactNode }) { const { auth } = useAuth(); return auth === undefined ? <div className="login"><div className="panel empty" aria-busy="true">Checking your session…</div></div> : auth ? <>{children}</> : <Login />; }

function AppContent() {
  const me = useQuery({ queryKey: ['auth'], queryFn: api.me, retry: false });
  const [auth, setAuth] = useState<Auth | null | undefined>(undefined);
  useEffect(() => { if (me.isSuccess) setAuth(me.data); if (me.isError) setAuth(null); }, [me.data, me.isError, me.isSuccess]);
  useEffect(() => { const expired = () => { client.clear(); setAuth(null); }; window.addEventListener('quant-stock:session-expired', expired); return () => window.removeEventListener('quant-stock:session-expired', expired); }, []);
  const value = useMemo(() => ({ auth, setAuth }), [auth]);
  return <AuthContext.Provider value={value}><ToastProvider><BrowserRouter><Routes><Route element={<Gate><Shell /></Gate>}><Route path="/markets" element={<MarketsPage />} /><Route path="/stocks/:symbol" element={<StockPage />} /><Route path="/fundamentals/:symbol" element={<FundamentalsPage />} /><Route path="/portfolio" element={<PortfolioPage />} /><Route path="*" element={<Navigate to="/markets" replace />} /></Route></Routes></BrowserRouter></ToastProvider></AuthContext.Provider>;
}

function App() { return <QueryClientProvider client={client}><AppContent /></QueryClientProvider>; }
createRoot(document.getElementById('root')!).render(<App />);
