// Lo que vigila cada prueba, sin que la prueba tenga que acordarse:
// - cada peticion de la pagina va a 127.0.0.1 (una a otro sitio se corta y la prueba falla);
// - ninguna violacion de la politica de contenido (CSP);
// - ningun error en la consola ni ninguna excepcion sin capturar.
// Y las ayudas: entrar con un token de prueba, el analisis de accesibilidad (axe) y las
// capturas, que van a CAPTURAS_DIR (por defecto test-results/capturas).
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type Page } from '@playwright/test';

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

export function token(who: 'ana' | 'bram' = 'ana'): string {
  const value = who === 'ana' ? process.env.BMS_E2E_TOKEN_ANA : process.env.BMS_E2E_TOKEN_BRAM;
  if (!value) throw new Error('faltan los tokens de prueba (e2e/global-setup.ts)');
  return value;
}

/** Entra con el token de una persona de prueba y espera al marco con las pestanas. */
export async function login(page: Page, who: 'ana' | 'bram' = 'ana'): Promise<void> {
  await page.locator('#token').fill(token(who));
  await page.locator('form button[type="submit"]').click();
  await expect(page.getByRole('tablist')).toBeVisible();
}

/** Ningun problema de accesibilidad serio o critico (WCAG 2.1 A y AA). */
export async function expectAccessible(page: Page, what: string): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious, `accesibilidad: ${what}`).toEqual([]);
}

/** Una captura de la ventana a CAPTURAS_DIR, para mirarla. */
export async function capture(page: Page, name: string): Promise<void> {
  const dir = process.env.CAPTURAS_DIR || join('test-results', 'capturas');
  mkdirSync(dir, { recursive: true });
  // Que no salga a medias una animacion ni el cursor de texto.
  await page.waitForTimeout(350);
  await page.screenshot({ path: join(dir, `${name}.png`), caret: 'hide', animations: 'disabled' });
}
