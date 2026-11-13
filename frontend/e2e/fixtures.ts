// Lo que vigila cada prueba, sin que la prueba tenga que acordarse:
// - cada peticion de la pagina va a 127.0.0.1 (una a otro sitio se corta y la prueba falla);
// - ninguna violacion de la politica de contenido (CSP);
// - ningun error en la consola ni ninguna excepcion sin capturar.
// Y las ayudas: entrar con un token de prueba, elegir el tema, el analisis de accesibilidad
// (axe), los restos de otro idioma y las capturas, que van a CAPTURAS_DIR (por defecto
// test-results/capturas), en una carpeta por tema: dark/ o light/ (paso 16).
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type APIRequestContext, type Locator, type Page } from '@playwright/test';
import type { InvoiceRow } from '../src/lib/api';
import { DOMAIN_FALLBACK, type Lang } from '../src/i18n/langs';
import { glossaryMisses } from '../src/i18n/glossary';
import { leftoversIn } from '../src/i18n/leftovers';
import { decodePng } from './png';

interface Watch {
  external: string[];
  consoleErrors: string[];
  cspViolations: string[];
  /** Los codigos de error HTTP que el navegador anota en la consola (fetch que falla). */
  httpErrors: number[];
  /** Los que esta prueba provoca a proposito (un token que no vale: 401). */
  expectHttpErrors: (...statuses: number[]) => void;
}

