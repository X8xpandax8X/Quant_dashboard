import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { PriceResponse, Timeframe } from '../api/types';
import { ChartPanel } from '../components/Chart';
import { QueryState } from '../components/Shell';
import { Button, Timeframes } from '../components/ui';
import { money, percent, statusLabel, vixZone } from '../lib';

const frames = ['1D', '5D', '1M', '1Y'];
function Observation({ item }: { item: PriceResponse }) {
  return <div className="market-observation">
    <span className={`status ${item.meta.status}`}>{statusLabel(item.meta.status)}</span>
    <span>{item.meta.as_of ? new Date(item.meta.as_of).toLocaleString('en-US', { timeZone: 'UTC' }) + ' UTC' : 'Observation unavailable'}</span>
    <span>{item.meta.status === 'demo' ? 'Illustrative session' : 'Exchange session status unavailable'} · {item.meta.interval ?? 'No bars'}</span>
    <span>{item.meta.source}</span>
    {item.meta.status !== 'demo' && item.meta.notes.map(note => <span key={note}>{note}</span>)}
  </div>;
}
function Candle({ item, timeframe, primary }: { item: PriceResponse; timeframe: Timeframe; primary?: boolean }) {
  const bars = item.bars;
  return <section className="panel panel-pad market-card">
    <h2>{item.instrument.name}<small>{item.instrument.symbol}</small></h2>
    <div className="quote-row"><strong className="mono">{money(item.last_price, item.instrument.currency)}</strong>
      <span className={item.change != null && item.change < 0 ? 'down' : 'up'}>{percent(item.change)}<small> vs previous session</small></span>
    </div>
    <ChartPanel title={`${item.instrument.symbol} price`} subtitle={item.instrument.currency} meta={item.meta} revision={`${item.instrument.symbol}:${timeframe}`}
      data={bars.length ? [{ type: 'candlestick', x: bars.map(b => b.time), open: bars.map(b => b.open), high: bars.map(b => b.high), low: bars.map(b => b.low), close: bars.map(b => b.close), increasing: { line: { color: '#3DD6A0' } }, decreasing: { line: { color: '#FF7B72' } } }] as any : []}
      layout={{ height: primary ? 235 : 150, margin: { l: 48, r: 12, t: 8, b: 26 }, yaxis: { title: { text: item.instrument.currency } } }}
      summary={bars.length ? `${timeframe} ${item.meta.interval} candles; ${bars.length} observed bars.` : 'Price history is unavailable. Refresh to retry.'} />
    <Observation item={item} />
  </section>;
}
function Vix({ item, timeframe }: { item: PriceResponse; timeframe: Timeframe }) {
  const value = item.last_price;
  return <section className="panel panel-pad market-card">
    <h2>Volatility index <small>VIX</small></h2>
    <div className="quote-row"><strong className="mono">{value?.toFixed(1) ?? '—'}<small> points</small></strong><span>{vixZone(value)}</span></div>
    <ChartPanel title="VIX volatility gauge" meta={item.meta} revision={`VIX:${timeframe}`} subtitle="Index points"
      data={value == null ? [] : [{ type: 'indicator', mode: 'gauge', value, gauge: { axis: { range: [0, Math.max(50, value * 1.1)], tickcolor: '#9AAEC6' }, bar: { color: '#7CAEFF', thickness: 0.22 }, steps: [{ range: [0, 15], color: '#3DD6A0' }, { range: [15, 20], color: '#9AAEC6' }, { range: [20, 30], color: '#F4C66A' }, { range: [30, Math.max(50, value * 1.1)], color: '#FF7B72' }] } }] as any}
      layout={{ height: 185, margin: { l: 26, r: 26, t: 18, b: 10 } }} summary={value == null ? 'VIX observation unavailable.' : `Current zone: ${vixZone(value)}. Change ${percent(item.change)} versus previous session.`} />
    <div className="zone-labels"><span>Low &lt;15</span><span>Normal 15–20</span><span>Elevated 20–30</span><span>Extreme ≥30</span></div>
    <Observation item={item} />
  </section>;
}
export function MarketsPage() {
  const [params, setParams] = useSearchParams();
  const timeframe = (frames.includes(params.get('timeframe') || '') ? params.get('timeframe') : '1D') as Timeframe;
  const query = useQuery({ queryKey: ['markets', timeframe], queryFn: () => api.markets(timeframe), refetchInterval: () => document.visibilityState === 'visible' && ['1D', '5D'].includes(timeframe) ? 300_000 : false });
  const items = query.data?.items ?? [];
  const ordered = [...items.filter(i => i.instrument.symbol === '^GSPC'), ...items.filter(i => i.instrument.symbol === '^VIX'), ...items.filter(i => !['^GSPC', '^VIX'].includes(i.instrument.symbol))];
  return <><header className="page-head"><div><p className="eyebrow">RESEARCH DESK / GLOBAL MARKETS</p><h1>Markets</h1><p>Seven benchmarks. One view of the trading landscape.</p></div><div className="toolbar">
    <Timeframes value={timeframe} onChange={value => setParams(previous => { previous.set('timeframe', value); return previous; })} />
    <Button onClick={() => query.refetch()} disabled={query.isFetching}>{query.isFetching ? 'Refreshing…' : 'Refresh'}</Button>
  </div></header>
    <div className="research-strip"><span><strong>Window</strong> {timeframe}</span><span><strong>Refresh</strong> 5 minutes for active intraday views</span><span><strong>Price basis</strong> Split-adjusted; dividends excluded</span></div>
    <QueryState loading={query.isLoading} error={query.error} hasData={!!query.data} retry={() => query.refetch()}>
      <div className="grid markets-grid">{ordered.map(item => <div key={item.instrument.symbol} className={item.instrument.symbol === '^GSPC' ? 'span-7' : item.instrument.symbol === '^VIX' ? 'span-5' : 'span-4'}>
        {item.instrument.symbol === '^VIX' ? <Vix item={item} timeframe={timeframe} /> : <Candle item={item} timeframe={timeframe} primary={item.instrument.symbol === '^GSPC'} />}
      </div>)}</div>
      {query.data && !items.length && <div className="panel empty">No benchmark observations are available.</div>}
    </QueryState>
  </>;
}
