import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import type { Data, Layout } from 'plotly.js';
import type { Metadata as DataMetadata } from '../api/types';

let plotlyPromise: Promise<typeof import('plotly.js')> | undefined;
function loadPlotly() {
  plotlyPromise ??= Promise.all([
    import('plotly.js/lib/core'), import('plotly.js/lib/bar'),
    import('plotly.js/lib/candlestick'), import('plotly.js/lib/heatmap'),
    import('plotly.js/lib/sankey'), import('plotly.js/lib/pie'),
    import('plotly.js/lib/indicator'), import('plotly.js/lib/waterfall'),
  ]).then(([core, ...traces]) => {
    core.default.register(traces.map(trace => trace.default));
    return core.default;
  }).catch(error => {
    plotlyPromise = undefined;
    throw error;
  });
  return plotlyPromise;
}

function themeData(value: unknown, colors: Record<string, string>): unknown {
  if (typeof value === 'string') return colors[value.toLowerCase()] ?? value;
  if (Array.isArray(value)) return value.map(item => themeData(item, colors));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, themeData(item, colors)]));
  }
  return value;
}

function chartTheme(data: Data[], layout: Partial<Layout>, revision: string) {
  const style = getComputedStyle(document.documentElement);
  const token = (name: string) => style.getPropertyValue(name).trim();
  const colors: Record<string, string> = {
    '#7caeff': token('--primary'), '#3dd6a0': token('--positive'),
    '#ff7b72': token('--negative'), '#f4c66a': token('--warning'),
    '#9aaec6': token('--muted'), '#e7eef7': token('--fg'),
  };
  const axis = { gridcolor: token('--border'), zerolinecolor: token('--muted'), automargin: true };
  const themedLayout: Partial<Layout> = {
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'IBM Plex Sans', color: token('--muted'), size: 11 },
    margin: { l: 52, r: 20, t: 16, b: 48 }, showlegend: false,
    colorway: [token('--primary'), token('--positive'), token('--warning'), token('--negative'), token('--muted')],
    hoverlabel: { bgcolor: token('--surface'), font: { color: token('--fg') } },
    uirevision: revision,
    ...layout,
    xaxis: { ...axis, rangeslider: { visible: false }, ...layout.xaxis },
    yaxis: { ...axis, ...layout.yaxis },
  };
  return { data: themeData(data, colors) as Data[], layout: themeData(themedLayout, colors) as Partial<Layout> };
}

export type ChartRow = [series: string, observation: string, measure: string, value: string];
function cell(value: unknown): string {
  if (value == null || (typeof value === 'number' && !Number.isFinite(value))) return 'Unavailable';
  if (typeof value === 'number') return String(Number(value.toPrecision(8)));
  return String(value);
}

/** Full, unshifted observations for every supported renderer, including gaps. */
export function chartRows(data: Data[], layout: Partial<Layout> = {}): ChartRow[] {
  return data.flatMap((trace: Data, traceIndex): ChartRow[] => {
    const t = trace as unknown as Record<string, any>;
    const name = String(t.name || t.type || `Series ${traceIndex + 1}`);
    if (t.type === 'candlestick') {
      return (t.x ?? []).flatMap((x: unknown, i: number) => ['open', 'high', 'low', 'close'].map(
        measure => [name, cell(x), measure, cell(t[measure]?.[i])] as ChartRow,
      ));
    }
    if (t.type === 'sankey') {
      return (t.link?.value ?? []).map((value: unknown, i: number) => [
        name, cell(t.node?.label?.[t.link.source[i]]),
        `to ${cell(t.node?.label?.[t.link.target[i]])}`, cell(value),
      ]);
    }
    if (t.type === 'heatmap') {
      return (t.z ?? []).flatMap((row: unknown[], i: number) => row.map((value, j): ChartRow => [
        name, cell(t.y?.[i] ?? i), cell(t.x?.[j] ?? j), cell(value),
      ]));
    }
    if (t.type === 'indicator') return [[name, 'Current observation', 'Value', cell(t.value)]];
    if (t.type === 'pie') {
      return (t.labels ?? []).map((label: unknown, i: number) => [name, cell(label), 'Value', cell(t.values?.[i])]);
    }
    const horizontal = t.orientation === 'h';
    const observations = horizontal ? t.y : t.x;
    const values = horizontal ? t.x : t.y;
    const axisKey = horizontal ? (t.xaxis || 'x') : (t.yaxis || 'y');
    const axis = (layout as Record<string, any>)[axisKey.replace(/^([xy])/, '$1axis')] ?? {};
    const percentage = String(axis.tickformat ?? '').includes('%');
    const measure = typeof axis.title === 'string' ? axis.title : axis.title?.text;
    const formatted = (value: unknown) => value == null ? 'Unavailable' : percentage && typeof value === 'number'
      ? `${cell(value * 100)}%` : `${axis.tickprefix ?? ''}${cell(value)}${axis.ticksuffix ?? ''}`;
    return (observations ?? []).map((observation: unknown, i: number) => [
      name, cell(observation), measure || (horizontal ? 'x value' : 'y value'), formatted(values?.[i]),
    ]);
  });
}