export const test = base.extend<{ watch: Watch; baseUrl: string }>({
  baseUrl: async ({}, use) => {
    const url = process.env.BMS_E2E_URL;
    if (!url) throw new Error('falta BMS_E2E_URL (lo pone e2e/global-setup.ts)');
    await use(url);
  },
  watch: [
    async ({ page }, use) => {
      const allowed = new Set<number>();
      const watch: Watch = {
        external: [],
        consoleErrors: [],
        cspViolations: [],
        httpErrors: [],
        expectHttpErrors: (...statuses) => statuses.forEach((s) => allowed.add(s)),
      };
      await page.route('**/*', (route) => {
        const url = new URL(route.request().url());
        if (url.protocol !== 'blob:' && url.protocol !== 'data:' && url.hostname !== '127.0.0.1') {
          watch.external.push(url.href);
          return route.abort('blockedbyclient');
        }
        return route.continue();
      });
      page.on('console', (message) => {
        if (message.type() !== 'error') return;
        const http = /^Failed to load resource: the server responded with a status of (\d{3})/.exec(message.text());
        if (http) watch.httpErrors.push(Number(http[1]));
        else watch.consoleErrors.push(message.text());
      });
      page.on('pageerror', (error) => watch.consoleErrors.push(`pageerror: ${error.message}`));
      await page.exposeFunction('__bmsCsp', (text: string) => watch.cspViolations.push(text));
      await page.addInitScript(() => {
        document.addEventListener('securitypolicyviolation', (event) => {
          (window as unknown as { __bmsCsp: (t: string) => void }).__bmsCsp(
            `${event.violatedDirective} ${event.blockedURI} ${event.sourceFile}:${event.lineNumber}`
          );
        });
      });
      await use(watch);
      expect(watch.external, 'peticiones fuera de 127.0.0.1').toEqual([]);
      expect(watch.cspViolations, 'violaciones de la CSP').toEqual([]);
      expect(watch.consoleErrors, 'errores en la consola').toEqual([]);
      expect(watch.httpErrors.filter((s) => !allowed.has(s)), 'respuestas de error no esperadas').toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

export type Who = 'ana' | 'bram' | 'cas';

export function token(who: Who = 'ana'): string {
  const value = { ana: process.env.BMS_E2E_TOKEN_ANA, bram: process.env.BMS_E2E_TOKEN_BRAM, cas: process.env.BMS_E2E_TOKEN_CAS }[who];
  if (!value) throw new Error('faltan los tokens de prueba (e2e/global-setup.ts)');
  return value;
}

/** Los numeros de las facturas que las pruebas abren por su papel en la base de prueba (los da
 *  scripts/crear_demo_e2e.py: llevan el mes y el ano del dia en que se hace la base). */
export interface DemoNumbers {
  /** La vieja del gemeentehuis, vencida hace mas de sesenta dias (urgente). */
  municipalOld: string;
  /** K. Testpersoon: la de hace dos meses (vencida) y la del mes pasado (un dato dudoso). */
  testpersoonOld: string;
  testpersoonRecent: string;
  /** Noord: la del mes pasado y su abono propuesto (R5). */
  noordCredited: string;
  noordCredit: string;
  /** Proefwacht: la que trae otro IBAN (F2, F3). */
  proefwachtNewIban: string;
  /** La de otra moneda (X1) y la de Oost, con el texto que pide cambiar el IBAN. */
  otherCurrency: string;
  oost: string;
  /** J. Voorbeeld: la primera, la repetida (B2) y las de antes, de la mas reciente a la mas vieja. */
  voorbeeldFirst: string;
  voorbeeldTwin: string;
  voorbeeldEarlier: string[];
  /** El ultimo trimestre terminado del BTW, listo para revisar y sin presentar: "2026-T3". */
  vatQuarter: string;
}

let numbers: DemoNumbers | null = null;

/** Los numeros por papel. Se leen al usarlos (no al cargar el fichero: la lista de pruebas se
 *  hace antes de e2e/global-setup.ts). */
export const N: DemoNumbers = new Proxy({} as DemoNumbers, {
  get(_target, key: string) {
    if (!numbers) {
      const raw = process.env.BMS_E2E_NUMEROS;
      if (!raw) throw new Error('faltan los numeros de la base de prueba (e2e/global-setup.ts)');
      numbers = JSON.parse(raw) as DemoNumbers;
    }
    const value = numbers[key as keyof DemoNumbers];
    if (value === undefined) throw new Error(`la base de prueba no da el numero «${key}»`);
    return value;
  },
});

/** Las facturas de J. Voorbeeld que se pueden marcar como revisadas sin mas: sin revisar, sin
 *  nada abierto (ningun hallazgo, dato dudoso ni excepcion), de la mas reciente a la mas vieja.
 *  Cuales son depende del dia de la base y de lo que ya hicieron otras pruebas. */
export async function cleanToReview(request: APIRequestContext, baseUrl: string): Promise<string[]> {
  const response = await request.get(`${baseUrl}/api/v2/facturas`, { headers: { 'X-BMS-Token': token('ana') } });
  expect(response.status()).toBe(200);
  const rows = ((await response.json()) as { facturas: InvoiceRow[] }).facturas;
  const clean = rows
    .filter((f) => f.contraparte === 'J. Voorbeeld Beveiliging (zzp)' && f.numero && f.nivel === 'normal' && f.estado_revision !== 'revisada')
    .filter((f) => !f.sin_resolver && !f.dudosos && !f.pendientes && !f.sin_datos && !f.excepcion)
    .sort((a, b) => (b.fecha_factura ?? '').localeCompare(a.fecha_factura ?? ''));
  expect(clean.length, 'la base de prueba tiene facturas limpias por revisar').toBeGreaterThan(0);
  return clean.map((f) => f.numero!);
}

/** Entra con el token de una persona de prueba y espera al inicio (paso 17: el saludo de Aurora
 *  con su nombre, en el mismo sitio donde pedia el codigo). */
export async function login(page: Page, who: Who = 'ana'): Promise<void> {
  await page.locator('#token').fill(token(who));
  await page.locator('#login-submit').click();
  await expect(page.getByRole('heading', { level: 1, name: /^(Welkom|Welcome|Bienvenido), / })).toBeVisible();
  await expect(page.locator('#token')).toHaveCount(0);
}

/**
 * Espera a que la pantalla este quieta: ninguna animacion con fin en marcha (las que laten
 * sin fin, como el punto de una pastilla, no cuentan), el contenido de la pestana (que entra
 * con un fundido) entero y a opacidad 1, y ninguna opacidad a medias durante tres cuadros
 * seguidos. Sin esperas fijas: con la maquina cargada, axe media el contraste en mitad del
 * fundido (opacidad < 1 cuenta como visible para Playwright) y fallaba sin motivo.
 */
export async function settled(page: Page): Promise<void> {
  await page.waitForFunction(
    () =>
      new Promise<boolean>((resolve) => {
        let calm = 0;
        let last = '';
        const still = (): string | null => {
          const running = document.getAnimations().filter((a) => {
            if (a.playState !== 'running') return false;
            const end = a.effect?.getComputedTiming().endTime;
            return typeof end === 'number' && Number.isFinite(end);
          });
          if (running.length > 0) return null;
          // El cambio de pantalla de Aurora (aurora/root.tsx): la que sale se funde encima y el
          // orbe vuela; quieta es una sola pantalla, entera, y sin vuelo.
          const screens = Array.from(document.querySelectorAll<HTMLElement>('[data-aurora-root] > .app-screen'));
          if (screens.length > 1 || screens.some((el) => getComputedStyle(el).opacity !== '1')) return null;
          if (document.querySelector('.aurora-route-flight')) return null;
          const fading = Array.from(document.querySelectorAll<HTMLElement>('[style*="opacity"]'))
            .map((el) => el.style.opacity)
            .filter((o) => o !== '' && Number(o) > 0 && Number(o) < 1);
          if (fading.length > 0) return null;
          return Array.from(document.querySelectorAll<HTMLElement>('[style*="opacity"]'))
            .map((el) => el.style.opacity)
            .join(',');
        };
        const tick = (frames: number) => {
          const now = still();
          if (now !== null && now === last) calm += 1;
          else calm = 0;
          last = now ?? '';
          if (calm >= 3) resolve(true);
          else if (frames > 600) resolve(false);
          else requestAnimationFrame(() => tick(frames + 1));
        };
        requestAnimationFrame(() => tick(0));
      }),
    undefined,
    { timeout: 15_000 }
  );
}

/** Los grises de Aurora que no llegan a 4,5:1 en el tema oscuro (especificacion §6.6 y §7,
 *  punto 9): se dejan exactos y se apuntan aqui, cada uno con su sitio y su par de colores. */
interface ContrastException {
  /** Expresion regular sobre el selector que da axe. */
  selector: string;
  fg: string;
  bg: string;
}
const AURORA_CONTRAST: ContrastException[] = (
  JSON.parse(readFileSync(new URL('./aurora/contraste.json', import.meta.url), 'utf8')) as { casos: ContrastException[] }
).casos;

/** Ningun problema de accesibilidad serio o critico (WCAG 2.1 A y AA), ninguna falta de
 *  contraste (de ningun grado) salvo los grises de Aurora apuntados en e2e/aurora/contraste.json
 *  (solo en oscuro), y cada pastilla de estado medida a 4,5:1 o mas. Se mide con la pantalla
 *  quieta (settled). */
export async function expectAccessible(page: Page, what: string): Promise<void> {
  await settled(page);
  // La marca de agua del papel de la hoja («MUESTRA», aria-hidden) es decoracion: WCAG 1.4.3 no
  // pide contraste al texto que solo decora.
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .exclude('.ws-watermark')
    .analyze();
  const dark = (await shownTheme(page)) === 'dark';
  const excepted = (n: (typeof results.violations)[number]['nodes'][number]) => {
    if (!dark) return false;
    const data = n.any.find((c) => c.id === 'color-contrast')?.data as { fgColor?: string; bgColor?: string } | undefined;
    const target = n.target.join(' ');
    return AURORA_CONTRAST.some((c) => c.fg === data?.fgColor && c.bg === data?.bgColor && new RegExp(c.selector).test(target));
  };
  const contrastNodes = results.violations.filter((v) => v.id === 'color-contrast').flatMap((v) => v.nodes);
  const unexcused = contrastNodes.filter((n) => !excepted(n));
  if (process.env.BMS_E2E_CONTRASTE) {
    // Para apuntar casos nuevos: los deja en un fichero y no falla por ellos.
    for (const n of unexcused) {
      const data = n.any.find((c) => c.id === 'color-contrast')?.data as { fgColor?: string; bgColor?: string } | undefined;
      appendFileSync(process.env.BMS_E2E_CONTRASTE, JSON.stringify({ what, target: n.target.join(' '), fg: data?.fgColor, bg: data?.bgColor, dark }) + '\n');
    }
  }
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .filter((v) => v.id !== 'color-contrast')
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious, `accesibilidad: ${what}`).toEqual([]);
  const contrast = process.env.BMS_E2E_CONTRASTE ? [] : unexcused.map((n) => `${n.target.join(' ')}: ${n.failureSummary ?? ''}`);
  expect(contrast, `contraste (axe): ${what}`).toEqual([]);
  await expectStatusContrast(page, what);
}

/**
 * El contraste del texto de cada pastilla de estado (components/ui/status.tsx), medido en
 * el navegador: su color contra el fondo que se ve debajo, con los tintes semitransparentes
 * de la pastilla y de lo que la contiene compuestos sobre un canvas (como lo pinta
 * Chromium). axe deja estos casos como "incomplete" cuando no sabe componer el fondo; aqui
 * no se deja ninguno sin medir.
 */
export async function expectStatusContrast(page: Page, what: string): Promise<void> {
  const low = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 2;
    canvas.height = 2;
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
    const paint = (colors: string[]): [number, number, number] => {
      ctx.globalCompositeOperation = 'source-over';
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, 2, 2);
      for (const color of colors) {
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 2, 2);
      }
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0]!, d[1]!, d[2]!];
    };
    const luminance = ([r, g, b]: [number, number, number]) => {
      const f = (v: number) => {
        const c = v / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const out: string[] = [];
    for (const pill of Array.from(document.querySelectorAll<HTMLElement>('[data-slot="status"]'))) {
      const label = pill.querySelector<HTMLElement>('[data-slot="status-label"]') ?? pill;
      const box = label.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      // Los fondos, del de fuera al de dentro (el de la pastilla el ultimo).
      const layers: string[] = [];
      for (let el: HTMLElement | null = label; el; el = el.parentElement) {
        const bg = getComputedStyle(el).backgroundColor;
        if (bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)') layers.unshift(bg);
      }
      const background = paint(layers);
      const text = paint([...layers, getComputedStyle(label).color]);
      const [hi, lo] = [luminance(background), luminance(text)].sort((a, b) => b - a) as [number, number];
      const ratio = (hi + 0.05) / (lo + 0.05);
      if (ratio < 4.5) out.push(`${pill.dataset.variant} "${label.textContent ?? ''}": ${ratio.toFixed(2)}`);
    }
    return out;
  });
  expect(low, `contraste de las pastillas: ${what}`).toEqual([]);
}

