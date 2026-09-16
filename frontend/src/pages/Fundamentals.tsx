import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Fundamentals, StatementRow } from '../api/types';
import { ChartPanel } from '../components/Chart';
import { Metadata, QueryState } from '../components/Shell';
import { AppTabs, Button, TabPanel } from '../components/ui';
import { SymbolSearch } from '../components/SymbolSearch';
import { compact, money, number, percent } from '../lib';

function DataTable({ rows }: { rows: StatementRow[] }) {
  return <div className="table-wrap"><table className="chart-table"><thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">Unit</th></tr></thead><tbody>{rows.map(row => <tr key={row.label}><th scope="row">{row.label}</th><td className="mono">{row.unit === 'percent' ? percent(row.value) : row.unit === 'currency' ? money(row.value) : number(row.value)}</td><td>{row.unit === 'currency' ? 'USD' : row.unit}</td></tr>)}</tbody></table>{!rows.length && <p className="note">No statement values are available.</p>}</div>;
}
function KeyFigures({ data }: { data: Fundamentals }) {
  return <section className="panel panel-pad"><h2>{data.symbol} key figures</h2><div className="metric-grid">{[['Current price', money(data.metrics.price)], ['Market cap', compact(data.metrics.market_cap, 'USD')], ['P/E', number(data.metrics.pe)], ['P/BV', number(data.metrics.pb)], ['Trailing EPS', money(data.metrics.eps)], ['Beta vs S&P 500', number(data.metrics.beta)], ['6-month Sharpe', number(data.metrics.sharpe_6m)], ['CAPM scenario price', money(data.metrics.capm_target)]].map(([label, value]) => <div className="metric" key={label}><div className="label">{label}</div><div className="value mono">{value}</div></div>)}</div><p className="note">CAPM is a one-year research scenario; the latest Treasury proxy is held constant for historical risk metrics.</p></section>;
}
function Performance({ data }: { data: Fundamentals }) {
  const quarters = data.quarters, latest = quarters.at(-1), estimate = data.estimate;
  const growth = (label: string, qoq: number | null | undefined, yoy: number | null | undefined) => <div className="growth-row"><strong>{label}</strong><span>QoQ {percent(qoq)}</span><span>YoY {percent(yoy)}</span></div>;
  const delta = (current: number | null | undefined, previous: number | null | undefined) => current == null || previous == null ? '—' : `${current - previous >= 0 ? '+' : ''}${((current - previous) * 100).toFixed(1)} pp`;
  return <div className="grid markets-grid">
    <div className="span-6"><ChartPanel title={`${data.symbol} quarterly revenue`} subtitle="USD · reported and next-quarter estimate" meta={data.meta} revision={data.symbol}
      data={[{ type: 'bar', name: 'Reported revenue', x: quarters.map(q => q.period), y: quarters.map(q => q.revenue), marker: { color: '#7CAEFF' } }, { type: 'bar', name: 'Forward consensus', x: estimate ? [estimate.period] : [], y: estimate ? [estimate.revenue] : [], marker: { color: '#F4C66A', pattern: { shape: '/' } } }] as any}
      layout={{ height: 300, showlegend: true, legend: { orientation: 'h', y: -0.22 }, yaxis: { title: { text: 'Revenue (USD)' }, tickprefix: '$', tickformat: '.2s', rangemode: 'tozero' } }} summary={`${quarters.length} historical quarters available of eight requested. Next-quarter revenue estimate: ${money(estimate?.revenue)}.`}>
      {growth('Revenue growth', latest?.revenue_qoq, latest?.revenue_yoy)}
    </ChartPanel></div>
    <div className="span-6"><ChartPanel title={`${data.symbol} quarterly EPS`} subtitle="USD per share · reported and estimate" meta={data.meta} revision={data.symbol}
      data={[{ type: 'scatter', mode: 'lines+markers', name: 'Reported EPS', x: quarters.map(q => q.period), y: quarters.map(q => q.eps), line: { color: '#3DD6A0' }, connectgaps: false }, { type: 'scatter', mode: 'markers', name: 'Forward consensus', x: estimate ? [estimate.period] : [], y: estimate ? [estimate.eps] : [], marker: { color: '#F4C66A', size: 11, symbol: 'diamond' } }] as any}
      layout={{ height: 300, showlegend: true, legend: { orientation: 'h', y: -0.22 }, yaxis: { title: { text: 'EPS (USD per share)' }, tickprefix: '$' } }} summary={`Reported diluted earnings per share. Next-quarter EPS estimate: ${money(estimate?.eps)}. Missing estimates remain unavailable.`}>
      {growth('EPS growth', latest?.eps_qoq, latest?.eps_yoy)}
    </ChartPanel></div>
    <div className="span-12"><ChartPanel title={`${data.symbol} profitability margins`} subtitle="Quarterly · percentage of revenue" meta={data.meta} revision={data.symbol}
      data={(['gross_margin', 'operating_margin', 'net_margin'] as const).map((key, i) => ({ type: 'scatter', mode: 'lines+markers', name: ['Gross', 'Operating', 'Net'][i], x: quarters.map(q => q.period), y: quarters.map(q => q[key]), connectgaps: false })) as any}
      layout={{ height: 300, showlegend: true, legend: { orientation: 'h', y: -0.22 }, yaxis: { title: { text: 'Margin' }, tickformat: '.0%' } }} summary="Gross, operating and net margins use reported profit divided by positive revenue. Changes are percentage points.">
      <div className="table-wrap"><table className="chart-table"><thead><tr><th>Margin</th><th>Latest</th><th>QoQ change</th><th>YoY change</th></tr></thead><tbody>{(['gross_margin', 'operating_margin', 'net_margin'] as const).map((key, i) => <tr key={key}><th>{['Gross', 'Operating', 'Net'][i]}</th><td>{percent(latest?.[key])}</td><td>{delta(latest?.[key], quarters.at(-2)?.[key])}</td><td>{delta(latest?.[key], quarters.at(-5)?.[key])}</td></tr>)}</tbody></table></div>
    </ChartPanel></div>
  </div>;
}
function IncomeFlow({ data }: { data: Fundamentals }) {
  const flow = data.income_flow;
  if (flow.kind !== 'sankey') return <section className="panel panel-pad"><h2>Income statement flow <small>Signed statement alternative</small></h2><p className="note">Losses, missing items or unreconciled flows cannot form a truthful Sankey.</p><DataTable rows={flow.steps.map(step => ({ ...step, unit: 'currency' }))} /><p className="note">{flow.notes.join(' ')}</p></section>;
  return <ChartPanel title={`${data.symbol} income statement flow`} subtitle="Latest reported quarter · USD" meta={data.meta} revision={data.symbol}
    data={[{ type: 'sankey', node: { label: flow.nodes, color: '#7CAEFF', pad: 22, thickness: 15 }, link: { source: flow.links.map(link => flow.nodes.indexOf(link.source)), target: flow.links.map(link => flow.nodes.indexOf(link.target)), value: flow.links.map(link => link.value), color: 'rgba(124,174,255,0.28)' } }] as any}
    layout={{ height: 350, margin: { l: 8, r: 15, t: 10, b: 10 } }} summary="Observed revenue through costs, operating income and net income. Flows reconcile at every internal node."><p className="note">{flow.notes.join(' ')}</p></ChartPanel>;
}
function Consensus({ data }: { data: Fundamentals }) {
  const c = data.consensus;
  const complete = c.buy != null && c.hold != null && c.sell != null;
  const total = complete ? c.buy! + c.hold! + c.sell! : 0;
  const proportions = [c.buy, c.hold, c.sell].map(value => complete && total > 0 && value != null ? value / total : null);
  return <div className="grid markets-grid">
    <div className="span-6"><ChartPanel title={`${data.symbol} analyst recommendations`} subtitle="Share of available recommendations" meta={data.meta} revision={data.symbol}
      data={[{ type: 'bar', x: ['Buy', 'Hold', 'Sell'], y: proportions, marker: { color: ['#3DD6A0', '#F4C66A', '#FF7B72'] } }] as any}
      layout={{ height: 250, yaxis: { title: { text: 'Recommendation share' }, tickformat: '.0%', range: [0, 1] } }} summary={complete && total ? `${number(total, 0)} recommendations; Buy ${percent(proportions[0])}, Hold ${percent(proportions[1])}, Sell ${percent(proportions[2])}.` : 'Recommendation proportions unavailable because counts are missing or empty.'}>
      <p className="note">Counts: Buy {number(c.buy, 0)} · Hold {number(c.hold, 0)} · Sell {number(c.sell, 0)}.</p>
    </ChartPanel></div>
    <div className="span-6"><ChartPanel title={`${data.symbol} analyst price targets`} subtitle="USD · low / mean / high" meta={data.meta} revision={data.symbol}
      data={[{ type: 'scatter', mode: 'lines+markers', name: 'Target range', x: [c.target_low, c.target_high], y: [1, 1], line: { color: '#9AAEC6', width: 4 } }, { type: 'scatter', mode: 'markers', name: 'Mean target', x: [c.target_mean], y: [1], marker: { color: '#7CAEFF', size: 14, symbol: 'diamond' } }] as any}
      layout={{ height: 250, showlegend: true, legend: { orientation: 'h', y: -0.24 }, yaxis: { visible: false, range: [0.6, 1.4] }, xaxis: { title: { text: 'Analyst target price (USD)' }, tickprefix: '$' } }} summary={`Low ${money(c.target_low)}, mean ${money(c.target_mean)}, high ${money(c.target_high)}. Analyst count ${number(c.analyst_count, 0)}. Consensus is not a guarantee.`} />
    </div>
  </div>;
}
export function FundamentalsPage() {
  const { symbol = 'AAPL' } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'statements' ? 'statements' : 'performance';
  const statement = ['valuation', 'income', 'balance'].includes(params.get('statement') || '') ? params.get('statement')! : 'valuation';
  const query = useQuery({ queryKey: ['fundamentals', symbol], queryFn: () => api.fundamentals(symbol), staleTime: 86400000 });
  const update = (key: string, value: string) => setParams(previous => { previous.set(key, value); return previous; });
  return <><header className="page-head"><div><p className="eyebrow">RESEARCH DESK / COMPANY FINANCIALS</p><h1>Fundamentals</h1><p>Reported performance, forward estimates and analyst context.</p></div><Button onClick={() => query.refetch()} disabled={query.isFetching}>{query.isFetching ? 'Refreshing…' : 'Refresh'}</Button></header>
    <div className="toolbar research-controls"><SymbolSearch value={symbol} onPick={next => navigate(`/fundamentals/${next}?${params.toString()}`)} /></div>
    <QueryState loading={query.isLoading} error={query.error} hasData={!!query.data} retry={() => query.refetch()}>{query.data && <><Metadata meta={query.data.meta} /><KeyFigures data={query.data} />
      <div className="section-gap"><AppTabs value={tab} onChange={value => update('tab', value)} items={[{ value: 'performance', label: 'Performance & estimates' }, { value: 'statements', label: 'Statements & consensus' }]}>
        <TabPanel value="performance"><Performance data={query.data} /></TabPanel>
        <TabPanel value="statements"><div className="grid"><IncomeFlow data={query.data} /><section className="panel panel-pad"><h2>Financial statements</h2><AppTabs value={statement} onChange={value => update('statement', value)} items={[{ value: 'valuation', label: 'Valuation ratios' }, { value: 'income', label: 'Profitability & income' }, { value: 'balance', label: 'Balance sheet & cash flow' }]}>
          <TabPanel value="valuation"><DataTable rows={query.data.statements.valuation} /></TabPanel><TabPanel value="income"><DataTable rows={query.data.statements.income} /></TabPanel><TabPanel value="balance"><DataTable rows={query.data.statements.balance_cashflow} /></TabPanel>
        </AppTabs></section><Consensus data={query.data} /></div></TabPanel>
      </AppTabs></div>
    </>}</QueryState>
  </>;
}
