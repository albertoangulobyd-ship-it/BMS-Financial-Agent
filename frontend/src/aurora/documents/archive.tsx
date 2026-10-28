// Las piezas del archivo de Aurora (paso 16), sacadas de document-workspace.tsx del prototipo:
// el marco con "EXPLORAR" y el arbol, la cabecera con el orbe, las pestanas y el buscador de
// carpetas, la rejilla de carpetas, la ficha de la carpeta con sus documentos y la vista
// previa. Sin datos: el prototipo traia seis empresas inventadas (en pesos), las guardaba en
// el navegador (bms-demo-parties-v1), navegaba con rutas #/ y tenia "Agregar muestra",
// "Descargar muestra TXT", la pista de los 12 s y la marca "MUESTRA". Aqui quien monta
// Documentos (screens/documents.tsx) pasa lo que ensena, ya traducido, y recibe los clics; cada
// documento se abre por su id. Todo texto que viene de un dato se pinta como texto. Las migas
// son las de la app (shell/crumbs.tsx): las del prototipo no se traen.
import { useEffect, useRef, type ReactNode } from 'react';
import { ArrowUpRight, ChevronRight, FileText, FolderOpen, Search, X } from 'lucide-react';
import { SiriWave } from '@/aurora/orb/siri-wave';
import { fmt, useT } from '@/i18n';
import { cn } from '@/lib/utils';
import { GlassFolder, type ArtRecipe, type FolderFile } from './glass-folder';
import { TreeView, type TreeViewProps } from './tree-view';
import './archive.css';

/** El dorso de las carpetas de clientes y de proveedores (los del prototipo). */
export const CLIENT_ART: ArtRecipe = {
  style: 'marble',
  colors: ['#0a0a10', '#30133f', '#693c83', '#a089bb', '#232d49', '#b3c4d8'],
  scale: 0.65,
  warp: 3.2,
  gloss: 0.45,
  veins: 0.25,
};
export const PROVIDER_ART: ArtRecipe = {
  ...CLIENT_ART,
  style: 'streak',
  colors: ['#0c121b', '#223751', '#617f9c', '#b6bacb', '#432554', '#9b7fad'],
  angle: -0.5,
  warp: 1.7,
};

/** El marco: arriba la cabecera; a la izquierda "EXPLORAR" con el arbol; a la derecha la
 *  ficha de la carpeta abierta (top) y lo demas (las pestanas, las carpetas). En el movil la
 *  ficha va justo debajo de la cabecera, antes del arbol. */
export function ArchiveLayout({
  heading,
  tree,
  hint,
  top,
  children,
}: {
  heading: ReactNode;
  /** La ficha de la carpeta abierta. */
  top?: ReactNode;
  /** Sin arbol (mientras se leen las carpetas), solo su titulo. */
  tree: (Omit<TreeViewProps, 'label'> & { label?: string }) | null;
  /** Las dos lineas bajo el arbol ("Cada carpeta, una historia..."). */
  hint?: [string, string];
  children: ReactNode;
}) {
  const { t } = useT();
  return (
    <div className='aurora-root'>
      <div className='ws-layout'>
        {heading}
        <aside className='ws-sidebar' aria-label={t.aurora.archive.navigation}>
          <p className='ws-eyebrow'>{t.aurora.archive.explore}</p>
          {tree && <TreeView {...tree} label={tree.label ?? t.aurora.archive.treeLabel} />}
          {hint && (
            <p className='ws-tree-hint'>
              {hint[0]}
              <br />
              {hint[1]}
            </p>
          )}
        </aside>
        {top && <div className='ws-top'>{top}</div>}
        <div className='ws-main'>{children}</div>
      </div>
    </div>
  );
}

/** La cabecera: el orbe (que lleva al inicio), una linea pequena, el titulo y su frase. */
export function ArchiveHeading({
  eyebrow,
  title,
  description,
  onHome,
}: {
  eyebrow: string;
  /** Con un nombre de los datos dentro, marcado (data-proper-name) por quien lo pasa. */
  title: ReactNode;
  description: string;
  onHome?: () => void;
}) {
  const { t } = useT();
  return (
    <div className='ws-heading'>
      <div>
        {onHome ? (
          <button type='button' className='ws-companion' onClick={onHome} aria-label={t.aurora.archive.home}>
            <span className='aurora-shared'>
              <SiriWave size={180} renderScale={1} />
            </span>
          </button>
        ) : (
          <span className='ws-companion'>
            <span className='aurora-shared'>
              <SiriWave size={180} renderScale={1} />
            </span>
          </span>
        )}
        <p className='ws-eyebrow'>{eyebrow}</p>
        <div className='ws-title-line'>
          <h1>{title}</h1>
        </div>
        <p>{description}</p>
      </div>
    </div>
  );
}

