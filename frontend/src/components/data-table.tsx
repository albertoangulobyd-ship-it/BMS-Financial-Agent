// La tabla de todas las listas. Seis columnas como mucho (lo exige el tipo: una lista
// mas ancha no se entiende), cifras alineadas a la derecha y una columna "principal" que
// es un boton: con el raton se abre la fila entera, con el teclado ese boton (Tab y
// Intro). Abrir una fila abre su ficha en una pestana (useTabs().openRoute).
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface Column<Row> {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  /** Importes y horas a la derecha, con cifras alineadas. */
  align?: 'left' | 'right';
  /** El contenido de esta columna es el boton que abre la fila. */
  primary?: boolean;
  /** Ancho CSS de la columna ("8rem"); sin el, se reparte. */
  width?: string;
  /** Texto del encabezado para el lector de pantalla si el visible no basta. */
  srHeader?: string;
  /** Una cifra que se deduce de las otras (el coste, de opbrengst y marge): por debajo de
   *  1280 px no se pinta, para que "Waarom" quepa a 1024 px sin desplazarse. */
  wideOnly?: boolean;
}

/** De una a seis columnas, ni una mas. */
export type Columns<Row> =
  | readonly [Column<Row>]
  | readonly [Column<Row>, Column<Row>]
  | readonly [Column<Row>, Column<Row>, Column<Row>]
  | readonly [Column<Row>, Column<Row>, Column<Row>, Column<Row>]
  | readonly [Column<Row>, Column<Row>, Column<Row>, Column<Row>, Column<Row>]
  | readonly [Column<Row>, Column<Row>, Column<Row>, Column<Row>, Column<Row>, Column<Row>];

export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  onOpen,
  openLabel,
  caption,
  empty,
}: {
  columns: Columns<Row>;
  rows: readonly Row[];
  rowKey: (row: Row) => string | number;
  /** Lo que hace abrir una fila; sin el, las filas no se abren. */
  onOpen?: (row: Row) => void;
  /** El nombre accesible del boton de una fila ("Factura KT-202608 openen"). */
  openLabel?: (row: Row) => string;
  /** Lo que es la tabla, para el lector de pantalla. */
  caption: string;
  /** Lo que se ensena sin filas (un EmptyState). */
  empty?: ReactNode;
}) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div className='overflow-x-auto rounded-md border border-border bg-card'>
      <table className='w-full border-collapse text-left'>
        <caption className='sr-only'>{caption}</caption>
        <thead>
          <tr className='border-b border-border bg-[#f2efe8]'>
            {columns.map((col) => (
              <th
                key={col.key}
                scope='col'
                style={col.width ? { width: col.width } : undefined}
                className={cn(
                  'px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground',
                  col.align === 'right' && 'text-right',
                  col.wideOnly && 'hidden xl:table-cell'
                )}
              >
                {col.header}
                {col.srHeader && <span className='sr-only'>{col.srHeader}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onOpen ? () => onOpen(row) : undefined}
              className={cn(
                'border-b border-[#ebe7df] last:border-b-0 align-top',
                onOpen && 'cursor-pointer hover:bg-[#f4f1ea]'
              )}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn('px-3 py-2.5', col.align === 'right' && 'text-right num', col.wideOnly && 'hidden xl:table-cell')}
                >
                  {col.primary && onOpen ? (
                    <button
                      type='button'
                      aria-label={openLabel?.(row)}
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpen(row);
                      }}
                      className='rounded-sm text-left font-medium text-primary hover:underline'
                    >
                      {col.cell(row)}
                    </button>
                  ) : (
                    col.cell(row)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
