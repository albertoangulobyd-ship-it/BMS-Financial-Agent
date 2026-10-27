// Las piezas del archivo de Aurora (paso 16), sacadas de document-workspace.tsx del prototipo:
// el marco con "EXPLORAR" y el arbol, las migas, la cabecera con el orbe, la rejilla de
// carpetas, la ficha de la carpeta con sus documentos y la vista previa. Sin datos: el
// prototipo traia seis empresas inventadas (en pesos), las guardaba en el navegador
// (bms-demo-parties-v1), navegaba con rutas #/ y tenia "Agregar muestra", "Descargar muestra
// TXT", la pista de los 12 s y la marca "MUESTRA". Aqui quien monta Documentos (el paso de
// Documentos con datos reales, revision §8.5) pasa lo que ensena, ya traducido, y recibe los
// clics; cada documento se abre por su id. Todo texto que viene de un dato se pinta como texto.
import { useEffect, useRef, type ReactNode } from 'react';
import { ArrowUpRight, ChevronRight, FileText, FolderOpen, X } from 'lucide-react';
import { AuroraOrb } from '@/aurora/orb/aurora-orb';
import { useT } from '@/i18n';
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

export interface Crumb {
  label: string;
  /** Sin onSelect es donde se esta (aria-current). */
  onSelect?: () => void;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useT();
  return (
    <nav className='ws-breadcrumbs' aria-label={t.aurora.archive.breadcrumbs}>
      {items.map((item, i) => (
        <span key={i} className='ws-crumb'>
          {i > 0 && <ChevronRight size={12} aria-hidden='true' />}
          {item.onSelect ? (
            <button type='button' onClick={item.onSelect}>
              {item.label}
            </button>
          ) : (
            <span aria-current='page'>{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

/** El marco: a la izquierda "EXPLORAR" con el arbol, a la derecha lo demas. */
export function ArchiveLayout({
  tree,
  hint,
  children,
}: {
  tree: Omit<TreeViewProps, 'label'> & { label?: string };
  /** Las dos lineas bajo el arbol ("Cada carpeta, una historia..."). */
  hint?: [string, string];
  children: ReactNode;
}) {
  const { t } = useT();
  return (
    <div className='aurora-root'>
      <div className='ws-layout'>
        <aside className='ws-sidebar' aria-label={t.aurora.archive.navigation}>
          <p className='ws-eyebrow'>{t.aurora.archive.explore}</p>
          <TreeView {...tree} label={tree.label ?? t.aurora.archive.treeLabel} />
          {hint && (
            <p className='ws-tree-hint'>
              {hint[0]}
              <br />
              {hint[1]}
            </p>
          )}
        </aside>
        <div className='ws-shell'>{children}</div>
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
  orbActive = false,
}: {
  eyebrow: string;
  title: string;
  description: string;
  onHome?: () => void;
  orbActive?: boolean;
}) {
  const { t } = useT();
  return (
    <div className='ws-heading'>
      <div>
        {onHome ? (
          <button type='button' className='ws-companion' onClick={onHome} aria-label={t.aurora.archive.home}>
            <AuroraOrb label={t.aurora.name} size={140} active={orbActive} />
          </button>
        ) : (
          <span className='ws-companion'>
            <AuroraOrb label={t.aurora.name} size={140} active={orbActive} />
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

export function FolderGrid({ children }: { children: ReactNode }) {
  return <div className='ws-grid'>{children}</div>;
}

/** Una carpeta de la rejilla: de que tipo es, su numero, la carpeta y debajo el saldo y
 *  "Abrir ficha". */
export function FolderCell({
  kind,
  index,
  name,
  files,
  art,
  seed,
  balance,
  active,
  accessory,
  onOpenChange,
  onFileSelect,
  onOpenProfile,
}: {
  /** "CLIENTE" / "PROVEEDOR", ya traducido. */
  kind: string;
  index: number;
  name: string;
  files: FolderFile[];
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
}) {
  const { t } = useT();
  return (
    <article className={cn('ws-folder-cell', active && 'ws-folder-active')}>
      <span className='ws-party-type'>
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
        appear={false}
        open={active}
        onOpenChange={onOpenChange}
        onFileSelect={(file) => onFileSelect(file)}
      />
      <div className='ws-folder-caption'>
        <span>{balance}</span>
        <button type='button' onClick={onOpenProfile}>
          {active ? t.aurora.archive.viewProfile : t.aurora.archive.openProfile}
          <ArrowUpRight size={13} aria-hidden='true' />
        </button>
      </div>
    </article>
  );
}

export function ArchiveEmpty({ title, text, action }: { title: string; text: string; action?: ReactNode }) {
  return (
    <div className='ws-empty'>
      <FolderOpen size={30} aria-hidden='true' />
      <h2>{title}</h2>
      <p>{text}</p>
      {action}
    </div>
  );
}

export interface ArchiveFact {
  label: string;
  value: ReactNode;
}

export interface ArchiveFile {
  id: string;
  name: string;
  meta?: string;
  /** Una pastilla de estado al lado (el pago, la prioridad). */
  status?: ReactNode;
}

/** La ficha de la carpeta: que empresa es, sus datos y "Documentos de la carpeta". */
export function FolderProfile({
  eyebrow,
  title,
  subtitle,
  facts,
  files,
  onOpenFile,
  emptyFiles,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  facts: ArchiveFact[];
  files: ArchiveFile[];
  onOpenFile: (file: ArchiveFile) => void;
  emptyFiles: string;
}) {
  const { t } = useT();
  return (
    <section className='ws-profile' aria-label={title}>
      <div>
        <p className='ws-eyebrow'>{eyebrow}</p>
        <h2>{title}</h2>
        {subtitle && <p className='ws-tax'>{subtitle}</p>}
        <dl>
          {facts.map((fact) => (
            <div key={fact.label} className='contents'>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className='ws-file-table'>
        <div className='ws-table-head'>
          <span>{t.aurora.archive.folderDocuments}</span>
        </div>
        {files.length === 0 && <p className='ws-file-empty'>{emptyFiles}</p>}
        {files.map((f) => (
          <button type='button' key={f.id} onClick={() => onOpenFile(f)}>
            <FileText size={17} aria-hidden='true' />
            <span>
              <strong>{f.name}</strong>
              {f.meta && <small>{f.meta}</small>}
            </span>
            {f.status}
            <ChevronRight size={15} aria-hidden='true' />
          </button>
        ))}
      </div>
    </section>
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
  children,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow: string;
  title: string;
  subtitle?: string;
  facts: ArchiveFact[];
  /** Las acciones (Descargar original), debajo de la hoja. */
  children?: ReactNode;
}) {
  const { t } = useT();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
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
              <span className='ws-paper-brand'>
                BMS // <small>finance</small>
              </span>
              <FileText size={26} aria-hidden='true' />
              <h2>{title}</h2>
              {subtitle && <p>{subtitle}</p>}
              <hr />
              <dl>
                {facts.map((fact) => (
                  <div key={fact.label} className='contents'>
                    <dt>{fact.label}</dt>
                    <dd>{fact.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            {children && <div className='ws-dialog-actions'>{children}</div>}
          </>
        )}
      </dialog>
    </div>
  );
}
