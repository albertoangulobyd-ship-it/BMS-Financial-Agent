// El arbol del archivo de Aurora (paso 16): "EXPLORAR" en Documentos, clientes y proveedores
// con sus documentos. Viene de tree-view.tsx del prototipo casi tal cual: se maneja entero con
// el teclado (flechas, Inicio, Fin, la primera letra, Intro y espacio) con el patron "tree" de
// ARIA, y lo anima framer-motion (quieto con "menos movimiento"). Cambia: la ayuda para lectores
// de pantalla sale de los diccionarios y los tipos aguantan noUncheckedIndexedAccess.
import { useCallback, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useT } from "@/i18n";
const EASE = [0.23, 1, 0.32, 1] as const,
  LEAVE = [0.4, 0, 1, 1] as const;
const SMALL = {
  type: "spring",
  stiffness: 700,
  damping: 46,
  mass: 0.5,
} as const;
const OPEN_H = { duration: 0.28, ease: EASE },
  OPEN_O = { duration: 0.18, ease: EASE },
  SHUT_H = { duration: 0.2, ease: LEAVE },
  SHUT_O = { duration: 0.14, ease: LEAVE },
  STILL = { duration: 0 };
export type TreeNode = {
  id: string;
  label: string;
  /** Algo corto a la derecha (cuantos documentos). */
  meta?: string;
  /** Un tono para lo que pide atencion (lo nuevo de una lectura, un posible duplicado). */
  tone?: "new" | "duplicate";
  children?: TreeNode[];
};
export type TreeRow = {
  node: TreeNode;
  level: number;
  parentId: string | null;
  posinset: number;
  setsize: number;
  branch: boolean;
  open: boolean;
};
function flatten(
  nodes: TreeNode[],
  openSet: ReadonlySet<string>,
  level = 1,
  parentId: string | null = null,
  out: TreeRow[] = [],
): TreeRow[] {
  nodes.forEach((node, i) => {
    const children = node.children ?? [],
      branch = children.length > 0,
      open = branch && openSet.has(node.id);
    out.push({
      node,
      level,
      parentId,
      posinset: i + 1,
      setsize: nodes.length,
      branch,
      open,
    });
    if (open) flatten(children, openSet, level + 1, node.id, out);
  });
  return out;
}
export type UseTreeViewOptions = {
  nodes: TreeNode[];
  expanded?: string[];
  defaultExpanded?: string[];
  onExpandedChange?: (expanded: string[]) => void;
  selected?: string | null;
  defaultSelected?: string | null;
  onSelectedChange?: (selected: string) => void;
};
export function useTreeView({
  nodes,
  expanded,
  defaultExpanded = [],
  onExpandedChange,
  selected,
  defaultSelected = null,
  onSelectedChange,
}: UseTreeViewOptions) {
  const [internalOpen, setInternalOpen] = useState(defaultExpanded),
    openControlled = expanded !== undefined,
    openList = openControlled ? expanded : internalOpen,
    openSet = new Set(openList),
    [internalSel, setInternalSel] = useState<string | null>(defaultSelected),
    selControlled = selected !== undefined,
    selectedId = selControlled ? selected : internalSel,
    emitOpen = useRef(onExpandedChange),
    emitSel = useRef(onSelectedChange);
  emitOpen.current = onExpandedChange;
  emitSel.current = onSelectedChange;
  const rows = flatten(nodes, openSet),
    [focusId, setFocusId] = useState<string | null>(null),
    visible =
      focusId !== null && rows.some((r) => r.node.id === focusId)
        ? focusId
        : (rows.find((r) => r.node.id === selectedId)?.node.id ??
          rows[0]?.node.id ??
          null),
    refs = useRef(new Map<string, HTMLElement>());
  const register = useCallback((id: string, el: HTMLElement | null) => {
      if (el) refs.current.set(id, el);
      else refs.current.delete(id);
    }, []),
    focusRow = useCallback((id: string) => {
      setFocusId(id);
      refs.current.get(id)?.focus();
    }, []),
    setOpen = useCallback(
      (next: string[]) => {
        if (!openControlled) setInternalOpen(next);
        emitOpen.current?.(next);
      },
      [openControlled],
    ),
    toggle = useCallback(
      (id: string) => {
        const has = openList.includes(id);
        setOpen(has ? openList.filter((v) => v !== id) : [...openList, id]);
      },
      [openList, setOpen],
    ),
    select = useCallback(
      (id: string) => {
        if (!selControlled) setInternalSel(id);
        emitSel.current?.(id);
      },
      [selControlled],
    );
  const handleKey = useCallback(
    (event: KeyboardEvent, row: TreeRow) => {
      const at = rows.findIndex((r) => r.node.id === row.node.id),
        go = (index: number) => {
          const target = rows[index];
          if (target) focusRow(target.node.id);
        };
      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          go(at + 1);
          return;
        case "ArrowUp":
          event.preventDefault();
          go(at - 1);
          return;
        case "ArrowRight":
          event.preventDefault();
          if (row.branch && !row.open) toggle(row.node.id);
          else if (row.open) go(at + 1);
          return;
        case "ArrowLeft":
          event.preventDefault();
          if (row.open) toggle(row.node.id);
          else if (row.parentId) focusRow(row.parentId);
          return;
        case "Home":
          event.preventDefault();
          go(0);
          return;
        case "End":
          event.preventDefault();
          go(rows.length - 1);
          return;
        case "Enter":
        case " ":
          event.preventDefault();
          select(row.node.id);
          if (row.branch) toggle(row.node.id);
          return;
      }
      if (event.key.length === 1 && !event.metaKey && !event.ctrlKey) {
        const letter = event.key.toLowerCase();
        if (letter === " ") return;
        for (let step = 1; step <= rows.length; step++) {
          const candidate = rows[(at + step) % rows.length];
          if (candidate?.node.label.toLowerCase().startsWith(letter)) {
            event.preventDefault();
            focusRow(candidate.node.id);
            return;
          }
        }
      }
    },
    [rows, focusRow, toggle, select],
  );
  return {
    rows,
    openSet,
    selectedId,
    tabStop: visible,
    register,
    focusRow,
    setFocusId,
    toggle,
    select,
    handleKey,
  };
}
function Caret({ open }: { open: boolean }) {
  const reduced = useReducedMotion();
  return (
    <motion.span
      aria-hidden
      initial={false}
      animate={{ rotate: open ? 90 : 0 }}
      transition={reduced ? STILL : SMALL}
      className="tree-caret"
    >
      <svg viewBox="0 0 12 12" width="10" height="10" focusable="false">
        <path
          d="M4.5 2.5 8 6l-3.5 3.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </motion.span>
  );
}
export type TreeViewProps = UseTreeViewOptions & {
  label: string;
  className?: string;
};
export function TreeView({
  nodes,
  label,
  expanded,
  defaultExpanded,
  onExpandedChange,
  selected,
  defaultSelected,
  onSelectedChange,
  className = "",
}: TreeViewProps) {
  const { t } = useT();
  const tree = useTreeView({
      nodes,
      expanded,
      defaultExpanded,
      onExpandedChange,
      selected,
      defaultSelected,
      onSelectedChange,
    }),
    reduced = useReducedMotion(),
    hintId = useId();
  const renderNodes = (list: TreeNode[], level: number): ReactNode =>
    list.map((node, i) => {
      const row = tree.rows.find((r) => r.node.id === node.id);
      if (!row) return null;
      const isSelected = tree.selectedId === node.id;
      return (
        <li key={node.id} role="none">
          <div
            role="treeitem"
            ref={(el) => tree.register(node.id, el)}
            aria-level={level}
            aria-posinset={i + 1}
            aria-setsize={list.length}
            aria-expanded={row.branch ? row.open : undefined}
            aria-selected={isSelected}
            aria-describedby={hintId}
            tabIndex={tree.tabStop === node.id ? 0 : -1}
            onFocus={() => tree.setFocusId(node.id)}
            onKeyDown={(e) => tree.handleKey(e, row)}
            onClick={() => {
              tree.select(node.id);
              tree.focusRow(node.id);
              if (row.branch) tree.toggle(node.id);
            }}
            className={
              "tree-row " +
              (isSelected ? "tree-selected " : "") +
              (node.tone ? "tree-tone-" + node.tone : "")
            }
          >
            {isSelected && (
              <motion.span
                aria-hidden="true"
                className="tree-selection-background"
                layoutId={reduced ? undefined : hintId + "-selection"}
                transition={
                  reduced
                    ? STILL
                    : { type: "spring", stiffness: 420, damping: 38 }
                }
              />
            )}
            {row.branch ? (
              <Caret open={row.open} />
            ) : (
              <span className="tree-caret" />
            )}
            <span className="tree-label">{node.label}</span>
            {node.meta ? <span className="tree-meta">{node.meta}</span> : null}
          </div>
          {row.branch ? (
            <AnimatePresence initial={false}>
              {row.open ? (
                <motion.ul
                  key="group"
                  role="group"
                  initial={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={
                    reduced
                      ? { opacity: 0, transition: STILL }
                      : {
                          height: 0,
                          opacity: 0,
                          transition: { height: SHUT_H, opacity: SHUT_O },
                        }
                  }
                  transition={
                    reduced ? STILL : { height: OPEN_H, opacity: OPEN_O }
                  }
                  className="tree-group tree-branch"
                >
                  {renderNodes(node.children ?? [], level + 1)}
                </motion.ul>
              ) : null}
            </AnimatePresence>
          ) : null}
        </li>
      );
    });
  return (
    <div className="aurora-root">
      <div className={"tree-view " + className}>
        <ul role="tree" aria-label={label}>
          {renderNodes(nodes, 1)}
        </ul>
        <span id={hintId} className="sr-only">
          {t.aurora.tree.hint}
        </span>
      </div>
    </div>
  );
}
