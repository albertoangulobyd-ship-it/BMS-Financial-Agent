// Las piezas de la busqueda de Aurora (paso 16), de search-workspace.tsx del prototipo: la barra
// de "Filtros" con su contador y "Limpiar filtros", las pastillas de cada filtro activo con su
// X, la lista de resultados, el "Pensando..." con el orbe de particulas y el estado vacio con
// "Empezar de nuevo". La revision las quiere tal cual (§2) sobre nuestra busqueda
// (/api/v2/buscar); lo que se quita:
// - los 18 documentos fijos, el 1,5 s de "Pensando" de adorno y las fechas inventadas;
// - el deslizador de importe con NumberFlow y el calendario con date-fns (dos bibliotecas que
//   no traemos): el importe sera "Desde / Hasta" en euros y la fecha un rango, con nuestros
//   campos (revision §4.23);
// - los enlaces #/ (un resultado se abre con onOpen) y los pesos mexicanos (los importes los
//   formatea quien llama desde los centimos).
import type { ReactNode } from 'react';
import { ArrowUpRight, ChevronDown, FileText, FolderSearch, SlidersHorizontal, X } from 'lucide-react';
import { ThinkingOrb } from '@/aurora/thinking-orb/thinking-orb';
import { fmt, useT } from '@/i18n';
import { cn } from '@/lib/utils';
import './search.css';

export function FilterBar({
  open,
  onToggle,
  count,
  results,
  onClear,
  controls,
}: {
  open: boolean;
  onToggle: () => void;
  /** Cuantos filtros hay puestos. */
  count: number;
  /** Cuantos resultados hay (null antes de buscar). */
  results: number | null;
  onClear: () => void;
  /** El id del panel de filtros (aria-controls). */
  controls: string;
}) {
  const { t } = useT();
  const texts = t.aurora.search;
  return (
    <div className='aurora-root'>
      <div className='search-filter-bar'>
        <button
          type='button'
          className={cn('filters-toggle', open && 'filters-open')}
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={controls}
        >
          <SlidersHorizontal size={14} aria-hidden='true' /> {texts.filters}
          {count > 0 && <span>{count}</span>}
          <ChevronDown size={13} aria-hidden='true' />
        </button>
        <span className='search-filter-hint'>
          {results === null ? '' : results === 1 ? texts.resultsOne : fmt(texts.results, { n: results })}
        </span>
        {count > 0 && (
          <button type='button' className='filters-reset' onClick={onClear}>
            {texts.clearFilters} <X size={11} aria-hidden='true' />
          </button>
        )}
      </div>
    </div>
  );
}

export interface ActiveFilter {
  id: string;
  label: string;
  onRemove: () => void;
}

export function FilterChips({ filters }: { filters: ActiveFilter[] }) {
  const { t } = useT();
  if (!filters.length) return null;
  return (
    <div className='aurora-root'>
      <div className='active-filter-chips'>
        {filters.map((f) => (
          <button type='button' key={f.id} onClick={f.onRemove} aria-label={fmt(t.aurora.search.removeFilter, { name: f.label })}>
            {f.label}
            <X size={10} aria-hidden='true' />
          </button>
        ))}
      </div>
    </div>
  );
}

/** Mientras busca de verdad: el orbe de particulas y "Pensando...". */
export function SearchThinking() {
  const { t } = useT();
  return (
    <div className='aurora-root'>
      <div className='search-thinking' role='status' aria-live='polite'>
        <ThinkingOrb mode='orbits' label={t.aurora.search.thinking} size={160} />
        <span>{t.aurora.search.thinking}</span>
      </div>
    </div>
  );
}

export function SearchResults({ heading, note, children }: { heading: string; note?: string; children: ReactNode }) {
  const { t } = useT();
  return (
    <div className='aurora-root'>
      <section className='search-results' aria-label={t.aurora.search.resultsLabel}>
        <div className='search-results-heading'>
          <span>{heading}</span>
          {note && <small>{note}</small>}
        </div>
        {children}
      </section>
    </div>
  );
}

/** Una fila de resultado: que es, de quien y cuando, y su importe (ya formateado). */
export function SearchResult({
  title,
  details,
  amount,
  onOpen,
}: {
  title: string;
  details: string[];
  amount?: string | null;
  onOpen: () => void;
}) {
  const { t } = useT();
  return (
    <button type='button' className='search-result' onClick={onOpen}>
      <span className='result-file-icon' aria-hidden='true'>
        <FileText size={19} />
      </span>
      <div className='result-info'>
        <strong>{title}</strong>
        <span>
          {details.map((d, i) => (
            <span key={i}>
              {i > 0 && <i aria-hidden='true' />}
              {d}
            </span>
          ))}
        </span>
      </div>
      <div className='result-amount'>{amount ? <strong className='num'>{amount}</strong> : <small>{t.aurora.search.noAmount}</small>}</div>
      <ArrowUpRight size={15} aria-hidden='true' />
    </button>
  );
}

export function SearchEmpty({ onStartOver }: { onStartOver: () => void }) {
  const { t } = useT();
  const texts = t.aurora.search;
  return (
    <div className='search-empty'>
      <FolderSearch size={27} aria-hidden='true' />
      <h2>{texts.noMatches}</h2>
      <p>{texts.noMatchesText}</p>
      <button type='button' onClick={onStartOver}>
        {texts.startOver}
      </button>
    </div>
  );
}