/** Las pestanas de la rejilla (Todas, Clientes, Proveedores), con cuantas hay en cada una. */
export function ArchiveTabs<T extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: { id: T; label: string; count: number }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role='group' aria-label={label} className='ws-tabs'>
      {items.map((item) => (
        <button key={item.id} type='button' aria-pressed={item.id === value} onClick={() => onChange(item.id)}>
          {item.label}
          <span className='ws-tab-count'>{item.count}</span>
        </button>
      ))}
    </div>
  );
}

/** El buscador de carpetas (en el prototipo estaba en el codigo y no salia). */
export function ArchiveSearch({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder: string;
}) {
  return (
    <label className='ws-search'>
      <Search size={15} aria-hidden='true' />
      <span className='sr-only'>{label}</span>
      <input type='search' value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} autoComplete='off' spellCheck={false} />
    </label>
  );
}

export function FolderGrid({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className='ws-grid' role='list' aria-label={label}>
      {children}
    </div>
  );
}

/** Una carpeta de la rejilla: de que tipo es, su numero, la carpeta y debajo el saldo y
 *  "Abrir ficha". Al pasar por encima o llegar con el teclado avisa (onWarm): asi se leen sus
 *  documentos antes de abrirla, y asoman en la carpeta. */
export function FolderCell({
  kind,
  index,
  name,
  files,
  total,
  art,
  seed,
  balance,
  active,
  accessory,
  onOpenChange,
  onFileSelect,
  onOpenProfile,
  onWarm,
}: {
  /** "CLIENTE" / "PROVEEDOR", ya traducido. */
  kind: string;
  index: number;
  name: string;
  files: FolderFile[];
  /** Cuantos documentos tiene (aunque aun no se hayan leido). */
  total: number;
  art: ArtRecipe;
  seed: number;
  /** El pendiente en euros ya formateado, o "Nada pendiente". */
  balance: string;
  active: boolean;
  /** Una pastilla de estado sobre la carpeta (la prioridad). */
  accessory?: ReactNode;
  onOpenChange: (open: boolean) => void;
  onFileSelect: (file: FolderFile) => void;
  onOpenProfile: () => void;
  onWarm?: () => void;
}) {
  const { t } = useT();
  return (
    <article
      role='listitem'
      aria-label={name}
      className={cn('ws-folder-cell', active && 'ws-folder-active')}
      onPointerEnter={onWarm}
      onFocus={onWarm}
    >
      <span className='ws-party-type' aria-hidden='true'>
        {kind}
        <span>{String(index + 1).padStart(2, '0')}</span>
      </span>
      <GlassFolder
        frontAccessory={accessory}
        label={name}
        art={art}
        seed={seed}
        width={264}
        files={files}
        total={total}
        appear={false}
        open={active}
        onOpenChange={onOpenChange}
        onFileSelect={(file) => onFileSelect(file)}
      />
      <div className='ws-folder-caption'>
        <span className='num'>{balance}</span>
        <button
          type='button'
          onClick={onOpenProfile}
          aria-label={fmt(active ? t.aurora.archive.viewProfileNamed : t.aurora.archive.openProfileNamed, { name })}
        >
          {active ? t.aurora.archive.viewProfile : t.aurora.archive.openProfile}
          <ArrowUpRight size={13} aria-hidden='true' />
        </button>
      </div>
    </article>
  );
}

/** Un vacio (ninguna carpeta, ninguna que cumpla la busqueda, una carpeta sin documentos), con
 *  la suricata donde ayuda o el icono de la carpeta. */