/** Los campos de formulario (WCAG 1.4.11): su unica marca visible es el borde, que tiene que
 *  llegar a 3:1 frente a lo de fuera y lo de dentro (docs/app-local.md, «El tema claro»). Cada
 *  selector es de una pieza que la app monta: la gira de e2e/claro.spec.ts falla si alguno no
 *  aparece nunca (la lista nombraba `.ws-search`, la busqueda de Documentos de Aurora, que la app
 *  no monta, y el campo de verdad de las listas, `.search`, quedaba sin mirar). */
export const FORM_FIELDS = ['.order-field .composer', '.filter-combo-trigger', '.filter-date-trigger', '.ui-button', '.search'] as const;

/**
 * El borde de cada campo de formulario a la vista (FORM_FIELDS), compuesto como lo pinta Chromium
 * sobre los fondos que tiene detras (el mismo lienzo que expectStatusContrast): 3:1 o mas frente
 * al fondo de fuera y frente al suyo. Devuelve cuantos campos midio de cada selector.
 */
export async function expectFieldBoundary(page: Page, what: string, min = 3): Promise<Record<string, number>> {
  const result = await page.evaluate(
    ({ selectors, min }) => {
      const canvas = document.createElement('canvas');
      canvas.width = 2;
      canvas.height = 2;
      const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
      const paint = (colors: string[]): [number, number, number] => {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, 2, 2);
        for (const color of colors) {
          ctx.fillStyle = color;
          ctx.fillRect(0, 0, 2, 2);
        }
        const d = ctx.getImageData(0, 0, 1, 1).data;
        return [d[0]!, d[1]!, d[2]!];
      };
      const luminance = ([r, g, b]: [number, number, number]) => {
        const f = (v: number) => {
          const c = v / 255;
          return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
      };
      const ratio = (a: [number, number, number], b: [number, number, number]) => {
        const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
        return (hi + 0.05) / (lo + 0.05);
      };
      const backgrounds = (from: Element | null) => {
        const layers: string[] = [];
        for (let el = from as HTMLElement | null; el; el = el.parentElement) {
          const bg = getComputedStyle(el).backgroundColor;
          if (bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)') layers.unshift(bg);
        }
        return layers;
      };
      const low: string[] = [];
      const seen: Record<string, number> = {};
      for (const selector of selectors) {
        for (const field of Array.from(document.querySelectorAll<HTMLElement>(selector))) {
          const box = field.getBoundingClientRect();
          const style = getComputedStyle(field);
          if (box.width === 0 || box.height === 0 || style.visibility === 'hidden' || parseFloat(style.borderTopWidth) === 0) continue;
          if (box.bottom < 0 || box.top > innerHeight || box.right < 0 || box.left > innerWidth) continue;
          seen[selector] = (seen[selector] ?? 0) + 1;
          const outside = backgrounds(field.parentElement);
          const inside = backgrounds(field);
          const border = paint([...inside, style.borderTopColor]);
          const worst = Math.min(ratio(border, paint(outside)), ratio(border, paint(inside)));
          if (worst < min) low.push(`${selector} (${style.borderTopColor}): ${worst.toFixed(2)}`);
        }
      }
      return { low, seen };
    },
    { selectors: [...FORM_FIELDS], min }
  );
  expect(result.low, `el borde de los campos: ${what}`).toEqual([]);
  return result.seen;
}

