import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { Portfolio, Position } from '../api/types';
import { ChartPanel } from '../components/Chart';
import { Metadata, QueryState } from '../components/Shell';
import { Button, ConfirmDialog, Modal, useToast } from '../components/ui';
import { SymbolSearch } from '../components/SymbolSearch';
import { useAuth } from '../auth';
import { number, percent, totalBps, validatePositions } from '../lib';

type Draft = { id?: string; name: string; positions: Position[]; revision?: number };
type MemoryDraft = { ownerId: string; draft: Draft };
type PortfolioList = Awaited<ReturnType<typeof api.portfolios>>;
type PortfolioAnalytics = Awaited<ReturnType<typeof api.portfolioAnalytics>>;

const DRAFT_PREFIX = 'quant-stock:portfolio-draft:';
let memoryDraft: MemoryDraft | undefined;

const storageKey = (ownerId: string) => DRAFT_PREFIX + ownerId;
const clone = (portfolio: Portfolio): Draft => ({
  id: portfolio.id,
  name: portfolio.name,
  positions: portfolio.positions.map(position => ({ ...position })),
  revision: portfolio.revision,
});

function parseDraft(value: string | null): Draft | undefined {
  if (!value) return undefined;
  try {
    const draft = JSON.parse(value) as Partial<Draft>;
    if (typeof draft.name !== 'string' || !Array.isArray(draft.positions)) return undefined;
    if (draft.id != null && typeof draft.id !== 'string') return undefined;
    if (draft.revision != null && (!Number.isInteger(draft.revision) || draft.revision < 1)) return undefined;
    if (draft.positions.some(position => !position || typeof position.symbol !== 'string'
      || !Number.isInteger(position.weight_bps))) return undefined;
    return {
      ...(draft.id ? { id: draft.id } : {}),
      name: draft.name,
      positions: draft.positions.map(position => ({ symbol: position.symbol, weight_bps: position.weight_bps })),
      ...(draft.revision ? { revision: draft.revision } : {}),
    };
  } catch {
    return undefined;
  }
}

function savedDraftError(draft: Draft): string | null {
  if (!draft.name.trim()) return 'Give the portfolio a name.';
  if (!draft.positions.length) return 'Add at least one position before saving.';
  if (draft.positions.length > 30) return 'A portfolio can hold at most 30 positions.';
  if (new Set(draft.positions.map(position => position.symbol)).size !== draft.positions.length) {
    return 'Each symbol may appear once.';
  }
  if (draft.positions.some(position => !position.symbol || !Number.isInteger(position.weight_bps)
    || position.weight_bps < 0 || position.weight_bps > 10_000)) {
    return 'Weights must be whole basis points from 0 to 10,000.';
  }
  return null;
}

export const clearMemoryDraft = () => {
  memoryDraft = undefined;
  for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = sessionStorage.key(index);
    if (key?.startsWith(DRAFT_PREFIX)) sessionStorage.removeItem(key);
  }
};

function DraftEditor({ draft, setDraft, onRun, busy }: {
  draft: Draft;
  setDraft: (draft: Draft) => void;
  onRun: () => void;
  busy: boolean;
}) {
  const total = totalBps(draft.positions);
  const analysisError = validatePositions(draft.positions);
  const add = (symbol: string) => {
    if (!symbol || draft.positions.some(position => position.symbol === symbol) || draft.positions.length >= 30) return;
    setDraft({ ...draft, positions: [...draft.positions, { symbol, weight_bps: 0 }] });
  };
  const update = (index: number, value: string) => setDraft({
    ...draft,
    positions: draft.positions.map((position, positionIndex) => (
      positionIndex === index ? { ...position, weight_bps: Number(value) } : position
    )),
  });
  const remove = (index: number) => setDraft({
    ...draft,
    positions: draft.positions.filter((_, positionIndex) => positionIndex !== index),
  });

  return <section className="panel panel-pad">
    <div className="context-row" style={{ justifyContent: 'space-between' }}>
      <h2>Holdings editor</h2>
      <span className={total === 10_000 ? 'status' : 'status stale'}>{(total / 100).toFixed(2)}%</span>
    </div>
    <form noValidate onSubmit={event => { event.preventDefault(); if (!analysisError) onRun(); }}>
      <div className="field">
        <label htmlFor="portfolio-name">Portfolio name</label>
        <input id="portfolio-name" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })}
          maxLength={100} aria-invalid={!draft.name.trim()} />
      </div>
      <div style={{ margin: '14px 0' }}><SymbolSearch value="" onPick={add} /></div>
      {draft.positions.map((position, index) => <div className="holdings-row" key={position.symbol}>
        <div className="field">
          <label htmlFor={`symbol-${position.symbol}`}>Symbol</label>
          <input id={`symbol-${position.symbol}`} value={position.symbol} readOnly aria-label={`${position.symbol} symbol`} />
        </div>
        <div className="field">
          <label htmlFor={`weight-${position.symbol}`}>Weight (bps)</label>
          <input id={`weight-${position.symbol}`} inputMode="numeric" type="number" min="0" max="10000" step="1"
            value={position.weight_bps} onChange={event => update(index, event.target.value)}
            aria-invalid={position.weight_bps < 0 || position.weight_bps > 10_000 || !Number.isInteger(position.weight_bps)} />
        </div>
        <Button className="ghost danger" aria-label={`Remove ${position.symbol}`} onClick={() => remove(index)}>
          <Trash2 size={16} />
        </Button>
      </div>)}
      {analysisError && <p className="notice error" role="alert">{analysisError}</p>}
      <Button className="primary" disabled={!!analysisError || busy} type="submit">
        {busy ? 'Running…' : 'Run portfolio analysis'}
      </Button>
    </form>
  </section>;
}

