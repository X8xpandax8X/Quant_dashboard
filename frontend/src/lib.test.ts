import { describe, expect, it } from 'vitest';
import { money, percent, totalBps, validatePositions, vixZone } from './lib';

describe('financial presentation', () => {
  it('formats fractional returns and missing values without inventing data', () => {
    expect(percent(0.1234)).toBe('+12.3%');
    expect(percent(null)).toBe('—');
  });

  it('formats point-denominated index values without treating them as currency', () => {
    expect(money(5017.84, 'points')).toBe('5,017.84 points');
    expect(money(null, 'USD')).toBe('—');
  });

  it('uses the specified VIX zones', () => {
    expect(vixZone(14.9)).toBe('Low');
    expect(vixZone(15)).toBe('Normal');
    expect(vixZone(20)).toBe('Elevated');
    expect(vixZone(30)).toBe('Extreme');
  });
});

describe('portfolio validation', () => {
  it('requires exactly 10,000 whole basis points before analysis', () => {
    const positions = [{ symbol: 'AAPL', weight_bps: 4_000 }, { symbol: 'MSFT', weight_bps: 6_000 }];
    expect(totalBps(positions)).toBe(10_000);
    expect(validatePositions(positions)).toBeNull();
    expect(validatePositions([{ symbol: 'AAPL', weight_bps: 9_999 }])).toContain('100.00%');
  });

  it('rejects duplicate symbols and fractional basis-point weights', () => {
    expect(validatePositions([{ symbol: 'AAPL', weight_bps: 5_000 }, { symbol: 'AAPL', weight_bps: 5_000 }])).toContain('once');
    expect(validatePositions([{ symbol: 'AAPL', weight_bps: 10.5 }])).toContain('whole basis points');
  });
});
