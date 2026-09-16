import { describe, expect, it } from 'vitest';
import { chartRows } from './Chart';
import type { Data } from 'plotly.js';

describe('accessible chart observations', () => {
  it('distinguishes fractional returns from already scaled percentage values', () => {
    const fraction = chartRows([{ type: 'scatter', x: ['A'], y: [0.123] }], { yaxis: { title: { text: 'Return' }, tickformat: '.0%' } });
    const scaled = chartRows([{ type: 'scatter', x: ['A'], y: [12.3] }], { yaxis: { title: { text: 'Return' }, ticksuffix: '%' } });
    expect(fraction[0]).toEqual(['scatter', 'A', 'Return', '12.3%']);
    expect(scaled[0]).toEqual(fraction[0]);
  });
  it('keeps all candle dates paired with their original OHLC values', () => {
    const rows = chartRows([{ type: 'candlestick', x: ['day-1', 'day-2'], open: [10, 20], high: [12, 22], low: [9, 19], close: [11, null] }] as Data[]);
    expect(rows).toHaveLength(8);
    expect(rows[4]).toEqual(['candlestick', 'day-2', 'open', '20']);
    expect(rows[7]).toEqual(['candlestick', 'day-2', 'close', 'Unavailable']);
  });
  it('retains the full horizontal profile without shifting or truncating values', () => {
    const rows = chartRows([{ type: 'bar', orientation: 'h', y: Array.from({ length: 50 }, (_, i) => `bucket-${i}`), x: Array.from({ length: 50 }, (_, i) => i * 100) }] as Data[]);
    expect(rows).toHaveLength(50);
    expect(rows[49]).toEqual(['bar', 'bucket-49', 'x value', '4900']);
  });
  it('resolves Sankey endpoints and matrix axes into readable rows', () => {
    expect(chartRows([{ type: 'sankey', node: { label: ['Revenue', 'COGS'] }, link: { source: [0], target: [1], value: [40] } }] as Data[])).toEqual([['sankey', 'Revenue', 'to COGS', '40']]);
    expect(chartRows([{ type: 'heatmap', x: ['A', 'B'], y: ['A'], z: [[1, null]] }] as Data[])).toEqual([['heatmap', 'A', 'A', '1'], ['heatmap', 'A', 'B', 'Unavailable']]);
  });
});
