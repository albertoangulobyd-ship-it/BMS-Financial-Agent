// La busqueda de Aurora en el espacio central (components/search-workspace.tsx, entrega del
// 28-10-2026, embedded): la misma caja con la lupa, "Filtros" con su contador y el recuento,
// los cuatro filtros (cliente o proveedor, tipo, fecha e importe), las pastillas activas,
// "Pensando…" (1,5 s como minimo) y los resultados. Cambios (especificacion §4.1):
// - D: busca en /api/v2/buscar (solo facturas): el texto, cliente_id o proveedor_id, el tipo, la
//   fecha (fecha_desde = fecha_hasta), el importe sin IVA (importe_min y importe_max) y, si se
//   entra desde un panel (E5-p), los filtros que trae, como pastillas que se quitan. "Pensando"
//   dura lo que tarde la lectura, 1,5 s como minimo;
// - E: euros (el deslizador va de 0 al importe mas alto, redondeado hacia arriba);
// - R: un resultado abre su factura con el vuelo (sin direccion);
// - I: los textos del diccionario; date-fns pasa a Intl (glass-calendar.tsx).
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ArrowUpRight, CalendarDays, ChevronDown, FileText, FolderSearch, SlidersHorizontal, X } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { LOCALES, fmt, useT, type Messages } from '@/i18n';
import { paths, type InvoiceRow } from '@/lib/api';
import type { PartyRow } from '@/lib/api-types';
import { formatDate, formatMoney } from '@/lib/format';
import { useSession } from '@/lib/session';
import type { SearchPreset } from '../estado';
import { WorkspaceComposer } from '../composer';
import { PartyCombobox, type PartyOption } from './ui/combobox';
import { FilterComboBox } from './ui/heroui-combo-box';
import { GlassCalendar } from './ui/glass-calendar';
import Slider06, { wholeEuros } from './ui/slider-06';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import './search-workspace.css';

/** Cuantos resultados se ensenan (el motor dice cuantos hay en total). */
const LIMIT = 50;
/** "Pensando…" dura al menos esto (Aurora: 1,5 s). */
const THINKING_MS = 1500;

/** "3 oct 2026" (el "d MMM yyyy" de Aurora). */
function shortDate(date: Date, locale: string): string {
  const month = new Intl.DateTimeFormat(locale, { month: 'short' }).format(date).replace(/\.$/, '');
  return `${date.getDate()} ${month} ${date.getFullYear()}`;
}

const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/** Lo que dice una pastilla de un filtro que llega desde un panel (E5-p). */
function presetLabel(t: Messages, key: string, value: string): string | null {
  const s = t.aurora.search;
  switch (key) {
    case 'sentido':
      return value === 'saliente' ? s.presetOut : s.presetIn;
    case 'vencida':
      return s.presetOverdue;
    case 'pendiente':
      return s.presetPending;
    case 'vence_desde':
      return fmt(s.presetDueFrom, { date: formatDate(value) });
    case 'vence_hasta':
      return fmt(s.presetDueTo, { date: formatDate(value) });
    default:
      return null;
  }
}

/** Los parametros de /api/v2/buscar para lo puesto. */
export function searchQuery(f: {
  text: string;
  party: string;
  kind: string;
  date?: Date;
  range: number[];
  max: number;
  preset: SearchPreset;
}): Record<string, string> {
  const q: Record<string, string> = { limite: String(LIMIT), orden: 'fecha', ...f.preset };
  if (f.text.trim()) q.texto = f.text.trim();
  const [side, id] = f.party.split(':');
  if (side === 'client' && id) q.cliente_id = id;
  if (side === 'provider' && id) q.proveedor_id = id;
  if (f.kind) q.tipo = f.kind;
  if (f.date) q.fecha_desde = q.fecha_hasta = isoDay(f.date);
  const [low = 0, high = f.max] = f.range;
  if (low > 0) q.importe_min = String(low);
  if (high < f.max) q.importe_max = String(high);
  return q;
}

/** El importe mas alto del deslizador: el de la factura mas grande, redondeado hacia arriba. */
export function amountCeiling(cents: number | null | undefined): number {
  const euros = Math.ceil(Math.abs(cents ?? 0) / 100);
  return Math.max(1000, Math.ceil(euros / 1000) * 1000);
}