function AnalyticsView({ data, revision }: { data: PortfolioAnalytics; revision: string }) {
  const colors = ['#7CAEFF', '#3DD6A0', '#F4C66A', '#FF7B72', '#c898e7', '#61c3e5'];
  const sectorDetails = data.sectors.map(sector => sector.holdings
    .map(holding => `${holding.symbol} ${(holding.weight_bps / 100).toFixed(2)}%`).join('<br>'));
  return <div className="grid">
    <section className="panel panel-pad">
      <h2>Portfolio analytics <small>1Y vs S&amp;P 500</small></h2>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(4,minmax(0,1fr))' }}>
        {[
          ['Expected return', percent(data.metrics.expected_return)],
          ['Volatility', percent(data.metrics.volatility)],
          ['Sharpe', number(data.metrics.sharpe)],
          ['Beta', number(data.metrics.beta)],
        ].map(([label, value]) => <div className="metric" key={String(label)}>
          <div className="label">{label}</div><div className="value mono">{value}</div>
        </div>)}
      </div>
    </section>
    <ChartPanel title="Allocation by GICS sector" data={[{
      type: 'pie', labels: data.sectors.map(sector => sector.sector),
      values: data.sectors.map(sector => sector.weight_bps), hole: .58,
      marker: { colors }, textinfo: 'label+percent', customdata: sectorDetails,
      hovertemplate: '%{label}<br>%{percent}<br>%{customdata}<extra></extra>',
    }] as any} layout={{ height: 310 }}
      summary={data.sectors.map(sector => `${sector.sector} ${(sector.weight_bps / 100).toFixed(2)}%`).join('; ')}
      meta={data.meta} revision={`${revision}:allocation`}>
      <div className="table-wrap"><table className="chart-table">
        <thead><tr><th>Sector</th><th>Weight</th><th>Holdings</th></tr></thead>
        <tbody>{data.sectors.map(sector => <tr key={sector.sector}>
          <th>{sector.sector}</th><td>{(sector.weight_bps / 100).toFixed(2)}%</td>
          <td>{sector.holdings.map(holding => `${holding.symbol} ${(holding.weight_bps / 100).toFixed(2)}%`).join(', ')}</td>
        </tr>)}</tbody>
      </table></div>
    </ChartPanel>
    <ChartPanel title="Performance vs S&P 500" subtitle="1Y cumulative return" data={[
      { type: 'scatter', mode: 'lines', name: 'Portfolio', x: data.performance.map(point => point.time), y: data.performance.map(point => point.portfolio), line: { color: '#7CAEFF' } },
      { type: 'scatter', mode: 'lines', name: 'S&P 500', x: data.performance.map(point => point.time), y: data.performance.map(point => point.benchmark), line: { color: '#9AAEC6' } },
    ] as any} layout={{ height: 290, showlegend: true, yaxis: { tickformat: '.0%' } }}
      summary="Cumulative portfolio and S&P 500 returns over the same complete-observation lookback window."
      meta={data.meta} revision={`${revision}:performance`} />
    <Metadata meta={data.meta} />
  </div>;
}

