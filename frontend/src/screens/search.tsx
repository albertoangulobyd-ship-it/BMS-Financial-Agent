// Zoeken / Search / Buscar (revision del paso 16, §1b filas 28 a 35 y §2): la busqueda de Aurora
// con sus filtros en pastillas, sobre la busqueda del motor (GET /api/v2/buscar) y no sobre 18
// documentos fijos. Un campo (numero o nombre), "Filtros" con su contador, el tipo de documento,
// el sentido, el cliente o el proveedor (cliente_id, proveedor_id), la fecha de la factura (un
// rango, dd-mm-aaaa), el importe sin IVA ("desde" y "hasta" en euros, como filtra el motor) y el
// pago (pendiente, vencido, pagado). Cada filtro puesto sale como una pastilla con su X; "Limpiar
// filtros" los quita y, sin resultados, "Empezar de nuevo" lo quita todo. Un resultado abre su
// factura; "Cerrar" (y "Volver") vuelve a donde se estaba: la busqueda es un paso del camino.
// Lo escrito y los filtros se recuerdan mientras la app esta abierta (lib/view-memory.ts), en
// memoria: al volver de una factura, la busqueda sigue como estaba.
import { useEffect, useId, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { FilterBar, FilterChips, SearchEmpty, SearchResult, SearchResults, type ActiveFilter } from '@/aurora/search/search-parts';
import { PageHeader, Screen } from '@/components/page-header';
import { ErrorState, Loading } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { StatusPill } from '@/components/status-pill';
import { fmt, useT, type Messages } from '@/i18n';
import { paymentStateLabel, stateLabel } from '@/i18n/domain';
import { paths, type InvoiceRow } from '@/lib/api';
import type { PartyRow } from '@/lib/api-types';
import { formatDate, formatMoney, parseTypedDate } from '@/lib/format';
import { useRefresh } from '@/lib/refresh';
import { useSession } from '@/lib/session';
import { twinMarks } from '@/lib/twins';
import { rememberView, useViewState } from '@/lib/view-memory';
import { useNav } from '@/shell/navigation';
import { centsToInput, parseEuros } from './money-model';
import { SEARCH_ROUTE, recordRoute, routeKey } from './registry';
import { useLoad } from './use-load';

/** Los filtros como se ven y se escriben (fechas dd-mm-aaaa, importes en euros tecleados). */
export interface FinderFilters {
  texto: string;
  tipo: '' | 'factura' | 'nota_credito';
  sentido: '' | 'saliente' | 'entrante';
  /** "cliente:12" o "proveedor:7" (vacio: cualquiera). */
  parte: string;
  desde: string;
  hasta: string;
  min: string;
  max: string;
  pago: '' | 'pendiente' | 'vencida' | 'pagada';
}

export const EMPTY_FILTERS: FinderFilters = { texto: '', tipo: '', sentido: '', parte: '', desde: '', hasta: '', min: '', max: '', pago: '' };

/** Cuantos resultados se ensenan (el motor dice cuantos hay en total). */
export const FINDER_LIMIT = 50;

type Problem = { field: 'desde' | 'hasta' | 'min' | 'max' } | null;

/**
 * Los parametros de GET /api/v2/buscar para unos filtros (sin React: lo prueban las pruebas en
 * el navegador contra la API). null si un campo no se entiende (y cual).
 */
export function finderQuery(f: FinderFilters): { query: Record<string, string> } | { problem: NonNullable<Problem> } {
  const query: Record<string, string> = { limite: String(FINDER_LIMIT), orden: 'fecha' };
  if (f.texto.trim()) query.texto = f.texto.trim();
  if (f.tipo) query.tipo = f.tipo;
  if (f.sentido) query.sentido = f.sentido;
  const [kind, id] = f.parte.split(':');
  if (kind === 'cliente' && id) query.cliente_id = id;
  if (kind === 'proveedor' && id) query.proveedor_id = id;
  for (const [field, name] of [
    ['desde', 'fecha_desde'],
    ['hasta', 'fecha_hasta'],
  ] as const) {
    if (!f[field].trim()) continue;
    const day = parseTypedDate(f[field]);
    if (day === null) return { problem: { field } };
    query[name] = day;
  }
  for (const [field, name] of [
    ['min', 'importe_min'],
    ['max', 'importe_max'],
  ] as const) {
    if (!f[field].trim()) continue;
    const cents = parseEuros(f[field]);
    if (cents === null || cents < 0) return { problem: { field } };
    // El motor lee "1000" o "1000,50": sin miles ni signo.
    query[name] = centsToInput(cents);
  }
  if (f.pago === 'pendiente') query.pendiente = 'si';
  if (f.pago === 'vencida') query.vencida = 'si';
  if (f.pago === 'pagada') query.pagada = 'si';
  return { query };
}

/** Si hay algo que buscar: un texto o algun filtro. */
export function hasSomething(f: FinderFilters): boolean {
  return Object.values(f).some((v) => v.trim() !== '');
}

/** Cuantos filtros hay puestos (el texto no es un filtro). */
export function filterCount(f: FinderFilters): number {
  return (Object.keys(f) as (keyof FinderFilters)[]).filter((k) => k !== 'texto' && f[k].trim() !== '').length;
}

/** Abre la busqueda con filtros encima de donde se esta, ya con lo escrito (desde Ctrl+K o la
 *  caja del inicio). */
export function openSearch(nav: { open: (route: typeof SEARCH_ROUTE) => void }, texto: string): void {
  rememberView(routeKey(SEARCH_ROUTE), 'finder', { ...EMPTY_FILTERS, texto: texto.trim() });
  nav.open(SEARCH_ROUTE);
}

interface Found {
  total: number;
  facturas: InvoiceRow[];
  /** El dia de la cache de los estados (el filtro "vencida" del motor va por ella). */
  estado_del: string | null;
  al_dia: boolean;
}

/** "Betaald · volgens de bank": lo pagado siempre con su fuente (decision 5), como las listas. */
function paidWithSource(t: Messages, label: string, source: InvoiceRow['fuente_pago']): string {
  if (!source) return label;
  const from = source === 'banco' ? t.payments.listBank : source === 'exact' ? t.payments.listExact : t.payments.listManual;
  return `${label} · ${from}`;
}

export function SearchScreen({ navKey }: { navKey: string }) {
  const { t, lang } = useT();
  const { session } = useSession();
  const { version } = useRefresh();
  const nav = useNav();
  const panelId = useId();
  const [applied, setApplied] = useViewState<FinderFilters>(navKey, 'finder', EMPTY_FILTERS);
  const [draft, setDraft] = useState<FinderFilters>(applied);
  const [open, setOpen] = useViewState<boolean>(navKey, 'finder-open', filterCount(applied) > 0);
  const [problem, setProblem] = useState<Problem>(null);
  const [found, setFound] = useState<{ key: string; data?: Found; error?: unknown } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const text = t.finder;

  useEffect(() => nav.setTitle(navKey, text.title), [nav, navKey, text.title]);

  // Las listas de clientes y proveedores, para elegir uno (una vez y tras cada orden).
  const [parties] = useLoad(
    () =>
      Promise.all([
        session!.api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
        session!.api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores),
      ]),
    [session, version]
  );
  const clients = parties.status === 'ready' ? parties.data[0] : [];
  const providers = parties.status === 'ready' ? parties.data[1] : [];

  const built = useMemo(() => finderQuery(applied), [applied]);
  const key = 'query' in built ? JSON.stringify(built.query) : '';
  const wanted = hasSomething(applied) && 'query' in built;

  useEffect(() => {
    if (!session || !wanted) return;
    let alive = true;
    setFound({ key });
    session.api
      .get<{ busqueda: Found }>(paths.search, (built as { query: Record<string, string> }).query)
      .then(
        (r) =>
          alive &&
          setFound({ key, data: { total: r.busqueda.total, facturas: r.busqueda.facturas, estado_del: r.busqueda.estado_del, al_dia: r.busqueda.al_dia } })
      )
      .catch((error: unknown) => alive && setFound({ key, error }));
    return () => {
      alive = false;
    };
    // `key` es la busqueda entera: se pide otra vez solo si cambia (o tras una orden).
  }, [session, version, key, wanted, attempt]);

  const apply = (next: FinderFilters) => {
    const check = finderQuery(next);
    if ('problem' in check) {
      setProblem(check.problem);
      return;
    }
    setProblem(null);
    setApplied(next);
  };
  const change = (patch: Partial<FinderFilters>, now = false) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    // Lo que se elige (una lista) se aplica ya; lo que se escribe, al buscar.
    if (now) apply({ ...applied, ...patch });
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    apply(draft);
  };
  const remove = (patch: Partial<FinderFilters>) => {
    const nextDraft = { ...draft, ...patch };
    setDraft(nextDraft);
    apply({ ...applied, ...patch });
  };
  const clearFilters = () => {
    const next = { ...EMPTY_FILTERS, texto: applied.texto };
    setDraft({ ...EMPTY_FILTERS, texto: draft.texto });
    setProblem(null);
    setApplied(next);
  };
  const startOver = () => {
    setDraft(EMPTY_FILTERS);
    setProblem(null);
    setApplied(EMPTY_FILTERS);
  };

  const partyName = (value: string): string => {
    const [kind, id] = value.split(':');
    const list = kind === 'cliente' ? clients : providers;
    return list.find((p) => String(p.id) === id)?.nombre ?? value;
  };
  const chips: ActiveFilter[] = [];
  if (applied.tipo) chips.push({ id: 'tipo', label: stateLabel(lang, 'tipo_factura', applied.tipo) ?? applied.tipo, onRemove: () => remove({ tipo: '' }) });
  if (applied.sentido)
    chips.push({ id: 'sentido', label: applied.sentido === 'saliente' ? text.sales : text.purchases, onRemove: () => remove({ sentido: '' }) });
  if (applied.parte) chips.push({ id: 'parte', label: partyName(applied.parte), onRemove: () => remove({ parte: '' }) });
  if (applied.desde) chips.push({ id: 'desde', label: fmt(text.chipFrom, { date: formatDate(parseTypedDate(applied.desde)) }), onRemove: () => remove({ desde: '' }) });
  if (applied.hasta) chips.push({ id: 'hasta', label: fmt(text.chipTo, { date: formatDate(parseTypedDate(applied.hasta)) }), onRemove: () => remove({ hasta: '' }) });
  if (applied.min) chips.push({ id: 'min', label: fmt(text.chipMin, { amount: formatMoney(parseEuros(applied.min)) }), onRemove: () => remove({ min: '' }) });
  if (applied.max) chips.push({ id: 'max', label: fmt(text.chipMax, { amount: formatMoney(parseEuros(applied.max)) }), onRemove: () => remove({ max: '' }) });
  if (applied.pago) {
    const label = applied.pago === 'pendiente' ? text.open : applied.pago === 'vencida' ? text.overdue : text.paid;
    chips.push({ id: 'pago', label, onRemove: () => remove({ pago: '' }) });
  }

  const current = found && found.key === key ? found : null;
  const results = current?.data;
  // "1 van 2" en dos facturas con el mismo numero y la misma empresa, como en las listas.
  const twins = twinMarks(results?.facturas ?? []);
  const fieldLabel = problem ? { desde: text.dateFrom, hasta: text.dateTo, min: text.amountFrom, max: text.amountTo }[problem.field] : '';

  return (
    <Screen>
      <PageHeader
        title={text.title}
        description={text.description}
        action={
          <Button variant='outline' size='sm' onClick={nav.back}>
            <X className='mr-1 h-4 w-4' aria-hidden='true' />
            {text.close}
          </Button>
        }
      />
      <form onSubmit={onSubmit} className='flex flex-col gap-3' role='search' aria-label={text.title}>
        <div className='flex flex-wrap items-end gap-2'>
          <div className='flex min-w-[16rem] flex-1 flex-col gap-1.5'>
            <Label htmlFor={`${panelId}-q`}>{text.query}</Label>
            <Input
              id={`${panelId}-q`}
              type='search'
              value={draft.texto}
              onChange={(e) => change({ texto: e.target.value })}
              placeholder={text.queryPlaceholder}
              autoComplete='off'
              spellCheck={false}
            />
          </div>
          <Button type='submit'>{text.submit}</Button>
        </div>
        <FilterBar
          open={open}
          onToggle={() => setOpen(!open)}
          count={filterCount(applied)}
          results={results ? results.total : null}
          onClear={clearFilters}
          controls={panelId}
        />
        <div id={panelId} hidden={!open} className='rounded-md border border-border bg-card px-4 py-4'>
          <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
            <Field label={text.kind} id={`${panelId}-tipo`}>
              <Select id={`${panelId}-tipo`} value={draft.tipo} onChange={(v) => change({ tipo: v as FinderFilters['tipo'] }, true)}>
                <option value=''>{text.kindAll}</option>
                <option value='factura'>{stateLabel(lang, 'tipo_factura', 'factura')}</option>
                <option value='nota_credito'>{stateLabel(lang, 'tipo_factura', 'nota_credito')}</option>
              </Select>
            </Field>
            <Field label={text.direction} id={`${panelId}-sentido`}>
              <Select id={`${panelId}-sentido`} value={draft.sentido} onChange={(v) => change({ sentido: v as FinderFilters['sentido'] }, true)}>
                <option value=''>{text.directionAll}</option>
                <option value='saliente'>{text.sales}</option>
                <option value='entrante'>{text.purchases}</option>
              </Select>
            </Field>
            <Field label={text.party} id={`${panelId}-parte`}>
              <Select id={`${panelId}-parte`} value={draft.parte} onChange={(v) => change({ parte: v }, true)}>
                <option value=''>{text.partyAll}</option>
                <optgroup label={text.clients}>
                  {clients.map((c) => (
                    <option key={`c${c.id}`} value={`cliente:${c.id}`}>
                      {c.nombre}
                    </option>
                  ))}
                </optgroup>
                <optgroup label={text.providers}>
                  {providers.map((p) => (
                    <option key={`p${p.id}`} value={`proveedor:${p.id}`}>
                      {p.nombre}
                    </option>
                  ))}
                </optgroup>
              </Select>
            </Field>
            <Field label={text.dateFrom} id={`${panelId}-desde`}>
              <Input
                id={`${panelId}-desde`}
                inputMode='numeric'
                placeholder={t.action.datePlaceholder}
                value={draft.desde}
                onChange={(e) => change({ desde: e.target.value })}
                aria-invalid={problem?.field === 'desde' || undefined}
              />
            </Field>
            <Field label={text.dateTo} id={`${panelId}-hasta`}>
              <Input
                id={`${panelId}-hasta`}
                inputMode='numeric'
                placeholder={t.action.datePlaceholder}
                value={draft.hasta}
                onChange={(e) => change({ hasta: e.target.value })}
                aria-invalid={problem?.field === 'hasta' || undefined}
              />
            </Field>
            <Field label={text.payment} id={`${panelId}-pago`}>
              <Select id={`${panelId}-pago`} value={draft.pago} onChange={(v) => change({ pago: v as FinderFilters['pago'] }, true)}>
                <option value=''>{text.paymentAll}</option>
                <option value='pendiente'>{text.open}</option>
                <option value='vencida'>{text.overdue}</option>
                <option value='pagada'>{text.paid}</option>
              </Select>
            </Field>
            <Field label={`${text.amountFrom} (€)`} id={`${panelId}-min`}>
              <Input
                id={`${panelId}-min`}
                inputMode='decimal'
                value={draft.min}
                onChange={(e) => change({ min: e.target.value })}
                aria-invalid={problem?.field === 'min' || undefined}
              />
            </Field>
            <Field label={`${text.amountTo} (€)`} id={`${panelId}-max`}>
              <Input
                id={`${panelId}-max`}
                inputMode='decimal'
                value={draft.max}
                onChange={(e) => change({ max: e.target.value })}
                aria-invalid={problem?.field === 'max' || undefined}
              />
            </Field>
          </div>
          <div className='mt-4 flex justify-end'>
            <Button type='submit' variant='outline' size='sm'>
              {text.submit}
            </Button>
          </div>
        </div>
        {problem && (
          <p role='alert' className='text-sm font-medium text-late-foreground'>
            {fmt(problem.field === 'desde' || problem.field === 'hasta' ? text.badDate : text.badAmount, { field: fieldLabel })}
          </p>
        )}
        <FilterChips filters={chips} />
      </form>

      <div className='mt-4' aria-live='polite'>
        {!wanted && !problem && <p className='py-6 text-center text-[13px] text-muted-foreground'>{text.start}</p>}
        {wanted && !current?.data && !current?.error && <Loading className='py-6' label={t.ask.searching} />}
        {current?.error !== undefined && <ErrorState error={current.error} onRetry={() => setAttempt((n) => n + 1)} />}
        {/* El estado de pago (y el filtro "Vervallen") es el de la ultima pasada del motor:
            si es de otro dia, se dice, como en el inicio y en Te ontvangen / Te betalen. */}
        {results && !results.al_dia && (
          <div role='status' className='mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]'>
            <StatusPill group='fuente' state='caducada' />
            <span>{fmt(t.overview.stale, { date: formatDate(results.estado_del) })}</span>
          </div>
        )}
        {results && results.total === 0 && (
          <div className='aurora-root'>
            <SearchEmpty onStartOver={startOver} />
          </div>
        )}
        {results && results.total > 0 && (
          <SearchResults
            heading={results.total === 1 ? text.headingOne : fmt(text.heading, { n: results.total })}
            note={results.total > results.facturas.length ? fmt(text.more, { shown: results.facturas.length, total: results.total }) : undefined}
          >
            {results.facturas.map((f) => (
              <SearchResult
                key={f.id}
                title={f.numero ?? String(f.id)}
                properTitle={f.numero !== null}
                details={[
                  ...(twins.get(f.id) ? [fmt(t.common.twin, { n: twins.get(f.id)!.n, of: twins.get(f.id)!.of })] : []),
                  stateLabel(lang, 'tipo_factura', f.tipo) ?? f.tipo,
                  ...(f.contraparte ? [{ text: f.contraparte, proper: true as const }] : []),
                  formatDate(f.fecha_factura),
                  ...(f.estado_pago
                    ? [
                        f.estado_pago === 'pagada'
                          ? paidWithSource(t, paymentStateLabel(lang, 'pagada') ?? 'pagada', f.fuente_pago)
                          : (paymentStateLabel(lang, f.estado_pago) ?? f.estado_pago),
                      ]
                    : []),
                ]}
                amount={f.total_cent !== null ? formatMoney(f.total_cent) : null}
                label={fmt(t.common.openRecord, { what: `${t.records.invoice.label} ${f.numero ?? f.id}` })}
                onOpen={() => nav.open(recordRoute('invoice', f.id))}
              />
            ))}
          </SearchResults>
        )}
      </div>
    </Screen>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return (
    <div className='flex flex-col gap-1.5'>
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function Select({ id, value, onChange, children }: { id: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className='h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
    >
      {children}
    </select>
  );
}