/** Un placeholder a la vista, medido. */
export interface PlaceholderMeasure {
  /** Donde esta: `#token`, `label.search input`, `div.ui-command-input input`... */
  field: string;
  text: string;
  /** El color del placeholder (el calculado, con su alfa), el fondo de verdad que tiene detras
   *  (el de sus pixeles), el color que resulta de pintar uno sobre otro y su razon de contraste. */
  color: string;
  background: string;
  seen: string;
  ratio: number;
}

/**
 * Cada placeholder a la vista (un campo vacio, sin tapar y activo: WCAG 1.4.3 no pide contraste a
 * lo inactivo), medido contra el fondo de verdad: el color calculado de ::placeholder (con su
 * alfa, su opacidad y la de lo que lo contiene), pintado como lo pinta Chromium sobre el color que
 * mas se repite en los pixeles de la caja del campo (un fondo translucido, un cristal o un
 * degradado cuentan como se ven, no como estan escritos). axe no mide los placeholders con alfa:
 * el de las listas («Zoek bedrijf of document…») salia con el 50 % del color del campo que le da
 * Tailwind, a 2,08:1, y ninguna guarda lo veia.
 */
export async function placeholderContrasts(page: Page): Promise<PlaceholderMeasure[]> {
  const shown = await page.evaluate(() => {
    const out: { field: string; text: string; color: string; alpha: number; clip: { x: number; y: number; width: number; height: number } }[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input[placeholder], textarea[placeholder]'))) {
      if (!el.placeholder.trim() || !el.matches(':placeholder-shown') || el.disabled) continue;
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden') continue;
      // La caja del texto (sin el borde ni el relleno), dentro de la ventana.
      const left = Math.max(0, box.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft));
      const right = Math.min(innerWidth, box.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight));
      const top = Math.max(0, box.top + parseFloat(style.borderTopWidth) + parseFloat(style.paddingTop));
      const bottom = Math.min(innerHeight, box.bottom - parseFloat(style.borderBottomWidth) - parseFloat(style.paddingBottom));
      if (right - left < 4 || bottom - top < 4) continue;
      // Lo que tapa otra capa (un dialogo, un menu abierto encima) no se lee.
      const over = document.elementFromPoint((left + right) / 2, (top + bottom) / 2);
      if (!over || (over !== el && !over.contains(el))) continue;
      const placeholder = getComputedStyle(el, '::placeholder');
      let alpha = parseFloat(placeholder.opacity);
      for (let e: Element | null = el; e; e = e.parentElement) alpha *= parseFloat(getComputedStyle(e).opacity);
      if (!(alpha > 0)) continue;
      const parent = el.parentElement;
      const where = parent ? `${parent.tagName.toLowerCase()}${parent.classList.length ? `.${Array.from(parent.classList).join('.')}` : ''} ` : '';
      out.push({
        // Un id de Radix (radix-_r_4c_) cambia de una pasada a otra: no nombra nada.
        field: el.id && !/^radix-|^:/.test(el.id) ? `#${el.id}` : `${where}${el.tagName.toLowerCase()}`,
        text: el.placeholder,
        color: placeholder.color,
        alpha,
        clip: { x: Math.floor(left), y: Math.floor(top), width: Math.max(1, Math.floor(right - left)), height: Math.max(1, Math.floor(bottom - top)) },
      });
    }
    return out;
  });
  const lum = (c: number[]) =>
    c
      .map((v) => {
        const x = v / 255;
        return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
      })
      .reduce((n, x, k) => n + x * [0.2126, 0.7152, 0.0722][k]!, 0);
  const measures: PlaceholderMeasure[] = [];
  for (const item of shown) {
    const shot = decodePng(await page.screenshot({ clip: item.clip, animations: 'disabled', caret: 'hide' }));
    const counts = new Map<number, number>();
    for (let p = 0; p < shot.data.length; p += 4) {
      const key = (shot.data[p]! << 16) | (shot.data[p + 1]! << 8) | shot.data[p + 2]!;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const key = [...counts].sort((a, b) => b[1] - a[1])[0]![0];
    const background = [(key >> 16) & 255, (key >> 8) & 255, key & 255];
    // El color del texto sobre ese fondo, pintado por el navegador (entiende cualquier color
    // calculado: rgb(), oklab(), color(srgb ...)).
    const seen = await page.evaluate(
      ({ background, color, alpha }) => {
        const canvas = document.createElement('canvas');
        canvas.width = 2;
        canvas.height = 2;
        const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
        ctx.fillStyle = `rgb(${background.join(',')})`;
        ctx.fillRect(0, 0, 2, 2);
        ctx.globalAlpha = alpha;
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 2, 2);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        return [d[0]!, d[1]!, d[2]!];
      },
      { background, color: item.color, alpha: item.alpha }
    );
    const [hi, lo] = [lum(background), lum(seen)].sort((a, b) => b - a) as [number, number];
    measures.push({
      field: item.field,
      text: item.text,
      color: item.alpha < 1 ? `${item.color} x ${item.alpha}` : item.color,
      background: `rgb(${background.join(', ')})`,
      seen: `rgb(${seen.join(', ')})`,
      ratio: (hi + 0.05) / (lo + 0.05),
    });
  }
  return measures;
}