function DataTable({ rows }: { rows: ChartRow[] }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const lastPage = Math.max(0, Math.ceil(rows.length / 40) - 1);
  const activePage = Math.min(page, lastPage);
  return <details className="table-wrap" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Chart data table · {rows.length} values</summary>
    {open && <>
      {rows.length ? <table className="chart-table">
        <caption className="sr-only">Underlying chart observations; unavailable values are retained.</caption>
        <thead><tr>{['Series', 'Observation', 'Measure', 'Value'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{rows.slice(activePage * 40, (activePage + 1) * 40).map((row, i) => <tr key={`${activePage}-${i}`}>
          {row.map((value, j) => <td key={j}>{value}</td>)}
        </tr>)}</tbody>
      </table> : <p className="note">No observed values are available for this chart.</p>}
      {lastPage > 0 && <div className="toolbar" style={{ marginTop: 8 }}>
        <button type="button" className="btn" disabled={!activePage} onClick={() => setPage(activePage - 1)}>Previous values</button>
        <span aria-live="polite">Page {activePage + 1} of {lastPage + 1}</span>
        <button type="button" className="btn" disabled={activePage >= lastPage} onClick={() => setPage(activePage + 1)}>Next values</button>
      </div>}
    </>}
  </details>;
}

function Plot({ data, layout, revision, onReady }: {
  data: Data[]; layout: Partial<Layout>; revision: string; onReady: (ready: boolean) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState(false);
  const [ready, setReady] = useState(false);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const mounted = useRef(true);
  const height = layout.height ?? 300;
  useEffect(() => {
    const node = ref.current!;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: '100px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    mounted.current = true;
    const node = ref.current!;
    const observer = new ResizeObserver(() => {
      if (plotlyPromise) void plotlyPromise.then(p => { if (mounted.current && node.classList.contains('js-plotly-plot')) return p.Plots.resize(node); }).catch(() => {});
    });
    observer.observe(node);
    return () => {
      mounted.current = false;
      observer.disconnect();
      void queue.current.finally(() => plotlyPromise?.then(p => p.purge(node))).catch(() => {});
    };
  }, []);
  useEffect(() => {
    if (!visible) return;
    // Serialize updates. Purge occurs only on unmount, so Plotly keeps user zoom.
    queue.current = queue.current.catch(() => {}).then(async () => {
      const plotly = await loadPlotly();
      if (!mounted.current || !ref.current) return;
      const theme = chartTheme(data, layout, revision);
      await plotly.react(ref.current, theme.data, theme.layout, {
        responsive: true, displayModeBar: false, scrollZoom: false,
      });
      if (mounted.current) { setError(false); setReady(true); onReady(true); }
    }).catch(() => { if (mounted.current) { setError(true); onReady(false); } });
  }, [data, layout, revision, visible, onReady]);
  return <div style={{ position: 'relative', height, minHeight: height }}>
    <div ref={ref} aria-hidden="true" style={{ height, width: '100%' }} />
    {(!ready || error) && <div role="status" className="empty" style={{ position: 'absolute', inset: 0, minHeight: 0, pointerEvents: 'none' }}>
      {error ? 'Chart unavailable. The data table remains accessible below.' : visible ? 'Loading chart…' : 'Chart loads when visible.'}
    </div>}
  </div>;
}

function wrap(text: string, width = 110): string[] {
  return text.match(new RegExp(`.{1,${width}}(?:\\s|$)|.{1,${width}}`, 'g'))?.map(line => line.trim()) ?? [];
}
function html(text: string) {
  return text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}
function csv(value: string) {
  // Treat exported labels as text rather than spreadsheet formulas.
  const safe = /^[=+@-]/.test(value) && !/^[+-]?\d+(\.\d+)?(e[+-]?\d+)?$/i.test(value) ? `'${value}` : value;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function ChartPanel({ title, subtitle, data, layout = {}, children, summary, meta, revision }: {
  title: string; subtitle?: string; data: Data[]; layout?: Partial<Layout>;
  children?: ReactNode; summary: string; meta?: DataMetadata; revision?: string;
}) {
  const id = useId();
  const section = useRef<HTMLElement>(null);
  const [ready, setReady] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const rows = useMemo(() => chartRows(data, layout), [data, layout]);
  const name = title || 'Price chart';
  const provenance = () => meta ? [
    `Source: ${meta.source} · observed: ${meta.as_of ?? 'unavailable'} · retrieved: ${meta.retrieved_at ?? 'unavailable'}`,
    `Status: ${meta.status} · units: ${meta.currency ?? subtitle ?? 'see axes'} · window: ${meta.requested_window ?? 'see chart'}`,
    ...meta.notes,
  ] : [section.current?.closest('main')?.querySelector('.research-strip')?.textContent || 'See the dashboard source context.'];
  const exportCSV = () => {
    const lines = [[name, subtitle || ''], ...[summary, ...provenance()].map(line => [line]), ['Series', 'Observation', 'Measure', 'Value'], ...rows];
    const url = URL.createObjectURL(new Blob([lines.map(row => row.map(csv).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `${name.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.csv`;
    anchor.click(); URL.revokeObjectURL(url);
  };
  const exportPNG = async () => {
    setExporting(true); setExportError('');
    const node = document.createElement('div');
    node.style.cssText = 'position:fixed;left:-20000px;width:1100px;';
    document.body.appendChild(node);
    try {
      const plotly = await loadPlotly();
      const notes = [summary, ...provenance()].flatMap(line => wrap(line));
      const footer = 35 + notes.length * 15;
      const theme = chartTheme(data, layout, revision || name);
      await plotly.newPlot(node, theme.data, {
        ...theme.layout, width: 1100, height: 520 + footer,
        paper_bgcolor: getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(),
        title: { text: html([name, subtitle].filter(Boolean).join(' · ')), x: 0.04 },
        margin: { l: 70, r: 50, t: 70, b: footer + 40 },
        annotations: [...(layout.annotations || []), { xref: 'paper', yref: 'paper', x: 0, y: 0, xanchor: 'left', yanchor: 'top', yshift: -55, text: notes.map(html).join('<br>'), align: 'left', showarrow: false, font: { size: 11 } }],
      }, { staticPlot: true });
      await plotly.downloadImage(node, { format: 'png', width: 1100, height: 520 + footer, filename: name.replace(/[^a-z0-9]+/gi, '-').toLowerCase() });
    } catch {
      setExportError('Image export failed. You can still export the observed data as CSV.');
    } finally {
      if (plotlyPromise) await plotlyPromise.then(p => p.purge(node)).catch(() => {});
      node.remove(); setExporting(false);
    }
  };
  return <section ref={section} className="panel panel-pad" aria-labelledby={id}>
    <h2 id={id}>{name}{subtitle && <small>{subtitle}</small>}</h2>
    <Plot data={data} layout={layout} revision={revision || name} onReady={setReady} />
    {summary && <p className="chart-caption">{summary}</p>}
    <div className="toolbar" style={{ margin: '8px 0' }}>
      <button type="button" className="btn" onClick={exportCSV} aria-label={`Export ${name} data as CSV`}>CSV</button>
      <button type="button" className="btn" disabled={!ready || exporting} onClick={exportPNG} aria-label={`Export ${name} chart as PNG`}>{exporting ? 'Exporting…' : 'PNG'}</button>
    </div>
    {exportError && <p role="alert" className="notice error">{exportError}</p>}
    <DataTable rows={rows} />
    {children}
  </section>;
}
