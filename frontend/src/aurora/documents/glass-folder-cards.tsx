// glass-folder-cards.tsx del dueno (entrega del 28-10-2026): la carpeta de cristal del archivo,
// una por cliente o proveedor, con el abanico de sus documentos al abrirla y el marmol o las vetas
// del dorso calculados en un canvas por partes (y guardados por semilla). Estructura, nombres y
// valores, los suyos. Cambios (especificacion §4.2):
// - C: su hoja (GF_CSS) va en glass-folder-cards.css, no en un <style> dentro de cada carpeta;
// - D: sin el boton "+" que creaba "Documento N" ni onAdd/onFilesChange (la V1 no crea
//   documentos), sin imagenes ni enlaces hechos con un dato (image, href): un documento se abre
//   con onFileSelect, por su id; "N documentos" puede venir dado (total), porque una carpeta
//   cerrada aun no ha leido los suyos; las marcas "Nueva" y "Repetida" salen de la ultima lectura;
// - I: los textos (nombres accesibles, "N documentos"), de los diccionarios;
// - T: sin tono dado, el del tema (la carpeta clara en el tema claro).
import * as React from "react";
import { fmt, useT } from "@/i18n";
import { useTheme } from "@/lib/theme";
import "./glass-folder-cards.css";

export type ArtPreset = "aurora" | "ember" | "dusk" | "glacier" | "verdant";
export type ArtRecipe = {
  style: "marble" | "streak";
  colors: string[];
  scale?: number;
  warp?: number;
  angle?: number;
  gloss?: number;
  veins?: number;
};
export type FolderArt = ArtPreset | ArtRecipe | "none";
export type FolderFile = {
  /** El id del documento (para abrirlo); el nombre es solo lo que se ve. */
  id: string;
  name: string;
  meta?: string;
  /** El nombre accesible de la hoja (lo que abre: su vista previa). */
  label?: string;
  /** Lo que dijo de ella la ultima lectura: nueva o repetida (y su nota). */
  analysisStatus?: "new" | "duplicate";
  analysisNote?: string;
  art?: ArtPreset | ArtRecipe;
};
export type FolderMenuItem = {
  label: string;
  onSelect?: () => void;
  danger?: boolean;
};
export type GlassFolderProps = {
  frontAccessory?: React.ReactNode;
  label: string;
  meta?: string;
  tone?: "light" | "dark";
  art?: FolderArt;
  seed?: number;
  files?: FolderFile[];
  /** Cuantos documentos tiene la carpeta, si no son los de `files` (una carpeta cerrada aun
   *  no ha leido los suyos: se leen al abrirla o al pasar por encima). */
  total?: number;
  /** El boton "..." con el menu de la carpeta (sin el, la carpeta solo se abre). */
  moreButton?: boolean;
  menu?: FolderMenuItem[];
  labelPlacement?: "bottom-left" | "top-left" | "top-right";
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  onFileSelect?: (file: FolderFile, index: number) => void;
  width?: number;
  appear?: boolean;
  appearDelay?: number;
  className?: string;
  style?: React.CSSProperties;
};
export const ART_PRESETS: Record<ArtPreset, ArtRecipe> = {
  aurora: {
    style: "streak",
    colors: [
      "#f4efe9",
      "#e9c2b8",
      "#c2433f",
      "#2a1e2a",
      "#22395e",
      "#6f97c2",
      "#e5edf4",
    ],
    scale: 0.7,
    warp: 1.4,
    angle: -0.62,
    gloss: 0.18,
    veins: 0,
  },
  ember: {
    style: "marble",
    colors: [
      "#07090c",
      "#16252c",
      "#3d5f68",
      "#1a1416",
      "#a3201a",
      "#ef4a2b",
      "#ff8a5c",
    ],
    scale: 0.62,
    warp: 3.2,
    angle: -0.5,
    gloss: 0.55,
    veins: 0.6,
  },
  dusk: {
    style: "marble",
    colors: [
      "#120c18",
      "#3e2850",
      "#8f6c9c",
      "#2b1a24",
      "#b3502f",
      "#eab08a",
      "#fbe7d2",
    ],
    scale: 0.75,
    warp: 3.6,
    angle: 0.8,
    gloss: 0.5,
    veins: 0.5,
  },
  glacier: {
    style: "streak",
    colors: ["#f7f8fa", "#d9e2ea", "#9fb4c7", "#e8edf2", "#bccbd8", "#ffffff"],
    scale: 0.7,
    warp: 1.6,
    angle: 0.35,
    gloss: 0.25,
    veins: 0,
  },
  verdant: {
    style: "marble",
    colors: [
      "#070b08",
      "#173024",
      "#4f7a5a",
      "#141812",
      "#a7843a",
      "#e9cf87",
      "#fbf3d6",
    ],
    scale: 0.7,
    warp: 3.4,
    angle: 2.1,
    gloss: 0.5,
    veins: 0.5,
  },
};
export function hexToRgb(hex: string): [number, number, number] {
  let h = hex.trim().replace(/^#/, "");
  if (h.length === 3) h = h.replace(/./g, (c) => c + c);
  const n = /^[0-9a-f]{6}$/i.test(h) ? parseInt(h, 16) : 0x808080;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function hashString(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++)
    h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}
export function fanSlot(i: number, n: number) {
  return n <= 1 ? 0 : (i / (n - 1)) * 2 - 1;
}
function makeFbm(seed: number) {
  const r = rng(seed),
    perm = new Uint8Array(512),
    grad = new Float32Array(512),
    p = Array.from({ length: 256 }, (_, i) => i);
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [p[i], p[j]] = [p[j]!, p[i]!];
  }
  for (let i = 0; i < 512; i++) perm[i] = p[i & 255]!;
  for (let i = 0; i < 256; i++) {
    const a = r() * Math.PI * 2;
    grad[i * 2] = Math.cos(a);
    grad[i * 2 + 1] = Math.sin(a);
  }
  const noise = (x: number, y: number) => {
    const xi = Math.floor(x),
      yi = Math.floor(y),
      xf = x - xi,
      yf = y - yi,
      X = xi & 255,
      Y = yi & 255,
      h00 = perm[X + perm[Y]!]! * 2,
      h10 = perm[X + 1 + perm[Y]!]! * 2,
      h01 = perm[X + perm[Y + 1]!]! * 2,
      h11 = perm[X + 1 + perm[Y + 1]!]! * 2,
      d00 = grad[h00]! * xf + grad[h00 + 1]! * yf,
      d10 = grad[h10]! * (xf - 1) + grad[h10 + 1]! * yf,
      d01 = grad[h01]! * xf + grad[h01 + 1]! * (yf - 1),
      d11 = grad[h11]! * (xf - 1) + grad[h11 + 1]! * (yf - 1),
      u = xf * xf * xf * (xf * (xf * 6 - 15) + 10),
      v = yf * yf * yf * (yf * (yf * 6 - 15) + 10);
    return (
      d00 + u * (d10 - d00) + v * (d01 - d00 + u * (d11 - d01 - d10 + d00))
    );
  };
  return (x: number, y: number, octaves: number) => {
    let sum = 0,
      amp = 0.5;
    for (let i = 0; i < octaves; i++) {
      sum += amp * noise(x, y);
      const nx = 1.6 * x + 1.2 * y + 7.1;
      y = -1.2 * x + 1.6 * y + 3.3;
      x = nx;
      amp *= 0.5;
    }
    return sum;
  };
}
export type ArtJob = {
  width: number;
  height: number;
  pixels: Uint8ClampedArray<ArrayBuffer>;
  step: (rows: number) => boolean;
};
export function createArtJob(
  width: number,
  height: number,
  recipe: ArtRecipe,
  seed: number,
): ArtJob {
  const w = Math.max(1, Math.round(width)),
    h = Math.max(1, Math.round(height)),
    colors = (
      recipe.colors.length >= 2 ? recipe.colors : ["#111111", "#eeeeee"]
    ).map(hexToRgb),
    fbm = makeFbm(seed * 977 + 13),
    r = rng(seed + 1),
    ox = r() * 50,
    oy = r() * 50,
    angle = (recipe.angle ?? 0) + (r() - 0.5) * 0.5,
    ca = Math.cos(angle),
    sa = Math.sin(angle),
    m = Math.min(w, h),
    gw = Math.ceil(w / 2) + 3,
    gh = Math.ceil(h / 2) + 3,
    G = new Float32Array(gw * gh),
    GQ = new Float32Array(gw * gh),
    F = new Float32Array(w * h),
    Q = new Float32Array(w * h),
    pixels = new Uint8ClampedArray(w * h * 4);
  let row = 0;
  const field = (gy: number) => {
    for (let gx = 0; gx < gw; gx++) {
      const u = ((gx - 1) * 2 - w / 2) / m,
        v = ((gy - 1) * 2 - h / 2) / m;
      let px = (u * ca - v * sa) * (recipe.scale ?? 0.7),
        py = (u * sa + v * ca) * (recipe.scale ?? 0.7);
      if (recipe.style === "streak") {
        px *= 0.14;
        py *= 2.2;
      }
      px += ox;
      py += oy;
      const warp = recipe.warp ?? 3,
        qx = fbm(px, py, 3),
        qy = fbm(px + 5.2, py + 1.3, 3),
        rx = fbm(px + warp * qx + 1.7, py + warp * qy + 9.2, 3),
        ry = fbm(px + warp * qx + 8.3, py + warp * qy + 2.8, 3);
      G[gy * gw + gx] = fbm(px + warp * rx, py + warp * ry, 4);
      GQ[gy * gw + gx] = Math.hypot(qx, qy);
    }
  };
  const finish = () => {
    const cr = (a: number, b: number, c: number, d: number) =>
        (-a + 9 * b + 9 * c - d) / 16,
      T = new Float32Array(w * gh);
    for (let gy = 0; gy < gh; gy++)
      for (let x = 0; x < w; x++) {
        const c = (x >> 1) + 1,
          j = gy * gw;
        T[gy * w + x] =
          x & 1
            ? cr(G[j + c - 1]!, G[j + c]!, G[j + c + 1]!, G[j + c + 2]!)
            : G[j + c]!;
      }
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const c = (y >> 1) + 1;
        F[y * w + x] =
          y & 1
            ? cr(
                T[(c - 1) * w + x]!,
                T[c * w + x]!,
                T[(c + 1) * w + x]!,
                T[(c + 2) * w + x]!,
              )
            : T[c * w + x]!;
        Q[y * w + x] = GQ[c * gw + (x >> 1) + 1]!;
      }
    const sample: number[] = [];
    for (let i = 0; i < F.length; i += Math.max(1, Math.floor(F.length / 4096)))
      sample.push(F[i]!);
    sample.sort((a, b) => a - b);
    const lo = sample[Math.floor(sample.length * 0.02)] ?? 0,
      hi = sample[Math.floor(sample.length * 0.98)] ?? 1,
      k = 1 / (hi - lo || 1),
      slope = k * m * 0.012;
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const i = y * w + x,
          t = Math.min(1, Math.max(0, (F[i]! - lo) * k)),
          idx = Math.min(
            colors.length - 2,
            Math.floor(t * (colors.length - 1)),
          );
        let f = t * (colors.length - 1) - idx;
        f = f * f * (3 - 2 * f);
        const gx = (F[x < w - 1 ? i + 1 : i]! - F[x > 0 ? i - 1 : i]!) * slope,
          gy = (F[y < h - 1 ? i + w : i]! - F[y > 0 ? i - w : i]!) * slope,
          nd =
            (gx * 0.55 + gy * 0.65 + 0.52) / Math.sqrt(gx * gx + gy * gy + 1),
          spec = Math.pow(Math.max(0, nd), 24) * (recipe.gloss ?? 0.4) * 255,
          vein =
            (recipe.veins ?? 0) *
            Math.max(0, 1 - Math.abs(Q[i]! - 0.42) * 14) *
            0.6,
          lit =
            (0.82 + 0.28 * nd) *
            (1 + 0.035 * Math.sin(t * 150 + Q[i]! * 24)) *
            (1 - vein);
        for (let c = 0; c < 3; c++)
          pixels[i * 4 + c] =
            (colors[idx]![c]! + (colors[idx + 1]![c]! - colors[idx]![c]!) * f) * lit +
            spec;
        pixels[i * 4 + 3] = 255;
      }
  };
  return {
    width: w,
    height: h,
    pixels,
    step(rows) {
      if (row >= gh) return true;
      const end = Math.min(gh, row + Math.max(1, rows));
      while (row < end) field(row++);
      if (row < gh) return false;
      finish();
      return true;
    },
  };
}
const cache = new Map<string, Promise<HTMLCanvasElement>>();
const queue: {
  job: ArtJob;
  done: (c: HTMLCanvasElement) => void;
  priority: number;
}[] = [];
let pumping = false;
function pump() {
  if (pumping) return;
  pumping = true;
  const tick = () => {
    const until = performance.now() + 7;
    while (queue.length && performance.now() < until) {
      const head = queue[0];
      if (head?.job.step(4)) {
        queue.shift();
        const c = document.createElement("canvas");
        c.width = head.job.width;
        c.height = head.job.height;
        c
          .getContext("2d")
          ?.putImageData(
            new ImageData(head.job.pixels, c.width, c.height),
            0,
            0,
          );
        head.done(c);
      }
    }
    if (queue.length) requestAnimationFrame(tick);
    else pumping = false;
  };
  requestAnimationFrame(tick);
}
function ArtCanvas({
  art,
  seed,
  w,
  h,
  density,
  priority,
  className,
}: {
  art: ArtPreset | ArtRecipe;
  seed: number;
  w: number;
  h: number;
  density: number;
  priority: number;
  className?: string;
}) {
  const ref = React.useRef<HTMLCanvasElement>(null),
    [ready, setReady] = React.useState(false),
    recipe = typeof art === "string" ? ART_PRESETS[art] : art,
    key = JSON.stringify([
      recipe,
      seed,
      Math.round(w * density),
      Math.round(h * density),
    ]);
  React.useEffect(() => {
    let live = true;
    setReady(false);
    let result = cache.get(key);
    if (!result) {
      result = new Promise<HTMLCanvasElement>((done) => {
        let at = queue.length;
        while (at > 1 && (queue[at - 1]?.priority ?? 0) > priority) at--;
        queue.splice(at, 0, {
          job: createArtJob(
            Math.round(w * density),
            Math.round(h * density),
            recipe,
            seed,
          ),
          priority,
          done,
        });
        pump();
      });
      cache.set(key, result);
    }
    result.then((src) => {
      const c = ref.current;
      if (!live || !c) return;
      c.width = src.width;
      c.height = src.height;
      c.getContext("2d")?.drawImage(src, 0, 0);
      setReady(true);
    });
    return () => {
      live = false;
    };
  }, [key]);
  return (
    <canvas
      ref={ref}
      aria-hidden
      className={className}
      data-ready={ready || undefined}
      style={{ width: w, height: h, maxWidth: "none" }}
    />
  );
}
const BACK_PATH =
  "M0 56A22 22 0 0 1 22 34L146 34C170 34 172 0 198 0L318 0A22 22 0 0 1 340 22L340 250A22 22 0 0 1 318 272L22 272A22 22 0 0 1 0 250Z";