/** Cada placeholder a la vista a 4,5:1 o mas (WCAG 1.4.3) contra su fondo de verdad. Devuelve los
 *  medidos. Con BMS_E2E_PLACEHOLDERS=<fichero> los apunta ahi y no falla (para la tabla de
 *  docs/v1/registro.md). */
export async function expectPlaceholderContrast(page: Page, what: string, min = 4.5): Promise<PlaceholderMeasure[]> {
  const measures = await placeholderContrasts(page);
  if (process.env.BMS_E2E_PLACEHOLDERS) {
    for (const m of measures) appendFileSync(process.env.BMS_E2E_PLACEHOLDERS, JSON.stringify({ what, ...m, ratio: Number(m.ratio.toFixed(2)) }) + '\n');
    return measures;
  }
  const low = measures.filter((m) => m.ratio < min).map((m) => `${m.field} «${m.text}»: ${m.color} sobre ${m.background} = ${m.ratio.toFixed(2)}`);
  expect(low, `el contraste de los placeholders: ${what}`).toEqual([]);
  return measures;
}

/**
 * El contraste de un texto medido en pixeles (lo que axe no mide: el texto sobre un cristal, un
 * lienzo o un desenfoque): el recorte del texto (su trozo mas largo) de cada elemento a la vista
 * y sin tapar, su fondo
 * (el color que mas se repite) y su texto (la media del 2 % de pixeles mas lejos del fondo).
 * Devuelve los medidos.
 */