export function PortfolioPage() {
  const { auth } = useAuth();
  const ownerId = auth?.user.id ?? '';
  const draftKey = ownerId ? storageKey(ownerId) : '';
  const queryClient = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ['portfolios'], queryFn: api.portfolios });
  const [draft, setDraftState] = useState<Draft>();
  const [initializedOwner, setInitializedOwner] = useState('');
  const [selected, setSelected] = useState<string>();
  const [analytics, setAnalytics] = useState<PortfolioAnalytics>();
  const [analysisRevision, setAnalysisRevision] = useState('portfolio-analysis');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const [actionError, setActionError] = useState('');
  const [conflictReloading, setConflictReloading] = useState(false);
  const createRequest = useRef<{ fingerprint: string; key: string } | undefined>(undefined);

  useEffect(() => {
    if (!ownerId) return;
    if (memoryDraft && memoryDraft.ownerId !== ownerId) {
      sessionStorage.removeItem(storageKey(memoryDraft.ownerId));
      memoryDraft = undefined;
    }
    const stored = memoryDraft?.ownerId === ownerId ? memoryDraft.draft : parseDraft(sessionStorage.getItem(draftKey));
    if (stored) {
      memoryDraft = { ownerId, draft: stored };
      setDraftState(stored);
      setSelected(stored.id);
    } else {
      sessionStorage.removeItem(draftKey);
      setDraftState(undefined);
      setSelected(undefined);
    }
    setAnalytics(undefined);
    setInitializedOwner(ownerId);
  }, [draftKey, ownerId]);

  const setDraft = (next: Draft | undefined, preserveAnalytics = false) => {
    memoryDraft = next && ownerId ? { ownerId, draft: next } : undefined;
    setDraftState(next);
    if (!preserveAnalytics) setAnalytics(undefined);
    if (draftKey) {
      if (next) sessionStorage.setItem(draftKey, JSON.stringify(next));
      else sessionStorage.removeItem(draftKey);
    }
  };

  useEffect(() => {
    if (initializedOwner !== ownerId || draft || !list.data?.items[0]) return;
    const first = list.data.items[0];
    setSelected(first.id);
    setDraft(clone(first));
  }, [draft, initializedOwner, list.data, ownerId]);

  const saved = draft?.id ? list.data?.items.find(portfolio => portfolio.id === draft.id) : undefined;
  const isDirty = !!draft && (draft.id
    ? !saved || JSON.stringify(clone(saved)) !== JSON.stringify(draft)
    : draft.name !== 'New portfolio' || draft.positions.length > 0);

  const updateList = (portfolio: Portfolio) => queryClient.setQueryData<PortfolioList>(['portfolios'], current => {
    if (!current) return { items: [portfolio] };
    const exists = current.items.some(item => item.id === portfolio.id);
    return { items: exists ? current.items.map(item => item.id === portfolio.id ? portfolio : item) : [portfolio, ...current.items] };
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['portfolios'] });
  const errorMessage = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback;

  const save = useMutation<Portfolio, Error, boolean>({
    mutationFn: async (copy = false) => {
      if (!draft) throw new Error('No portfolio draft.');
      const error = savedDraftError(draft);
      if (error) throw new Error(error);
      if (copy || !draft.id) {
        const name = copy ? `${draft.name} copy` : draft.name;
        const fingerprint = JSON.stringify({ name, positions: draft.positions });
        if (!createRequest.current || createRequest.current.fingerprint !== fingerprint) {
          createRequest.current = { fingerprint, key: crypto.randomUUID() };
        }
        return api.createPortfolio(name, draft.positions, createRequest.current.key);
      }
      return api.updatePortfolio(draft.id, draft.name, draft.positions, draft.revision!);
    },
    onMutate: () => setActionError(''),
    onSuccess: portfolio => {
      createRequest.current = undefined;
      updateList(portfolio);
      setSelected(portfolio.id);
      setDraft(clone(portfolio), true);
      void invalidate();
      toast.push('Portfolio saved.');
      setConflict(false);
    },
    onError: error => {
      if (error instanceof ApiError && error.status === 409) {
        setConflict(true);
        return;
      }
      const message = errorMessage(error, 'Portfolio could not be saved.');
      setActionError(message);
      toast.push(message, 'error');
    },
  });

  const run = useMutation({
    mutationFn: async () => {
      if (!draft) throw new Error('No draft.');
      const error = validatePositions(draft.positions);
      if (error) throw new Error(error);
      return api.portfolioAnalytics(draft.positions);
    },
    onMutate: () => setActionError(''),
    onSuccess: result => {
      setAnalytics(result);
      setAnalysisRevision(`portfolio-analysis:${crypto.randomUUID()}`);
    },
    onError: error => {
      const message = errorMessage(error, 'Analysis could not run.');
      setActionError(message);
      toast.push(message, 'error');
    },
  });

  const applySelect = (id: string) => {
    const portfolio = list.data?.items.find(item => item.id === id);
    if (!portfolio) return;
    setSelected(id);
    setDraft(clone(portfolio));
    setActionError('');
  };
  const beginNew = () => {
    setDraft({ name: 'New portfolio', positions: [] });
    setSelected(undefined);
    setActionError('');
  };
  const reloadSaved = () => {
    if (!saved) return;
    setDraft(clone(saved));
    setSelected(saved.id);
    setActionError('');
  };
  const confirmDiscard = (action: () => void) => {
    if (!isDirty) { action(); return; }
    setPendingAction(() => action);
    setDiscardOpen(true);
  };

  const removeFromList = (id: string) => queryClient.setQueryData<PortfolioList>(['portfolios'], current => (
    current ? { items: current.items.filter(item => item.id !== id) } : current
  ));
  const doDelete = useMutation({
    mutationFn: () => api.deletePortfolio(draft!.id!, draft!.revision!),
    onMutate: () => setActionError(''),
    onSuccess: () => {
      const deletedId = draft!.id!;
      removeFromList(deletedId);
      toast.push('Portfolio deleted.');
      setDraft(undefined);
      setSelected(undefined);
      void invalidate();
      setDeleteOpen(false);
    },
    onError: error => {
      const message = errorMessage(error, 'Portfolio could not be deleted.');
      setActionError(message);
      toast.push(message, 'error');
    },
  });

  const reloadConflict = async () => {
    if (!draft?.id) return;
    setConflictReloading(true);
    setActionError('');
    try {
      const portfolio = await api.portfolio(draft.id);
      updateList(portfolio);
      setDraft(clone(portfolio));
      setSelected(portfolio.id);
      setConflict(false);
    } catch (error) {
      setActionError(errorMessage(error, 'Latest saved portfolio could not be loaded.'));
    } finally {
      setConflictReloading(false);
    }
  };

  return <>
    <header className="page-head">
      <div><h1>Portfolio</h1><p>Private saved portfolios and explicit 1-year simulation</p></div>
      <div className="toolbar">
        <Button onClick={() => confirmDiscard(beginNew)}><Plus size={15} /> New portfolio</Button>
        {draft?.id && <Button className="danger" onClick={() => setDeleteOpen(true)}>Delete</Button>}
      </div>
    </header>
    {actionError && <p className="notice error" role="alert">{actionError}</p>}
    <QueryState loading={list.isLoading} error={list.data ? null : list.error} retry={() => list.refetch()}>
      {list.data && <>
        <div className="toolbar" style={{ marginBottom: 14 }}>
          <label className="field"><span>Saved portfolio</span>
            <select className="select-trigger" value={selected || ''} onChange={event => confirmDiscard(() => applySelect(event.target.value))}>
              {!selected && <option value="" disabled>Unsaved draft</option>}
              {list.data.items.map(portfolio => <option key={portfolio.id} value={portfolio.id}>{portfolio.name}</option>)}
            </select>
          </label>
          {isDirty && <span className="notice">Unsaved changes in this browser tab.</span>}
        </div>
        {draft ? <div className="grid portfolio-layout">
          <DraftEditor draft={draft} setDraft={setDraft} onRun={() => run.mutate()} busy={run.isPending} />
          <div className="grid">
            <section className="panel panel-pad">
              <h2>Saved copy</h2>
              <p className="note">Incomplete allocations can be saved as drafts. Analysis requires weights totaling 100.00%.</p>
              <div className="toolbar">
                <Button className="primary" disabled={save.isPending || !!savedDraftError(draft)} onClick={() => save.mutate(false)}>
                  {save.isPending ? 'Saving…' : 'Save changes'}
                </Button>
                <Button onClick={() => confirmDiscard(reloadSaved)} disabled={!draft.id}>Reload saved</Button>
              </div>
            </section>
            {analytics ? <AnalyticsView data={analytics} revision={analysisRevision} />
              : <section className="panel empty">Run analysis after weights total 100.00%.</section>}
          </div>
        </div> : <section className="panel empty"><div>
          <p>No saved portfolios yet.</p>
          <Button className="primary" onClick={beginNew}>Create portfolio</Button>
        </div></section>}
      </>}
    </QueryState>
    <ConfirmDialog open={discardOpen} onOpenChange={open => { setDiscardOpen(open); if (!open) setPendingAction(null); }}
      title="Discard unsaved changes?" description="This replaces the recoverable draft in this browser tab."
      confirm="Discard changes" onConfirm={() => { pendingAction?.(); setPendingAction(null); setDiscardOpen(false); }} />
    <ConfirmDialog open={deleteOpen} onOpenChange={setDeleteOpen} title={`Delete ${draft?.name || 'portfolio'}?`}
      description="This permanently removes the saved portfolio for your account." confirm="Delete portfolio"
      onConfirm={() => { if (!doDelete.isPending) doDelete.mutate(); }} />
    <Modal open={conflict} onOpenChange={setConflict} title="Portfolio changed elsewhere">
      <p className="note">Your draft is preserved. Reload replaces it with the latest saved version; Save as copy preserves your changes as a separate private portfolio.</p>
      <div className="toolbar" style={{ marginTop: 18 }}>
        <Button disabled={conflictReloading} onClick={reloadConflict}>{conflictReloading ? 'Reloading…' : 'Reload'}</Button>
        <Button className="primary" disabled={save.isPending} onClick={() => save.mutate(true)}>Save as copy</Button>
      </div>
    </Modal>
  </>;
}
