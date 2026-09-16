import { useEffect, useId, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { api } from '../api/client';
import type { Instrument } from '../api/types';

export function SymbolSearch({ value, onPick, label = 'Search stocks', clearOnPick = false }: {
  value: string; onPick: (symbol: string) => void; label?: string; clearOnPick?: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(value);
  const [items, setItems] = useState<Instrument[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [editing, setEditing] = useState(false);
  const [composing, setComposing] = useState(false);
  const [status, setStatus] = useState('');
  useEffect(() => { setQuery(value); setEditing(false); setOpen(false); }, [value]);
  useEffect(() => {
    if (!editing || composing) return;
    const controller = new AbortController();
    if (!query.trim()) { setItems([]); setOpen(false); return; }
    const timer = window.setTimeout(async () => {
      setStatus('Searching…'); setOpen(true);
      try {
        const result = await api.universe(query.trim(), controller.signal);
        if (!controller.signal.aborted) { setItems(result.items); setActive(0); setStatus(result.items.length ? '' : 'No matching S&P 500 symbols.'); }
      } catch {
        if (!controller.signal.aborted) { setItems([]); setStatus('Search unavailable. Edit the search to retry.'); }
      }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, editing, composing]);
  const pick = (symbol: string) => {
    onPick(symbol); setQuery(clearOnPick ? '' : symbol); setEditing(false); setOpen(false); setItems([]);
  };
  return <div className="symbol-search" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <label className="sr-only" htmlFor={id}>{label}</label>
    <Search size={15} aria-hidden="true" style={{ position: 'absolute', left: 10, top: 11, color: 'var(--muted)' }} />
    <input id={id} ref={input} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-list`} aria-activedescendant={open && items[active] ? `${id}-${active}` : undefined}
      autoComplete="off" value={query} placeholder={label} style={{ paddingLeft: 31 }}
      onChange={event => { setEditing(true); setQuery(event.target.value); }}
      onFocus={() => setEditing(true)} onCompositionStart={() => setComposing(true)}
      onCompositionEnd={event => { setComposing(false); setQuery(event.currentTarget.value); }}
      onKeyDown={event => {
        if (event.nativeEvent.isComposing) return;
        if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); setActive(index => Math.min(index + 1, items.length - 1)); }
        if (event.key === 'ArrowUp') { event.preventDefault(); setActive(index => Math.max(0, index - 1)); }
        if (event.key === 'Enter' && open && items[active]) { event.preventDefault(); pick(items[active].symbol); }
        if (event.key === 'Escape') { setOpen(false); setEditing(false); }
      }} />
    {query && <button type="button" className="clear" aria-label={`Clear ${label.toLowerCase()}`} onClick={() => { setQuery(''); setEditing(true); setItems([]); setOpen(false); input.current?.focus(); }}>×</button>}
    {open && <div className="listbox" id={`${id}-list`} role="listbox" aria-label={`${label} results`}>
      {status && <p role="status" className="note" style={{ padding: 10 }}>{status}</p>}
      {items.map((item, index) => <button type="button" id={`${id}-${index}`} role="option" aria-selected={active === index} tabIndex={-1} key={item.symbol}
        onMouseDown={event => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => pick(item.symbol)}>
        <strong>{item.symbol}</strong> <span className="note">{item.name}</span>
      </button>)}
    </div>}
  </div>;
}