export function SearchWorkspace({
  preset,
  onSearchingChange,
  onOpenInvoice,
}: {
  preset: SearchPreset | null;
  onSearchingChange?: (busy: boolean) => void;
  onOpenInvoice: (invoice: InvoiceRow) => void;
}) {
  const { t, lang } = useT();
  const s = t.aurora.search;
  const locale = LOCALES[lang];
  const { session } = useSession();
  const [thinking, setThinking] = useState(false),
    timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined),
    notify = useRef(onSearchingChange);
  notify.current = onSearchingChange;
  useEffect(() => {
    notify.current?.(thinking);
  }, [thinking]);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      notify.current?.(false);
    },
    []
  );
  const [parties, setParties] = useState<PartyOption[]>([]);
  const [max, setMax] = useState(1000);
  // "Buscar con filtros" desde la conversacion trae lo buscado (texto); no es un filtro.
  const [query, setQuery] = useState(preset?.texto ?? ''),
    [filtersOpen, setFiltersOpen] = useState(false),
    [party, setParty] = useState(''),
    [kind, setKind] = useState(''),
    [date, setDate] = useState<Date>(),
    [range, setRange] = useState<number[]>([0, 1000]),
    [presets, setPresets] = useState<SearchPreset>(() => {
      const { texto: _texto, ...rest } = preset ?? {};
      return rest;
    }),
    [dateOpen, setDateOpen] = useState(false),
    [found, setFound] = useState<{ total: number; rows: InvoiceRow[] } | null>(null),
    [failed, setFailed] = useState(false);
  const seq = useRef(0);

  // Las listas de clientes y proveedores y el importe mas alto, una vez.
  useEffect(() => {
    if (!session) return;
    let alive = true;
    Promise.all([
      session.api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
      session.api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores),
      session.api
        .get<{ busqueda: { facturas: InvoiceRow[] } }>(paths.search, { orden: 'importe', limite: '1' })
        .then((r) => r.busqueda.facturas[0]),
    ]).then(
      ([clients, providers, top]) => {
        if (!alive) return;
        setParties([
          ...clients.map<PartyOption>((p) => ({ value: `client:${p.id}`, label: p.nombre, description: p.exact_id ?? '', group: 'client' })),
          ...providers.map<PartyOption>((p) => ({ value: `provider:${p.id}`, label: p.nombre, description: p.exact_id ?? '', group: 'provider' })),
        ]);
        const ceiling = amountCeiling(top ? (top.base_cent ?? top.total_cent) : 0);
        setMax(ceiling);
        setRange([0, ceiling]);
      },
      () => undefined
    );
    return () => {
      alive = false;
    };
  }, [session]);

  const kinds = useMemo(
    () => [
      { value: '', label: s.kindAll },
      { value: 'factura', label: s.kindInvoice },
      { value: 'nota_credito', label: s.kindCredit },
    ],
    [s]
  );
  const amountFiltered = range[0] !== 0 || range[1] !== max,
    presetKeys = Object.keys(presets).filter((k) => presetLabel(t, k, presets[k]!) !== null),
    filterCount = Number(!!party) + Number(!!kind) + Number(!!date) + Number(amountFiltered) + presetKeys.length;
  const active = found !== null;

  function requestSearch(text: string) {
    if (!session) return;
    clearTimeout(timer.current);
    const mine = ++seq.current;
    setThinking(true);
    const started = performance.now();
    const params = searchQuery({ text, party, kind, date, range, max, preset: presets });
    session.api
      .get<{ busqueda: { total: number; facturas: InvoiceRow[] } }>(paths.search, params)
      .then(
        (r) => ({ total: r.busqueda.total, rows: r.busqueda.facturas, error: false }),
        () => ({ total: 0, rows: [] as InvoiceRow[], error: true })
      )
      .then((r) => {
        if (seq.current !== mine) return;
        timer.current = setTimeout(
          () => {
            setFound({ total: r.total, rows: r.rows });
            setFailed(r.error);
            setThinking(false);
          },
          Math.max(0, THINKING_MS - (performance.now() - started))
        );
      });
  }
  // Con los filtros de un panel (E5-p) o lo buscado en la conversacion, la busqueda sale ya hecha.
  const started = useRef(false);
  useEffect(() => {
    if (started.current || !preset || !session) return;
    started.current = true;
    requestSearch(query);
  });
  // Cambiar un filtro con algo ya buscado lo vuelve a buscar.
  const firstFilters = useRef(true);
  useEffect(() => {
    if (firstFilters.current) {
      firstFilters.current = false;
      return;
    }
    // Como en Aurora: con un filtro puesto ya se ve lo que cumple, aunque no se haya escrito nada.
    if (found !== null || party || kind || date || range[0] !== 0 || range[1] !== max || Object.keys(presets).length) requestSearch(query);
    // Solo cuando cambian los filtros.
  }, [party, kind, date, range[0], range[1], presets]);

  function search(e: FormEvent) {
    e.preventDefault();
    requestSearch(query);
  }
  function reset() {
    setParty('');
    setKind('');
    setDate(undefined);
    setRange([0, max]);
    setPresets({});
  }
  const selectedParty = parties.find((p) => p.value === party);
  const results = found?.rows ?? [];
  const total = found?.total ?? 0;
  const sideOf = (r: InvoiceRow) => (r.sentido === 'saliente' ? s.client : s.provider);
  return (
    <div className='search-workspace search-embedded'>
      <div className='search-shell'>
        <WorkspaceComposer mode='search' autoFocus value={query} onValueChange={setQuery} onSubmit={search} disabled={thinking} />
        <div className='search-filter-bar'>
          <button
            className={'filters-toggle ' + (filtersOpen ? 'filters-open' : '')}
            onClick={() => setFiltersOpen((v) => !v)}
            aria-expanded={filtersOpen}
            aria-controls='search-filters'
          >
            <SlidersHorizontal size={14} /> {s.filters}
            {filterCount > 0 && <span>{filterCount}</span>}
            <ChevronDown size={13} />
          </button>
          <span className='search-filter-hint'>{active ? fmt(total === 1 ? s.resultsOne : s.results, { n: total }) : ''}</span>
          {filterCount > 0 && (
            <button className='filters-reset' onClick={reset}>
              {s.clearFilters} <X size={11} />
            </button>
          )}
        </div>
        <AnimatePresence initial={false}>
          {filtersOpen && (
            <motion.div
              id='search-filters'
              className='search-filters'
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <div className='filters-fields'>
                <PartyCombobox options={parties} value={party} onValueChange={setParty} />
                <FilterComboBox label={s.kind} options={kinds} value={kind} onValueChange={setKind} />
                <div className='filter-date'>
                  <span className='filter-label'>{s.date}</span>
                  <Popover open={dateOpen} onOpenChange={setDateOpen}>
                    <PopoverTrigger asChild>
                      <button type='button' className='filter-date-trigger'>
                        <CalendarDays size={14} />
                        {date ? shortDate(date, locale) : s.dateAnyShort}
                        <ChevronDown size={13} />
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className='calendar-popover'>
                      <GlassCalendar
                        selectedDate={date}
                        onDateSelect={(d) => {
                          setDate(d);
                          setDateOpen(false);
                        }}
                        onClear={() => {
                          setDate(undefined);
                          setDateOpen(false);
                        }}
                      />
                    </PopoverContent>
                  </Popover>
                </div>
              </div>
              <div className='filter-amount-section'>
                <Slider06 range={range} max={max} onRangeChange={setRange} />
                <p>
                  {s.amountNote}
                  <br />
                  {amountFiltered ? s.amountOnly : s.amountAll}
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {filterCount > 0 && (
          <div className='active-filter-chips'>
            {presetKeys.map((k) => (
              <button
                key={k}
                aria-label={fmt(s.removeFilter, { name: presetLabel(t, k, presets[k]!)! })}
                onClick={() =>
                  setPresets((prev) => {
                    const next = { ...prev };
                    delete next[k];
                    return next;
                  })
                }
              >
                {presetLabel(t, k, presets[k]!)}
                <X size={10} />
              </button>
            ))}
            {party && (
              <button onClick={() => setParty('')}>
                <span data-proper-name=''>{selectedParty?.label}</span>
                <X size={10} />
              </button>
            )}
            {kind && (
              <button onClick={() => setKind('')}>
                {kinds.find((k) => k.value === kind)?.label}
                <X size={10} />
              </button>
            )}
            {date && (
              <button onClick={() => setDate(undefined)}>
                {shortDate(date, locale)}
                <X size={10} />
              </button>
            )}
            {amountFiltered && (
              <button onClick={() => setRange([0, max])}>
                {wholeEuros(range[0] ?? 0)}–{wholeEuros(range[1] ?? max)}
                <X size={10} />
              </button>
            )}
          </div>
        )}
        {thinking ? (
          <motion.div className='search-thinking' initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} role='status' aria-live='polite'>
            <span>
              {s.thinking}
              <span className='thinking-dots'>…</span>
            </span>
            <small>{s.thinkingNote}</small>
          </motion.div>
        ) : !active ? null : (
          <section className='search-results' aria-label={s.resultsLabel}>
            <div className='search-results-heading'>
              <span>{fmt(total === 1 ? s.foundOne : s.found, { n: total })}</span>
              <small>{failed ? t.errors.unexpected : s.order}</small>
            </div>
            <div role='status' className='sr-only'>
              {fmt(total === 1 ? s.resultsOne : s.results, { n: total })}
            </div>
            {results.length ? (
              results.map((r) => (
                <motion.a
                  layout
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  key={r.id}
                  role='link'
                  tabIndex={0}
                  className='search-result'
                  onClick={() => onOpenInvoice(r)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      onOpenInvoice(r);
                    }
                  }}
                >
                  <span className='result-file-icon'>
                    <FileText size={19} />
                  </span>
                  <div className='result-info'>
                    <strong data-proper-name=''>{r.numero ?? fmt(t.records.invoice.fallbackTitle, { id: r.id })}</strong>
                    <span>
                      <span data-proper-name=''>{r.contraparte ?? '—'}</span>
                      <i />
                      {sideOf(r)}
                      {r.fecha_factura && (
                        <>
                          <i />
                          {shortDate(new Date(`${r.fecha_factura}T12:00:00`), locale)}
                        </>
                      )}
                    </span>
                  </div>
                  <div className='result-amount'>{r.total_cent === null ? <small>{s.noAmount}</small> : <strong>{formatMoney(r.total_cent)}</strong>}</div>
                  <ArrowUpRight size={15} />
                </motion.a>
              ))
            ) : (
              <div className='search-empty'>
                <FolderSearch size={27} />
                <h2>{s.noMatches}</h2>
                <p>{s.noMatchesText}</p>
                <button
                  onClick={() => {
                    reset();
                    setQuery('');
                    setFound(null);
                  }}
                >
                  {s.startOver}
                </button>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