export async function expectPixelContrast(page: Page, selector: string, min: number, what: string): Promise<number[]> {
  const ratios: number[] = [];
  const items = page.locator(selector);
  const count = Math.min(await items.count(), 6);
  for (let i = 0; i < count; i += 1) {
    const item = items.nth(i);
    // La caja del texto, ajustada (Range): una fila ancha con una palabra pequena no cuenta su
    // hueco como fondo de mas. Un elemento sin texto, o transparente, no se mide.
    const box = await item.evaluate((el) => {
      if (!el.textContent?.trim()) return null;
      for (let e: Element | null = el; e; e = e.parentElement) if (getComputedStyle(e).opacity === '0') return null;
      // El trozo de texto mas largo del elemento (una ceja con su cuenta al otro lado, separados
      // por un hueco, cuenta solo la ceja): su caja ajustada.
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let longest: Text | null = null;
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if ((n.textContent?.trim().length ?? 0) > (longest?.textContent?.trim().length ?? 0)) longest = n as Text;
      }
      if (!longest) return null;
      const range = document.createRange();
      range.selectNodeContents(longest);
      const r = range.getBoundingClientRect();
      // Lo que tapa otra capa (el fundido del final de la conversacion, un dialogo) no se lee. Lo
      // que no recibe el raton (pointer-events:none, como el nombre de una carpeta) se mira igual.
      const passive: HTMLElement[] = [];
      for (let e = longest.parentElement; e; e = e.parentElement) if (getComputedStyle(e).pointerEvents === 'none') passive.push(e);
      const before = passive.map((e) => e.style.pointerEvents);
      passive.forEach((e) => (e.style.pointerEvents = 'auto'));
      const stack = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      passive.forEach((e, k) => (e.style.pointerEvents = before[k]!));
      // Lo que queda encima del texto tapa si pinta algo: un fondo con color o una imagen (un
      // degradado); una capa transparente o un lienzo (la escena de Procesar) no.
      const own = stack.findIndex((e) => e === longest.parentElement || el.contains(e));
      if (own < 0) return null;
      const covers = stack.slice(0, own).some((e) => {
        if (e.tagName === 'CANVAS') return false;
        const cs = getComputedStyle(e);
        const alpha = /rgba?\(([^)]+)\)/.exec(cs.backgroundColor)?.[1].split(',')[3];
        return cs.backgroundImage !== 'none' || (cs.backgroundColor !== 'transparent' && (alpha === undefined || parseFloat(alpha) > 0.05));
      });
      if (covers) return null;
      return { x: Math.floor(r.left), y: Math.floor(r.top), width: Math.ceil(r.width) + 1, height: Math.ceil(r.height) + 1 };
    });
    const view = page.viewportSize();
    if (!box || box.width < 2 || box.height < 2 || !view) continue;
    if (box.y + box.height <= 0 || box.y >= view.height || box.x + box.width <= 0 || box.x >= view.width) continue;
    if (!(await item.isVisible())) continue;
    const shot = decodePng(await page.screenshot({ clip: box, animations: 'disabled', caret: 'hide' }));
    const counts = new Map<number, number>();
    const px = shot.data;
    for (let p = 0; p < px.length; p += 4) {
      const key = (px[p]! << 16) | (px[p + 1]! << 8) | px[p + 2]!;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const bgKey = [...counts].sort((a, b) => b[1] - a[1])[0]![0];
    const bg = [(bgKey >> 16) & 255, (bgKey >> 8) & 255, bgKey & 255];
    const far: { d: number; c: number[] }[] = [];
    for (let p = 0; p < px.length; p += 4) {
      const c = [px[p]!, px[p + 1]!, px[p + 2]!];
      far.push({ d: Math.hypot(c[0]! - bg[0]!, c[1]! - bg[1]!, c[2]! - bg[2]!), c });
    }
    far.sort((a, b) => b.d - a.d);
    const top = far.slice(0, Math.max(1, Math.round(far.length * 0.02)));
    const ink = [0, 1, 2].map((k) => top.reduce((n, x) => n + x.c[k]!, 0) / top.length);
    const lum = (c: number[]) =>
      c
        .map((v) => {
          const x = v / 255;
          return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
        })
        .reduce((n, x, k) => n + x * [0.2126, 0.7152, 0.0722][k]!, 0);
    const [hi, lo] = [lum(bg), lum(ink)].sort((a, b) => b - a) as [number, number];
    const ratio = (hi + 0.05) / (lo + 0.05);
    ratios.push(ratio);
    expect.soft(ratio, `contraste en pixeles de ${selector} (${i + 1}): ${what}`).toBeGreaterThanOrEqual(min);
  }
  return ratios;
}

