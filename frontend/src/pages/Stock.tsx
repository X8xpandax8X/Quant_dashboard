import { useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Analytics, PriceResponse, Timeframe } from '../api/types';
import { ChartPanel } from '../components/Chart';
import { Metadata, QueryState } from '../components/Shell';
import { AppTabs, Button, TabPanel, Timeframes } from '../components/ui';
import { SymbolSearch } from '../components/SymbolSearch';
import { money, number, percent } from '../lib';

function Calendar({ returns }: { returns: Analytics['distribution']['returns'] }) {
  const [selected, setSelected] = useState<string>();
  const observed = new Map(returns.map(point => [point.time.slice(0, 10), point.value]));
  const first = returns[0]?.time;
  const last = returns.at(-1)?.time;
  const start = new Date(first || Date.now());
  start.setUTCHours(0, 0, 0, 0); start.setUTCDate(start.getUTCDate() - start.getUTCDay());
  const count = last ? Math.floor((new Date(last).getTime() - start.getTime()) / 86400000) + 1 : 0;
  const dates = Array.from({ length: Math.ceil(count / 7) * 7 }, (_, i) => new Date(start.getTime() + i * 86400000).toISOString().slice(0, 10));
  const max = Math.max(...returns.map(point => Math.abs(point.value ?? 0)), 0.001);
  const active = selected || last?.slice(0, 10);
  return <section className="panel panel-pad"><h2>Daily return calendar <small>Trailing 1Y</small></h2>
    <div className="calendar-months" aria-hidden="true">{dates.filter((_, i) => i % 7 === 0).map((date, i, weeks) => <span key={date}>{i === 0 || date.slice(0, 7) !== weeks[i - 1].slice(0, 7) ? new Date(date).toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' }) : ''}</span>)}</div>
    <div className="calendar-with-days"><div className="weekday-labels" aria-hidden="true">{['Sun','','Tue','','Thu','','Sat'].map((label,index)=><span key={index}>{label}</span>)}</div><div className="return-calendar" aria-label="Daily return calendar; columns are weeks, rows Sunday to Saturday">
      {dates.map(date => {
        const value = observed.get(date);
        const level = value == null || value === 0 ? 0 : Math.min(3, Math.ceil(Math.abs(value) / max * 3)) * Math.sign(value);
        return value == null ? <span key={date} className="calendar-gap" aria-hidden="true" /> : <button key={date} type="button" data-date={date} tabIndex={active === date ? 0 : -1} data-level={level} onKeyDown={event => { const delta = ({ArrowLeft:-7,ArrowRight:7,ArrowUp:-1,ArrowDown:1} as Record<string,number>)[event.key]; if (!delta) return; event.preventDefault(); let index = dates.indexOf(date) + delta; while (index >= 0 && index < dates.length && observed.get(dates[index]) == null) index += Math.sign(delta); const next = dates[index]; if (next) { setSelected(next); (event.currentTarget.parentElement?.querySelector(`[data-date="${next}"]`) as HTMLElement | null)?.focus(); } }} aria-label={`${date}: ${percent(value, 2)}`} onFocus={() => setSelected(date)} onClick={() => setSelected(date)} />;
      })}
    </div></div>
    <p className="chart-caption">Columns are weeks; rows run Sunday–Saturday. Empty cells have no observation. Coral is negative, green positive; intensity is relative to the largest absolute daily return.</p>
    <p className="calendar-detail" aria-live="polite">{active ? <><strong>{active}</strong> <span className="mono">{percent(observed.get(active), 2)}</span></> : 'Daily returns unavailable.'}</p>
    <details className="table-wrap"><summary>Daily return data table</summary><table className="chart-table"><thead><tr><th>Date (UTC)</th><th>Return</th></tr></thead><tbody>{returns.map(point => <tr key={point.time}><th>{point.time.slice(0, 10)}</th><td>{percent(point.value, 2)}</td></tr>)}</tbody></table></details>
  </section>;
}
function PriceTab({ price, analytics, timeframe }: { price: PriceResponse; analytics: Analytics; timeframe: Timeframe }) {
  const d = analytics.distribution, volume = analytics.volume_profile;
  const closes = price.bars.map(bar => bar.close).filter((value): value is number => value != null);
  const totalReturn = closes.length > 1 ? closes.at(-1)! / closes[0] - 1 : null;
  return <div className="grid markets-grid">
    <div className="span-8"><ChartPanel title={`${price.instrument.symbol} price and return`} subtitle={`${timeframe} · ${price.instrument.currency}`} meta={price.meta} revision={`${price.instrument.symbol}:${timeframe}`}
      data={[{ type: 'candlestick', x: price.bars.map(b => b.time), open: price.bars.map(b => b.open), high: price.bars.map(b => b.high), low: price.bars.map(b => b.low), close: price.bars.map(b => b.close), increasing: { line: { color: '#3DD6A0' } }, decreasing: { line: { color: '#FF7B72' } } }] as any}
      layout={{ height: 370, yaxis: { title: { text: price.instrument.currency } } }} summary={`Selected-window price return: ${percent(totalReturn, 2)}. Latest ${money(price.last_price)}. Dividend-excluding, split-adjusted price basis.`} /></div>
    <div className="span-4"><ChartPanel title={`${price.instrument.symbol} volume profile`} subtitle="OHLCV approximation" meta={price.meta} revision={`${price.instrument.symbol}:${timeframe}`}
      data={volume.bins.length ? [{ type: 'bar', orientation: 'h', y: volume.bins.map(b => (b.low + b.high) / 2), x: volume.bins.map(b => b.volume), marker: { color: '#7CAEFF' } }] as any : []}
      layout={{ height: 290, xaxis: { title: { text: 'Observed volume' } }, yaxis: { title: { text: 'Price (USD)' } } }} summary={volume.total_volume == null ? 'Observed volume is unavailable.' : `Value area covers ${percent(volume.coverage)} of ${number(volume.total_volume, 0)} observed shares.`}>
      <dl className="key-levels">{[['POC', volume.poc], ['VAH', volume.vah], ['VAL', volume.val]].map(([label, value]) => <div key={label as string}><dt>{label}</dt><dd className="mono">{money(value as number | null)}</dd></div>)}</dl>
      <p className="note">{volume.notes.join(' ')}</p>
    </ChartPanel></div>
    <section className="panel panel-pad span-12"><h2>Return statistics <small>Trailing 1Y · {d.sample_count} returns</small></h2><div className="metric-grid">{[['Mean daily', percent(d.daily_mean, 2)], ['Daily volatility', percent(d.daily_volatility, 2)], ['Annual volatility', percent(d.annual_volatility)], ['Win rate', percent(d.win_rate)]].map(([label, value]) => <div className="metric" key={label}><div className="label">{label}</div><div className="value mono">{value}</div></div>)}</div><p className="note">{d.notes.join(' ')}</p></section>
    <div className="span-5"><ChartPanel title={`${price.instrument.symbol} daily return distribution`} subtitle="Trailing 1Y" meta={analytics.meta} revision={price.instrument.symbol}
      data={[{ type: 'bar', x: d.histogram.map(bin => (bin.low + bin.high) / 2), y: d.histogram.map(bin => bin.count), width: d.histogram.map(bin => bin.high - bin.low), marker: { color: '#7CAEFF' } }] as any}
      layout={{ height: 250, bargap: 0.05, xaxis: { title: { text: 'Daily return' }, tickformat: '.1%' }, yaxis: { title: { text: 'Trading days' }, rangemode: 'tozero' } }} summary={`Frequency of observed daily returns; ${d.sample_count} sessions. Analysis is independent of the price-chart window.`} /></div>
    <div className="span-7"><Calendar returns={d.returns} /></div>
  </div>;
}
function PeersTab({ analytics }: { analytics: Analytics }) {
  const comparison = analytics.comparison, capm = analytics.capm;
  const symbols = comparison.symbols;
  const key = `${analytics.symbol}:${symbols.join(',')}`;
  const betaMin = Math.min(0, (capm.beta ?? 1) - 0.5), betaMax = Math.max(2, (capm.beta ?? 1) + 0.5);
  const line = (beta: number) => capm.risk_free_rate != null && capm.market_return != null ? capm.risk_free_rate + beta * (capm.market_return - capm.risk_free_rate) : null;
  return <div className="grid markets-grid">
    <div className="span-8"><ChartPanel title="Peer cumulative returns" subtitle="Trailing 1Y · common baseline" meta={analytics.meta} revision={key}
      data={comparison.series.map(series => ({ type: 'scatter', mode: 'lines', name: series.symbol, x: series.points.map(p => p.time), y: series.points.map(p => p.value), connectgaps: false })) as any}
      layout={{ height: 320, showlegend: true, legend: { orientation: 'h', y: -0.2 }, yaxis: { title: { text: 'Price return' }, tickformat: '.0%' } }} summary="All curves start at the same observed price baseline, with 0% initial return. Gaps remain unfilled." /></div>
    <section className="panel panel-pad span-4"><h2>Correlation matrix <small>Pearson · 1Y</small></h2><div className="table-wrap"><table className="chart-table correlation-table"><caption className="sr-only">Pairwise correlations and aligned observation counts</caption><thead><tr><th>Symbol</th>{symbols.map(s => <th key={s}>{s}</th>)}</tr></thead><tbody>{symbols.map(x => <tr key={x}><th>{x}</th>{symbols.map(y => {
      const point = comparison.correlations.find(p => p.x === x && p.y === y);
      const v = point?.value;
      return <td key={y} style={{ backgroundColor: v == null ? 'transparent' : `color-mix(in srgb, var(${v < 0 ? '--negative' : '--positive'}) ${Math.abs(v) * 25}%, var(--surface))` }}><strong>{number(v, 2)}</strong><small>n={point?.sample_count ?? 0}</small></td>;
    })}</tr>)}</tbody></table></div><p className="note">At least 60 aligned returns and nonzero variance are required for each pair.</p></section>
    <div className="span-8"><ChartPanel title={`${analytics.symbol} security market line`} subtitle="CAPM historical-alpha heuristic" meta={analytics.meta} revision={key}
      data={[{ type: 'scatter', mode: 'lines', x: [betaMin, betaMax], y: [line(betaMin), line(betaMax)], name: 'Security market line', line: { color: '#9AAEC6', dash: 'dot' } }, { type: 'scatter', mode: 'markers+text', x: [capm.beta], y: [capm.actual_return], text: [analytics.symbol], textposition: 'top center', marker: { color: '#7CAEFF', size: 12 }, name: 'Historical annual return' }] as any}
      layout={{ height: 340, margin: { l: 58, r: 18, t: 65, b: 60 }, xaxis: { title: { text: 'Beta vs S&P 500' }, range: [betaMin, betaMax] }, yaxis: { title: { text: 'Annual return' }, tickformat: '.0%' }, annotations: [{ x: 0, y: 1.18, xref: 'paper', yref: 'paper', xanchor: 'left', text: 'Above SML: Underpriced / Alpha &gt; 0 (heuristic)', font: { size: 10, color: '#3DD6A0' }, showarrow: false }, { x: 0, y: 1.08, xref: 'paper', yref: 'paper', xanchor: 'left', text: 'Below SML: Overpriced / Alpha &lt; 0 (heuristic)', font: { size: 10, color: '#FF7B72' }, showarrow: false }] }} summary={`CAPM return ${percent(capm.expected_return)}; historical alpha ${percent(capm.alpha)}; ${capm.sample_count} aligned returns. Zone labels are model heuristics, not evidence of fair value.`} /></div>
    <section className="panel panel-pad span-4"><h2>CAPM scenario <small>One-year assumption</small></h2><dl className="metric-list">{[['Risk-free proxy', percent(capm.risk_free_rate, 2)], ['Market historical return', percent(capm.market_return)], ['Beta', number(capm.beta)], ['Expected return', percent(capm.expected_return)], ['Historical alpha', percent(capm.alpha)], ['Scenario price', money(capm.scenario_price)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="mono">{value}</dd></div>)}</dl><p className="note">{capm.notes.join(' ')}</p></section>
  </div>;
}
export function StockPage() {
  const { symbol = 'AAPL' } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const timeframe = (['1D', '5D', '1M', '1Y'].includes(params.get('timeframe') || '') ? params.get('timeframe') : '1Y') as Timeframe;
  const tab = params.get('tab') === 'peers' ? 'peers' : 'price';
  const peers = useMemo(() => [...new Set((params.get('peers') ?? 'MSFT,NVDA').split(',').filter(s => s && s !== symbol))].slice(0, 5), [params, symbol]);
  const price = useQuery({ queryKey: ['price', symbol, timeframe], queryFn: () => api.price(symbol, timeframe), refetchInterval: () => document.visibilityState === 'visible' && ['1D', '5D'].includes(timeframe) ? 300000 : false });
  const analytics = useQuery({ queryKey: ['analytics', symbol, peers, timeframe], queryFn: () => api.analytics(symbol, peers, timeframe) });
  const update = (key: string, value: string) => setParams(previous => { previous.set(key, value); return previous; });
  return <><header className="page-head"><div><p className="eyebrow">RESEARCH DESK / EQUITIES</p><h1>Stock analysis</h1><p>Price, distributions and model assumptions in context.</p></div><div className="toolbar"><Timeframes value={timeframe} onChange={value => update('timeframe', value)} /><Button onClick={() => { price.refetch(); analytics.refetch(); }}>Refresh</Button></div></header>
    <div className="toolbar research-controls"><SymbolSearch value={symbol} onPick={next => navigate(`/stocks/${next}?${params.toString()}`)} /></div>
    <QueryState loading={price.isLoading || analytics.isLoading} error={price.error || analytics.error} hasData={!!price.data && !!analytics.data} retry={() => { price.refetch(); analytics.refetch(); }}>
      {price.data && analytics.data && <><Metadata meta={price.data.meta} /><div className="context-row instrument-heading"><strong>{symbol}</strong><span>{price.data.instrument.name}</span><strong className="mono">{money(price.data.last_price)}</strong><span className={price.data.change != null && price.data.change < 0 ? 'down' : 'up'}>{percent(price.data.change)} <small>vs previous session</small></span></div>
        <AppTabs value={tab} onChange={value => update('tab', value)} items={[{ value: 'price', label: 'Price & distribution' }, { value: 'peers', label: 'Peers & CAPM' }]}>
          <TabPanel value="price"><PriceTab price={price.data} analytics={analytics.data} timeframe={timeframe} /></TabPanel>
          <TabPanel value="peers"><div className="toolbar research-controls"><SymbolSearch value="" label="Add a comparison stock" clearOnPick onPick={next => { if (next !== symbol && !peers.includes(next) && peers.length < 5) update('peers', [...peers, next].join(',')); }} />{peers.map(peer => <Button key={peer} onClick={() => update('peers', peers.filter(p => p !== peer).join(','))} aria-label={`Remove peer ${peer}`}>{peer} ×</Button>)}<span className="note">Up to five peers</span></div><PeersTab analytics={analytics.data} /></TabPanel>
        </AppTabs><details className="method-details"><summary>Analysis data and methods</summary><Metadata meta={analytics.data.meta} /></details>
      </>}
    </QueryState>
  </>;
}
