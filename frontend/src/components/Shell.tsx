import { BarChart3, BriefcaseBusiness, Landmark, LineChart, LogOut, Menu } from 'lucide-react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useAuth } from '../auth';
import { api } from '../api/client';
import { Button, Modal } from './ui';
import { clearMemoryDraft } from '../pages/Portfolio';

const routeLinks = (symbol: string) => [['/markets', 'Markets', Landmark], [`/stocks/${symbol}`, 'Stock analysis', LineChart], [`/fundamentals/${symbol}`, 'Fundamentals', BarChart3], ['/portfolio', 'Portfolio', BriefcaseBusiness]] as const;

export function Shell() {
  const { auth, setAuth } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [offline, setOffline] = useState(!navigator.onLine);
  useEffect(() => { const update = () => setOffline(!navigator.onLine); window.addEventListener('online', update); window.addEventListener('offline', update); return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); }; }, []);
  const routeSymbol = location.pathname.match(/\/(?:stocks|fundamentals)\/([^/]+)/)?.[1]?.toUpperCase();
  const [symbol, setSymbol] = useState(() => sessionStorage.getItem('quant-stock:last-symbol') || 'AAPL');

  useEffect(() => {
    if (routeSymbol) {
      sessionStorage.setItem('quant-stock:last-symbol', routeSymbol);
      setSymbol(routeSymbol);
    }
  }, [routeSymbol]);

  const logout = async () => {
    try { await api.logout(); } finally {
      client.clear();
      clearMemoryDraft();
      setAuth(null);
      if (auth?.mode === 'demo') nav('/markets'); else window.location.assign('/oauth2/sign_out');
    }
  };

  return <div className={`app-shell ${collapsed ? 'is-collapsed' : ''}`}><aside className="sidebar"><Nav symbol={symbol} /><Button className="ghost" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => setCollapsed(value => !value)}><Menu size={16} /> {collapsed ? 'Expand' : 'Collapse'}</Button><div className="user-box">{auth && <><strong>{auth.user.name}</strong><br />{auth.mode === 'demo' ? 'Demo session' : auth.user.email}<Button className="ghost" onClick={logout}><LogOut size={14} /> Sign out</Button></>}</div></aside><header className="mobile-header"><NavLink className="brand" to="/markets">Quant Stock</NavLink><Button className="ghost" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={18} /></Button></header><Modal open={mobileOpen} onOpenChange={setMobileOpen} title="Navigate"><Nav symbol={symbol} onNavigate={() => setMobileOpen(false)} />{auth && <Button onClick={logout}><LogOut size={15} /> Sign out</Button>}</Modal><main>{offline && <p className="notice offline-notice" role="status">You are offline. Last loaded observations and portfolio drafts remain available. Reconnect to refresh or save.</p>}<Outlet /></main></div>;
}

function Nav({ symbol, onNavigate }: { symbol: string; onNavigate?: () => void }) {
  return <><NavLink className="brand" to="/markets" onClick={onNavigate}>Quant Stock<small>Private investment research</small></NavLink><nav className="nav" aria-label="Primary navigation">{routeLinks(symbol).map(([to, label, Icon]) => <NavLink key={label} to={to} onClick={onNavigate} className={({ isActive }) => isActive ? 'active' : ''}><Icon size={16} />{label}</NavLink>)}</nav></>;
}

export function Metadata({ meta }: { meta: { source: string; as_of: string | null; currency?: string | null; status: string; notes: string[] } }) {
  const observed = meta.as_of && Number.isFinite(new Date(meta.as_of).getTime()) ? new Date(meta.as_of).toLocaleString('en-US', { timeZone: 'UTC' }) + ' UTC' : meta.as_of || '—';
  return <div className="research-strip"><span><strong>Source</strong> {meta.source}</span><span><strong>Observed</strong> {observed}</span>{meta.currency && <span><strong>Currency</strong> {meta.currency}</span>}<span className={`status ${meta.status}`}>{meta.status === 'demo' ? 'Demo data' : meta.status}</span>{meta.notes?.map(note => <span key={note}>{note}</span>)}</div>;
}

export function QueryState({ loading, error, retry, children, hasData = false }: { loading: boolean; error: unknown; retry: () => void; children: React.ReactNode; hasData?: boolean }) {
  if (loading && !hasData) return <div className="panel empty research-loading" role="status" aria-busy="true">Loading research…</div>;
  const message = error instanceof Error ? error.message : 'Try again.';
  if (error && !hasData) return <div className="panel empty research-loading"><div><strong>Research could not be loaded.</strong><p className="note">{message}</p><Button onClick={retry}>Retry</Button></div></div>;
  return <>{error && <div className="notice" role="status">Refresh failed. The last valid observations remain visible. {message} <Button onClick={retry}>Retry</Button></div>}{children}</>;
}