const FRONT_PATH =
  "M0 22A22 22 0 0 1 22 0L118 0C144 0 146 32 172 32L318 32A22 22 0 0 1 340 54L340 176A22 22 0 0 1 318 198L22 198A22 22 0 0 1 0 176Z";
export function GlassFolder({
  frontAccessory,
  label,
  meta,
  tone: toneProp,
  art = "aurora",
  seed = 3,
  files = [],
  total,
  moreButton = false,
  menu = [],
  labelPlacement = "bottom-left",
  open: openProp,
  defaultOpen = false,
  onOpenChange,
  onFileSelect,
  width = 340,
  appear = true,
  appearDelay = 0,
  className,
  style,
}: GlassFolderProps) {
  const { t } = useT();
  const { resolved } = useTheme();
  // Sin tono dado, el del tema: la carpeta clara en el tema claro, la oscura en el oscuro.
  const tone = toneProp ?? resolved;
  const texts = t.aurora.folder;
  const uid = React.useId().replace(/:/g, ""),
    rootRef = React.useRef<HTMLDivElement>(null),
    filesRef = React.useRef<HTMLDivElement>(null),
    hitRef = React.useRef<HTMLButtonElement>(null),
    keyRef = React.useRef<HTMLButtonElement>(null),
    menuRef = React.useRef<HTMLDivElement>(null),
    [openState, setOpenState] = React.useState(defaultOpen),
    open = openProp ?? openState,
    [menuOpen, setMenuOpen] = React.useState(false),
    [entered, setEntered] = React.useState(!appear),
    k = width / 340,
    density = Math.min(1.5, Math.max(1, window.devicePixelRatio || 1)) * k;
  const setOpen = React.useCallback(
    (next: boolean) => {
      if (openProp === undefined) setOpenState(next);
      onOpenChange?.(next);
    },
    [openProp, onOpenChange],
  );
  React.useEffect(() => {
    if (!appear) return;
    const el = rootRef.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setEntered(true);
      return;
    }
    let timer = 0;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        timer = window.setTimeout(() => setEntered(true), appearDelay);
      },
      { threshold: 0.25 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      clearTimeout(timer);
    };
  }, [appear, appearDelay]);
  // La inclinacion 3D al pasar el raton (no con el dedo): solo dos variables CSS por cuadro.
  React.useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    let raf = 0,
      px = 0,
      py = 0;
    const write = () => {
        raf = 0;
        el.style.setProperty("--gf-px", px.toFixed(3));
        el.style.setProperty("--gf-py", py.toFixed(3));
      },
      move = (e: PointerEvent) => {
        if (e.pointerType === "touch") return;
        const r = el.getBoundingClientRect();
        px = ((e.clientX - r.left) / r.width) * 2 - 1;
        py = ((e.clientY - r.top) / r.height) * 2 - 1;
        if (!raf) raf = requestAnimationFrame(write);
      },
      leave = () => {
        px = py = 0;
        if (!raf) raf = requestAnimationFrame(write);
      };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
      cancelAnimationFrame(raf);
    };
  }, []);
  React.useEffect(() => {
    filesRef.current?.toggleAttribute("inert", !open);
  }, [open]);
  // Escape cierra el menu (y devuelve el foco a su boton) o la carpeta; un clic fuera, igual.
  React.useEffect(() => {
    if (!open && !menuOpen) return;
    const key = (e: KeyboardEvent) => {
        if (e.key !== "Escape") return;
        if (openProp !== undefined && !rootRef.current?.contains(e.target as Node)) return;
        if (menuOpen) {
          setMenuOpen(false);
          keyRef.current?.focus();
        } else {
          setOpen(false);
          hitRef.current?.focus();
        }
      },
      down = (e: PointerEvent) => {
        const target = e.target as Node;
        if (menuOpen && !menuRef.current?.contains(target) && !keyRef.current?.contains(target)) setMenuOpen(false);
        if (open && openProp === undefined && !menuOpen && !rootRef.current?.contains(target)) setOpen(false);
      };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", down);
    return () => {
      document.removeEventListener("keydown", key);
      document.removeEventListener("pointerdown", down);
    };
  }, [open, menuOpen, setOpen, openProp]);
  React.useEffect(() => {
    if (menuOpen) menuRef.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
  }, [menuOpen]);
  const menuItems: FolderMenuItem[] = [
    { label: open ? texts.close : texts.open, onSelect: () => setOpen(!open) },
    ...menu,
  ];
  const onMenuKey = (e: React.KeyboardEvent) => {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []),
      at = items.indexOf(document.activeElement as HTMLElement);
    let next: number | undefined;
    if (e.key === "ArrowDown") next = at + 1;
    if (e.key === "ArrowUp") next = at - 1;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = items.length - 1;
    if (next !== undefined) {
      e.preventDefault();
      items[(next + items.length) % items.length]?.focus();
    }
    if (e.key === "Tab") setMenuOpen(false);
  };
  // En el abanico caben cuatro hojas: las ultimas.
  const start = Math.max(0, files.length - 4),
    visible = files.slice(start),
    n = total ?? files.length,
    count = n === 1 ? texts.documentsOne : fmt(texts.documents, { n }),
    metaLine = meta ?? count;
  return (
      <div
        ref={rootRef}
        className={"gf-root" + (className ? " " + className : "")}
        data-tone={tone}
        data-open={open || undefined}
        data-entered={entered || undefined}
        data-place={labelPlacement}
        style={{ width, height: 326 * k, ...style }}
      >
        <div className="gf-stage" style={{ transform: `translateY(${54 * k}px) scale(${k})` }}>
          <div className="gf-tilt">
            <div className="gf-shadow" aria-hidden />
            <div className="gf-back" style={{ clipPath: `path('${BACK_PATH}')` }} aria-hidden>
              {art !== "none" ? (
                <ArtCanvas className="gf-art" art={art} seed={seed} w={364} h={296} density={density} priority={0} />
              ) : null}
              <div className="gf-back-sheen" />
            </div>
            <svg className="gf-rim gf-back-rim" viewBox="0 0 340 272" aria-hidden>
              <path d={BACK_PATH} />
            </svg>
            <div className="gf-front" style={{ clipPath: `path('${FRONT_PATH}')` }}>
              <div className="gf-tint" />
              <div className="gf-spec" />
              <svg className="gf-rim gf-front-rim" viewBox="0 0 340 198" aria-hidden>
                <defs>
                  <linearGradient id={"gf-rim-" + uid} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#fff" stopOpacity=".95" />
                    <stop offset=".35" stopColor="#fff" stopOpacity=".35" />
                    <stop offset="1" stopColor="#fff" stopOpacity=".12" />
                  </linearGradient>
                </defs>
                <path d={FRONT_PATH} stroke={`url(#gf-rim-${uid})`} />
              </svg>
              <button
                ref={hitRef}
                type="button"
                className="gf-hit"
                aria-describedby={frontAccessory ? "gf-status-" + uid : undefined}
                aria-expanded={open}
                aria-label={fmt(open ? texts.closeNamed : texts.openNamed, { name: label, count })}
                onClick={() => {
                  setMenuOpen(false);
                  setOpen(!open);
                }}
              />
              <div id={"gf-status-" + uid} className="gf-statuses">
                {frontAccessory}
              </div>
              <div className="gf-label">
                <span className="gf-title" title={label} data-proper-name="">{label}</span>
                <span className="gf-meta" key={metaLine}>
                  {metaLine}
                </span>
              </div>
            </div>
            <div ref={filesRef} className="gf-files" role="list" aria-label={fmt(texts.filesOf, { name: label })}>
              {visible.map((file, v) => {
                const slot = fanSlot(v, visible.length),
                  jitter = rng(hashString(file.id + file.name));
                return (
                  <div role="listitem" key={file.id} className="gf-sheet-slot">
                    <button
                      type="button"
                      className={"gf-sheet" + (file.analysisStatus ? " gf-sheet--" + file.analysisStatus : "") + (file.art ? " gf-sheet--art" : "")}
                      style={
                        {
                          "--gf-slot": slot,
                          "--gf-depth": visible.length - 1 - v,
                          "--gf-jx": (jitter() - 0.5) * 10 + "px",
                          "--gf-jr": (jitter() - 0.5) * 3.2 + "deg",
                          zIndex: v + 1,
                        } as React.CSSProperties
                      }
                      aria-label={file.label}
                      onClick={() => onFileSelect?.(file, start + v)}
                    >
                      {file.art ? (
                        <ArtCanvas
                          className="gf-sheet-art"
                          art={file.art}
                          seed={hashString(file.name) % 997}
                          w={272}
                          h={184}
                          density={Math.min(density, 1.25)}
                          priority={1}
                        />
                      ) : (
                        <span className="gf-lines" aria-hidden>
                          {[86, 92, 64, 88, 42].map((w, i) => (
                            <i key={i} style={{ width: w + "%" }} />
                          ))}
                        </span>
                      )}
                      <span className="gf-sheet-head">
                        <span className="gf-sheet-name">{file.name}</span>
                        {file.meta && (
                          <span className="gf-sheet-meta">
                            {file.analysisStatus === "new" ? texts.freshMark : file.analysisStatus === "duplicate" ? texts.repeatedMark : ""}
                            <span data-proper-name="">{file.meta}</span>
                          </span>
                        )}
                      </span>
                    </button>
                  </div>
                );
              })}
            </div>
            {moreButton && (
              <>
                <button
                  ref={keyRef}
                  type="button"
                  className="gf-key gf-key--more"
                  aria-label={fmt(texts.optionsOf, { name: label })}
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((m) => !m)}
                >
                  <svg className="gf-glyph gf-glyph--more" viewBox="0 0 30 12" aria-hidden>
                    {[1, 11, 21].map((x) => (
                      <rect key={x} x={x} y="1.5" width="8" height="9" rx="3.4" />
                    ))}
                  </svg>
                </button>
                <div
                  ref={menuRef}
                  role="menu"
                  aria-label={fmt(texts.optionsOf, { name: label })}
                  className="gf-menu"
                  data-open={menuOpen || undefined}
                  onKeyDown={onMenuKey}
                >
                  {menuItems.map((item, i) => (
                    <button
                      key={i}
                      role="menuitem"
                      type="button"
                      tabIndex={menuOpen ? -1 : undefined}
                      disabled={!menuOpen}
                      className={"gf-menu-item" + (item.danger ? " gf-menu-item--danger" : "")}
                      onClick={() => {
                        setMenuOpen(false);
                        keyRef.current?.focus();
                        item.onSelect?.();
                      }}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
  );
}