/**
 * El indicador de foco de una pieza, medido en pixeles (WCAG 1.4.11: 3:1 frente a lo que tiene al
 * lado): la columna del centro, de su borde de arriba hacia fuera. El anillo es el pixel que mas
 * se aparta del fondo de fuera (a 10 px); se compara con ese fondo y, si entre la pieza y el
 * anillo hay un hueco, con el hueco. Un halo translucido pegado a la pieza (el del oscuro pasado
 * al claro: 1,29) no llega; un anillo del acento separado por un hueco blanco, si.
 */
export async function focusRingContrast(page: Page, target: Locator): Promise<{ ring: string; inner: string | null; outer: string; ratio: number }> {
  const box = await target.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.floor(r.left + r.width / 2), top: Math.round(r.top) };
  });
  const reach = 10;
  const shot = decodePng(await page.screenshot({ clip: { x: box.x, y: box.top - reach, width: 1, height: reach }, animations: 'disabled', caret: 'hide' }));
  // De la pieza hacia fuera: column[0] toca su borde; column[reach - 1], lo de fuera.
  const column: number[][] = [];
  for (let y = reach - 1; y >= 0; y -= 1) column.push([shot.data[y * 4]!, shot.data[y * 4 + 1]!, shot.data[y * 4 + 2]!]);
  const far = (a: number[], b: number[]) => Math.hypot(a[0]! - b[0]!, a[1]! - b[1]!, a[2]! - b[2]!);
  const lum = (c: number[]) =>
    c
      .map((v) => {
        const x = v / 255;
        return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
      })
      .reduce((n, x, k) => n + x * [0.2126, 0.7152, 0.0722][k]!, 0);
  const contrast = (a: number[], b: number[]) => {
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x) as [number, number];
    return (hi + 0.05) / (lo + 0.05);
  };
  const outer = column[reach - 1]!;
  let at = 0;
  for (let i = 1; i < reach - 2; i += 1) if (far(column[i]!, outer) > far(column[at]!, outer)) at = i;
  const ring = column[at]!;
  let inner: number[] | null = null;
  for (let i = 0; i < at; i += 1) if (far(column[i]!, ring) > 24 && (!inner || far(column[i]!, ring) > far(inner, ring))) inner = column[i]!;
  const rgb = (c: number[]) => `rgb(${c.join(', ')})`;
  return {
    ring: rgb(ring),
    inner: inner ? rgb(inner) : null,
    outer: rgb(outer),
    ratio: Math.min(contrast(ring, outer), inner ? contrast(ring, inner) : Infinity),
  };
}

/** El tema que se ve: la clase .dark de <html> (lib/theme.tsx), la unica que lo decide. */
export async function shownTheme(page: Page): Promise<'dark' | 'light'> {
  return (await page.evaluate(() => document.documentElement.classList.contains('dark'))) ? 'dark' : 'light';
}

/** Una captura de la ventana a CAPTURAS_DIR/<tema>/<nombre>.png, para mirarla. */
export async function capture(page: Page, name: string): Promise<void> {
  const dir = join(process.env.CAPTURAS_DIR || join('test-results', 'capturas'), await shownTheme(page));
  mkdirSync(dir, { recursive: true });
  // Que no salga a medias una animacion ni el cursor de texto.
  await settled(page);
  await page.screenshot({ path: join(dir, `${name}.png`), caret: 'hide', animations: 'disabled' });
}

