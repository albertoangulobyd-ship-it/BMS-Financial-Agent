// El resultado de una lectura de facturas, como lo pinta Aurora (paso 16): las cifras grandes
// ("3 nuevas · 2 repetidas") y una fila por documento. La revision lo quiere tal cual (§2) con
// las categorias del motor (§8.5, paso 7): nuevas (entran sin revisar y pasan por las reglas),
// ya leidas (el mismo fichero, por su huella: no se vuelve a pagar), posibles duplicados (avisos
// B2-B5, esperan a una persona) y fallidas. Viene de processing-workspace.tsx sin el analisis
// inventado (invoice-analysis.ts decidia "repetida" por el nombre del fichero) ni los enlaces #/:
// cada fila se abre con onOpen. Lo montara Procesar cuando la lectura llegue a la app.
import { ArrowUpRight, Check, Copy, RotateCw, TriangleAlert } from 'lucide-react';
import { useT } from '@/i18n';
import { cn } from '@/lib/utils';
import './processing.css';

export type ResultKind = 'new' | 'read' | 'duplicate' | 'failed';

export interface ResultEntry {
  key: string;
  kind: ResultKind;
  /** El numero de la factura o el nombre del fichero (texto). */
  title: string;
  /** La empresa, o el motivo en palabras. */
  subtitle?: string;
}

const ICONS = { new: Check, read: RotateCw, duplicate: Copy, failed: TriangleAlert } as const;

export function ProcessingResult({
  counts,
  entries,
  onOpen,
}: {
  counts: Record<ResultKind, number>;
  entries: ResultEntry[];
  onOpen?: (entry: ResultEntry) => void;
}) {
  const { t } = useT();
  const texts = t.aurora.processing.result;
  const kinds: ResultKind[] = ['new', 'read', 'duplicate', 'failed'];
  return (
    <div className='aurora-root'>
      <div className='processing-complete'>
        <div className='analysis-counts'>
          {kinds
            .filter((k) => k === 'new' || counts[k] > 0)
            .map((k, i) => (
              <div key={k} className={cn('analysis-count', 'analysis-' + k)}>
                {i > 0 && <span className='analysis-divider' aria-hidden='true' />}
                <strong className='num'>{counts[k]}</strong>
                <span>{texts[k]}</span>
              </div>
            ))}
        </div>
        <div className='analysis-report-list'>
          {entries.map((e) => {
            const Icon = ICONS[e.kind];
            return (
              <button type='button' key={e.key} className={cn('analysis-entry', e.kind)} onClick={() => onOpen?.(e)}>
                <span className='analysis-entry-icon' aria-hidden='true'>
                  <Icon size={14} />
                </span>
                <span>
                  <strong>{e.title}</strong>
                  {e.subtitle && <small>{e.subtitle}</small>}
                </span>
                <span className='analysis-entry-status'>{texts.status[e.kind]}</span>
                <ArrowUpRight size={13} aria-hidden='true' />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