export function ArchiveEmpty({ title, text, action, mascot }: { title: string; text?: string; action?: ReactNode; mascot?: ReactNode }) {
  return (
    <div className='ws-empty'>
      {mascot ?? <FolderOpen size={30} aria-hidden='true' />}
      <h2>{title}</h2>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

export interface ArchiveFact {
  label: string;
  value: ReactNode;
  /** El valor viene de los datos (un nombre, un numero): no es texto de la app. */
  data?: boolean;
}

/** La ficha de la carpeta: que empresa es y sus datos a la izquierda; "Documentos de la
 *  carpeta" a la derecha (children). */
export function FolderProfile({
  id,
  eyebrow,
  title,
  subtitle,
  facts,
  footer,
  children,
}: {
  id?: string;
  eyebrow: string;
  title: string;
  subtitle?: string;
  facts: ArchiveFact[];
  /** Debajo de los datos (abrir la ficha completa). */
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className='ws-profile' aria-labelledby={id ? `${id}-title` : undefined}>
      <div>
        <p className='ws-eyebrow'>{eyebrow}</p>
        <h2 id={id ? `${id}-title` : undefined} tabIndex={-1} data-proper-name=''>
          {title}
        </h2>
        {subtitle && (
          <p className='ws-tax' data-proper-name=''>
            {subtitle}
          </p>
        )}
        <dl>
          {facts.map((fact) => (
            <div key={fact.label} className='contents'>
              <dt>{fact.label}</dt>
              <dd data-proper-name={fact.data ? '' : undefined}>{fact.value}</dd>
            </div>
          ))}
        </dl>
        {footer && <div className='ws-profile-footer'>{footer}</div>}
      </div>
      <div className='ws-file-table'>{children}</div>
    </section>
  );
}

export interface ArchiveFile {
  id: string;
  name: string;
  meta?: string;
  /** Una pastilla de estado al lado (el pago). */
  status?: ReactNode;
  /** El nombre accesible de la fila (lo que abre). */
  label: string;
  /** Al lado de la fila: descargar el original. */
  aside?: ReactNode;
}

/** "Documentos de la carpeta": su titulo con cuantos hay, el filtro de tipo (si hay mas de
 *  uno) y una fila por documento, que abre su vista previa. */
export function FileTable({
  title,
  count,
  filter,
  files,
  onOpenFile,
  empty,
}: {
  title: string;
  count?: string;
  filter?: ReactNode;
  files: ArchiveFile[];
  onOpenFile: (file: ArchiveFile) => void;
  empty?: ReactNode;
}) {
  return (
    <>
      <div className='ws-table-head'>
        <h3>{title}</h3>
        {count && <span className='ws-count'>{count}</span>}
      </div>
      {filter}
      {files.length === 0 ? (
        empty
      ) : (
        <ul className='ws-file-list'>
          {files.map((f) => (
            <li key={f.id} className='ws-file-row'>
              <button type='button' className='ws-file-open' onClick={() => onOpenFile(f)} aria-label={f.label}>
                <FileText size={17} aria-hidden='true' />
                <span className='ws-file-text'>
                  <strong data-proper-name=''>{f.name}</strong>
                  {f.meta && <small data-proper-name=''>{f.meta}</small>}
                </span>
                {f.status}
                <ChevronRight size={15} aria-hidden='true' />
              </button>
              {f.aside}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/**
 * La vista previa: la hoja clara con lo que el sistema sabe de un documento (dibujada desde
 * el registro, nunca desde el PDF: la CSP no deja marcos y un PDF de terceros no se abre
 * dentro de la app). Escape, la X o un clic fuera la cierran y devuelven el foco.
 */
export function DocumentPreview({
  open,
  onClose,
  eyebrow,
  title,
  subtitle,
  facts,
  note,
  children,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow: string;
  title: string;
  subtitle?: string;
  facts: ArchiveFact[];
  /** Una linea pequena al pie de la hoja (de donde sale lo que dice). */
  note?: string;
  /** Las acciones (Descargar original), debajo de la hoja. */
  children?: ReactNode;
}) {
  const { t } = useT();
  const ref = useRef<HTMLDialogElement>(null);
  // Al cerrar, el foco vuelve a lo que la abrio (la fila, la hoja del abanico o el arbol).
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
    }
    if (!open && dialog.open) {
      dialog.close();
      if (opener.current?.isConnected) opener.current.focus();
      opener.current = null;
    }
  }, [open]);
  return (
    // El envoltorio lleva el ambito de los estilos de Aurora (aurora.css: display contents).
    <div className='aurora-root'>
      <dialog
        ref={ref}
        className='ws-dialog'
        aria-label={title}
        onCancel={(e) => {
          e.preventDefault();
          onClose();
        }}
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        {open && (
          <>
            <div className='ws-dialog-top'>
              <span>{eyebrow}</span>
              <button type='button' autoFocus aria-label={t.aurora.archive.closePreview} onClick={onClose}>
                <X size={19} aria-hidden='true' />
              </button>
            </div>
            <div className='ws-paper'>
              <span className='ws-paper-brand' aria-hidden='true'>
                BMS // <small>finance</small>
              </span>
              <FileText size={26} aria-hidden='true' />
              <h2 data-proper-name=''>{title}</h2>
              {subtitle && <p data-proper-name=''>{subtitle}</p>}
              <hr />
              <dl>
                {facts.map((fact) => (
                  <div key={fact.label} className='contents'>
                    <dt>{fact.label}</dt>
                    <dd data-proper-name={fact.data ? '' : undefined}>{fact.value}</dd>
                  </div>
                ))}
              </dl>
              {note && <p className='ws-paper-note'>{note}</p>}
            </div>
            {children && <div className='ws-dialog-actions'>{children}</div>}
          </>
        )}
      </dialog>
    </div>
  );
}