/**
 * Ningun resto de otro idioma en lo que se ve (paso 16; antes solo "nada de castellano"): en
 * neerlandes, ninguna palabra que solo sea inglesa o castellana; en ingles, ninguna neerlandesa
 * o castellana; en castellano, ninguna neerlandesa ni inglesa. Las listas son las de
 * src/i18n/leftovers.ts, las mismas que miran los diccionarios. Si un idioma dijera lo del
 * dominio con el catalogo de otro (DOMAIN_FALLBACK, src/i18n/langs.ts; desde que llego es.json,
 * ninguno), se tolerarian los restos de ese otro. Lo que no es de la app va con
 * data-proper-name y no cuenta: un nombre, un numero, un fichero de la persona, o el texto
 * libre de un campo tal como vino del documento.
 */
export async function expectNoLeftovers(page: Page, lang: Lang, what: string): Promise<void> {
  await expect(page.locator('html')).toHaveAttribute('lang', lang);
  const text = await page.evaluate(() => {
    let visible = document.body.innerText;
    // Las bandas que pone el servidor (.bms-banda, app_local.py) van en neerlandes e ingles a
    // la vez, a proposito: no son de la app.
    // Los mas largos primero: un "30" suelto no deja a medias un "30 dagen".
    const own = Array.from(document.querySelectorAll<HTMLElement>('[data-proper-name], .bms-banda'))
      .map((element) => (element.innerText || element.textContent || '').trim())
      .filter((t) => t !== '')
      .sort((a, b) => b.length - a.length);
    for (const t of own) visible = visible.split(t).join(' ');
    return visible;
  });
  const fallback = DOMAIN_FALLBACK[lang];
  // Cada resto con un poco de lo que lo rodea, para encontrarlo en la pantalla.
  const found = leftoversIn(text, lang, fallback ? [fallback] : []).map((hit) => {
    const word = hit.slice(hit.indexOf(':') + 1);
    const at = text.toLocaleLowerCase('nl-NL').search(new RegExp(`(?<!\\p{L})${word}(?!\\p{L})`, 'u'));
    return at < 0 ? hit : `${hit} («${text.slice(Math.max(0, at - 30), at + word.length + 30).replace(/\s+/g, ' ')}»)`;
  });
  expect(found, `restos de otro idioma en ${what}`).toEqual([]);
  // En castellano, ademas, un solo glosario (i18n/glossary.ts): la app y el catalogo del motor
  // decian IVA y BTW, abono y nota de credito... en la misma pantalla (revision del paso 16).
  if (lang === 'es') expect(glossaryMisses(text), `glosario del castellano en ${what}`).toEqual([]);
}

/**
 * Lo que se sale de la ventana por los lados: cada elemento visible que pasa del borde y no
 * esta dentro de algo que se desplaza en horizontal (una tabla en su caja). Lo que recorta un
 * overflow hidden no cuenta como desplazable: tambien es estar fuera. Lo usan el marco
 * (shell.spec.ts) y las pantallas de cobrar y pagar (payments.spec.ts).
 */
export async function outsideTheWindow(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const width = window.innerWidth;
    const out: string[] = [];
    if (document.documentElement.scrollWidth > width) out.push(`html ${document.documentElement.scrollWidth}`);
    if (document.body.scrollWidth > width) out.push(`body ${document.body.scrollWidth}`);
    const scrolls = (el: Element) => {
      const x = getComputedStyle(el).overflowX;
      return x === 'auto' || x === 'scroll';
    };
    // El orbe de Aurora se sale de la ventana a proposito (a 400 px, el de la rueda empieza en
    // x = -18, como en Aurora) y el lienzo del orbe pequeno de las pantallas de trabajo mide 180
    // px en su caja de 96: es la onda, sin nada que leer ni pulsar, y no da desplazamiento.
    const ORB = '.aurora, .aurora *, .ws-companion canvas, .aurora-route-flight, .aurora-route-flight *';
    for (const el of Array.from(document.body.querySelectorAll('*'))) {
      if (el.matches(ORB)) continue;
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      if (box.right <= width + 1 && box.left >= -1) continue;
      let inside = false;
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        if (scrolls(a)) {
          inside = true;
          break;
        }
      }
      if (!inside) {
        const name = el.getAttribute('aria-label') ?? el.textContent?.trim().slice(0, 30) ?? '';
        out.push(`${el.tagName.toLowerCase()} "${name}" ${Math.round(box.left)}-${Math.round(box.right)}`);
      }
    }
    return out;
  });
}
