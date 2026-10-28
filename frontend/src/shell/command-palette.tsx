// Ctrl+K: abrir cualquier pantalla o ficha escribiendo (paso 16). Un dialogo con un campo y la
// lista de lo que se encuentra (lib/quick-search.ts): pantallas por su nombre en cualquiera de
// los tres idiomas, clientes, proveedores, Objects, PO y facturas. Flechas para elegir, Intro
// para abrir, Esc para cerrar (el patron combobox de WAI-ARIA: el foco se queda en el campo y
// la opcion elegida va en aria-activedescendant). Abrir es ir alli: no cambia nada.
import { Search } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Loading } from '@/components/states';
import { fmt, useT } from '@/i18n';
import { RESULT_KINDS, type QuickResult } from '@/lib/quick-search';
import { cn } from '@/lib/utils';
import { openSearch } from '@/screens/search';
import { useNav } from './navigation';
import { useQuickSearch } from './use-quick-search';

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useT();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        closeLabel={t.common.close}
        className='top-[12vh] max-w-xl translate-y-0 gap-0 overflow-hidden p-0'
        // El foco va al campo (lo pone el campo con autoFocus).
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        {open && <PaletteBody onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function PaletteBody({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const nav = useNav();
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const search = useQuickSearch(query, 180);
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const results = search.results;

  useEffect(() => {
    input.current?.focus();
  }, []);
  useEffect(() => {
    setSelected(0);
  }, [query]);
  useEffect(() => {
    if (selected >= results.length) setSelected(Math.max(0, results.length - 1));
  }, [results.length, selected]);

  const choose = (r: QuickResult | undefined) => {
    if (!r) return;
    onClose();
    if (r.route.screen === r.view && r.route.id === undefined) nav.go(r.view);
    else nav.openFrom(r.view, r.route);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelected((i) => (results.length ? (i + 1) % results.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelected((i) => (results.length ? (i - 1 + results.length) % results.length : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(results[selected]);
    }
  };

  const grouped = useMemo(
    () => RESULT_KINDS.map((kind) => ({ kind, items: results.map((r, i) => ({ r, i })).filter(({ r }) => r.kind === kind) })).filter((g) => g.items.length),
    [results]
  );
  const optionId = (i: number) => `${listId}-o${i}`;
  const q = query.trim();

  return (
    <div className='flex flex-col'>
      <DialogTitle className='sr-only'>{t.palette.title}</DialogTitle>
      <DialogDescription className='sr-only'>{t.palette.hint}</DialogDescription>
      <div className='flex items-center gap-3 border-b border-border px-4 py-3 pr-12'>
        <Search className='h-4 w-4 shrink-0 text-muted-foreground' aria-hidden='true' />
        <input
          ref={input}
          role='combobox'
          aria-expanded={results.length > 0}
          aria-controls={listId}
          aria-autocomplete='list'
          aria-activedescendant={results.length ? optionId(selected) : undefined}
          aria-label={t.palette.title}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t.palette.placeholder}
          autoComplete='off'
          spellCheck={false}
          className='min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground'
        />
      </div>
      <div className='max-h-[min(60vh,28rem)] overflow-y-auto px-2 py-2'>
        {!q && <p className='px-3 py-6 text-center text-[13px] text-muted-foreground'>{t.palette.empty}</p>}
        {q && results.length === 0 && !search.loading && (
          <div className='px-3 py-6 text-center'>
            <p className='font-medium'>{fmt(t.ask.nothing, { q })}</p>
            <p className='mt-1 text-[13px] text-muted-foreground'>{t.ask.nothingText}</p>
          </div>
        )}
        <div id={listId} role='listbox' aria-label={t.palette.title} className={cn(results.length === 0 && 'hidden')}>
          {grouped.map((g) => (
            <div key={g.kind} role='group' aria-label={t.ask.groups[g.kind]}>
              <p aria-hidden='true' className='px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground'>
                {t.ask.groups[g.kind]}
              </p>
              {g.items.map(({ r, i }) => (
                <div
                  key={r.key}
                  id={optionId(i)}
                  role='option'
                  aria-selected={i === selected}
                  onMouseMove={() => setSelected(i)}
                  onClick={() => choose(r)}
                  className={cn(
                    'flex cursor-pointer flex-col rounded-md px-3 py-2',
                    i === selected ? 'bg-accent text-accent-foreground' : 'hover:bg-row-hover'
                  )}
                >
                  <span className={cn('text-[14px]', (r.kind === 'invoices' || r.kind === 'pos') && 'font-mono text-[13px]')} data-proper-name={r.kind === 'screens' ? undefined : ''}>
                    {r.label}
                  </span>
                  {r.detail && (
                    <span className='text-xs text-muted-foreground' data-proper-name={r.kind === 'screens' ? undefined : ''}>
                      {r.detail}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
        {q && search.loading && <Loading className='justify-center py-3' label={t.ask.searching} />}
        {search.moreInvoices > 0 && (
          <p className='px-3 py-2 text-xs text-muted-foreground'>{fmt(search.moreInvoices === 1 ? t.ask.moreInvoicesOne : t.ask.moreInvoices, { n: search.moreInvoices })}</p>
        )}
      </div>
      <div className='flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2'>
        <p className='text-xs text-muted-foreground'>{t.palette.hint}</p>
        {/* La busqueda con filtros (revision del paso 16): lo escrito pasa con ella. */}
        <button
          type='button'
          onClick={() => {
            onClose();
            openSearch(nav, query);
          }}
          className='rounded-sm text-xs font-medium text-primary underline-offset-4 hover:underline'
        >
          {t.finder.withFilters}
        </button>
      </div>
    </div>
  );
}
