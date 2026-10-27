// Lo que vigila cada prueba, sin que la prueba tenga que acordarse:
// - cada peticion de la pagina va a 127.0.0.1 (una a otro sitio se corta y la prueba falla);
// - ninguna violacion de la politica de contenido (CSP);
// - ningun error en la consola ni ninguna excepcion sin capturar.
// Y las ayudas: entrar con un token de prueba, elegir el tema, el analisis de accesibilidad
// (axe), los restos de otro idioma y las capturas, que van a CAPTURAS_DIR (por defecto
// test-results/capturas), en una carpeta por tema: dark/ o light/ (paso 16).
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type Page } from '@playwright/test';
import { DOMAIN_FALLBACK, type Lang } from '../src/i18n/langs';
import { leftoversIn } from '../src/i18n/leftovers';
import { THEME_CHOICES, type ThemeChoice } from '../src/lib/theme-choice';

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

/** Entra con el token de una persona de prueba y espera al inicio (paso 16: el saludo y la
 *  rueda; antes, el marco con las pestanas). */
export async function login(page: Page, who: Who = 'ana'): Promise<void> {
  await page.locator('#token').fill(token(who));
  await page.locator('#login-submit').click();
  await expect(page.locator('#contenido')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: /^(Welkom|Welcome|Hola), / })).toBeVisible();
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
          // La pantalla que entra con un fundido al cambiar de sitio (shell/app-shell.tsx).
          const panels = Array.from(document.querySelectorAll<HTMLElement>('#view > div'));
          if (panels.length > 1 || panels.some((el) => getComputedStyle(el).opacity !== '1')) return null;
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

/** Ningun problema de accesibilidad serio o critico (WCAG 2.1 A y AA), ninguna falta de
 *  contraste (de ningun grado) y cada pastilla de estado medida a 4,5:1 o mas. Se mide con
 *  la pantalla quieta (settled). */
export async function expectAccessible(page: Page, what: string): Promise<void> {
  await settled(page);
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious, `accesibilidad: ${what}`).toEqual([]);
  const contrast = results.violations
    .filter((v) => v.id === 'color-contrast')
    .flatMap((v) => v.nodes.map((n) => `${n.target.join(' ')}: ${n.failureSummary ?? ''}`));
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

/** El tema que se ve: la clase .dark de <html> (lib/theme.tsx), la unica que lo decide. */
export async function shownTheme(page: Page): Promise<'dark' | 'light'> {
  return (await page.evaluate(() => document.documentElement.classList.contains('dark'))) ? 'dark' : 'light';
}

/** El menu del nombre, arriba a la derecha (en cualquier idioma). */
export const ACCOUNT_MENU = /^(Accountmenu van|Account menu for|Menú de la cuenta de) /;

/** Elige el tema en el menu del nombre (Donker / Licht / Volg Windows, en el orden de
 *  THEME_CHOICES, sea cual sea el idioma) y espera a que se vea. */
export async function chooseTheme(page: Page, choice: ThemeChoice): Promise<void> {
  await page.getByRole('button', { name: ACCOUNT_MENU }).click();
  const items = page.getByRole('menu').getByRole('group', { name: /^(Thema|Theme|Tema)$/ }).getByRole('menuitemradio');
  await expect(items).toHaveCount(THEME_CHOICES.length);
  await items.nth(THEME_CHOICES.indexOf(choice)).click();
  await expect(page.getByRole('menu')).toBeHidden();
  if (choice !== 'system') {
    await expect(page.locator('html')).toHaveAttribute('data-theme', choice);
  }
  await settled(page);
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
}
