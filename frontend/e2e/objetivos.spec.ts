// Lo que se pulsa, de 24 × 24 px como poco (WCAG 2.2, 2.5.8; peticion del dueno del 02-11-2026:
// «Sí, amplía también esos controles»). Las zonas tactiles de bms.css agrandan los controles
// pequenos sin que nada cambie a la vista:
// - la guarda: en cada estado de la gira (e2e/objetivos.ts), a 400 × 860 con el raton y con el
//   dedo, a ningun elemento que se pulse le falta un cuadrado de 24 × 24 de puntos suyos (medidos
//   con elementFromPoint) salvo con la excepcion del espaciado, ni a los apuntados abajo con su
//   razon (hoy, ninguno);
// - cada zona, a 1440 y a 400, con el raton y con el dedo (pointer: coarse), en oscuro y en claro:
//   su tamano medido (24 o mas; con el dedo, 44 donde cabe), que no pisa a nadie (a donde va un
//   clic, punto a punto, con las zonas y sin ellas: solo cambian puntos que no eran de nadie, o del
//   margen de la hoja para su ✕, o de la pista del importe para sus tiradores), las mismas medidas
//   de desplazamiento y los mismos pixeles (en reposo, con el raton encima y con el foco del
//   teclado) que sin ellas;
// - con el dedo (isMobile, hasTouch, 400 × 860): un toque cerca del borde de cada zona, fuera de lo
//   que se ve, hace lo mismo que uno en el control; y donde una zona linda con otra cosa (la lista
//   de las empresas sobre los tiradores, «Filters wissen» sobre el campo de la empresa, la esquina
//   de la ✕ de una tarjeta en un panel y en la hoja, «Kaart … openen» bajo su carpeta, dos lineas
//   de migas), cada toque de verdad va adonde iba en 1cc96b0, o a la zona si antes no hacia nada
//   (Chromium acerca un toque al objetivo que mejor cae bajo el dedo: elementFromPoint no lo ve;
//   el clic en el margen de una hoja la cierra, y eso no es nada; el de una etiqueta es el de su
//   control).
import type { Locator, Page } from '@playwright/test';
import { expect, expectAccessible, login, N, settled, test } from './fixtures';
import {
  TEXTS,
  ask,
  fill,
  chooseTheme,
  detail,
  folderProfile,
  openCard,
  openDocuments,
  openEntry,
  openFolder,
  openGroup,
  openInvoice,
  openSheetRow,
  panel,
  panelRow,
  processLanded,
  sheetDialog,
  signOut,
  toHome,
  wheel,
} from './nav';
import { areaOf, grid, hitChanges, measureTargets, scrollChanges, tapChanges, tour, zoneTour, type TapChange, type Target } from './objetivos';
import { decodePng, differingPixels } from './png';
import { coarsePointer, withoutHitArea, ZONES } from './zona-tactil';

const t = TEXTS.nl;
const JV = 'J. Voorbeeld Beveiliging (zzp)';
const HAVEN = 'Demo Havenbedrijf BV';

/** Los que pueden quedarse por debajo de 24 × 24, con su razon. Hoy ninguno: cada control
 *  pequeno tiene su zona, y a lo que no le cabe un cuadrado de 24 de puntos suyos (los dias del
 *  calendario, los botones de una respuesta) le vale la excepcion del espaciado de 2.5.8, que se
 *  mide (objetivos.ts). Aparte, lo que tapa en parte una lista abierta (el calendario, la de las
 *  empresas, la de los tipos) no cuenta mientras esta abierta: se ve debajo, y un clic fuera de la
 *  lista la cierra (Radix); tampoco los tiradores del importe mientras una lista de los filtros
 *  esta abierta (sin zona, como en 1cc96b0: bms.css). */
const EXCEPTIONS: { what: RegExp; why: string }[] = [];

// ------------------------------------------------------------------ la guarda

for (const pointer of ['raton', 'dedo'] as const) {
  test.describe(`a 400 × 860, con el ${pointer}`, () => {
    test.use(pointer === 'dedo' ? { viewport: { width: 400, height: 860 }, hasTouch: true, isMobile: true } : { viewport: { width: 400, height: 860 } });

    test(`nada que se pulse mide menos de 24 × 24 en la gira, y las zonas no pisan, no desplazan ni se ven (${pointer})`, async ({ page, baseUrl }) => {
      test.setTimeout(1_800_000);
      await page.goto(`${baseUrl}/app`);
      expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(pointer === 'dedo');
      const small: string[] = [];
      const spaced = new Set<string>();
      const wrong: string[] = [];
      const taken: Record<string, number> = {};
      let states = 0;
      let measured = 0;
      await tour(page, async (state) => {
        states += 1;
        const all = await measureTargets(page);
        measured += all.length;
        // Cabe un cuadrado de 24 de puntos suyos; si no, la excepcion del espaciado (los dias del
        // calendario, circulos de 30, y los botones de una respuesta, de 26 redondeados: les cabe uno
        // de 23, igual que en 1cc96b0).
        for (const s of all.filter((x) => x.square < 24)) {
          if (s.underPopover || EXCEPTIONS.some((e) => e.what.test(s.what))) continue;
          // A un control con zona no le vale el espaciado: su zona tiene que dar el cuadrado (sin
          // ella, la ✕ de una tarjeta, sola en su esquina, pasaria por el espaciado).
          if (s.spacing && !s.zone) {
            spaced.add(`${s.what.replace(/«.*»/, '«…»')} ${s.square}`);
            continue;
          }
          small.push(`${state}: ${s.what}, su caja ${s.box.width} × ${s.box.height}, su zona ${s.hit.width} × ${s.hit.height}, su mayor cuadrado ${s.square}`);
        }
        // En cada estado de la gira, como en 1cc96b0 (las zonas nuevas quitadas): a donde va un clic
        // (salvo lo permitido), las medidas de desplazamiento y los pixeles en reposo.
        const changes = await hitChanges(page);
        wrong.push(...changes.wrong.map((w) => `${state}: ${w}`));
        for (const [k, n] of Object.entries(changes.taken)) taken[k] = (taken[k] ?? 0) + n;
        wrong.push(...(await scrollChanges(page)).map((w) => `${state}: las medidas de desplazamiento, ${w}`));
        await page.mouse.move(1, 1);
        await samePixels(page, state);
      });
      console.log(`la guarda (${pointer}): ${states} estados, ${measured} objetivos medidos, ${small.length} de menos de 24 × 24${small.map((x) => `\n  ${x}`).join('')}`);
      console.log(`por debajo de 24 con la excepcion del espaciado: ${[...spaced].join(' · ')}`);
      console.log(`lo que pasa a ser de una zona en la gira: ${Object.entries(taken).map(([k, n]) => `${k}: ${n}`).join(' · ')}`);
      console.log(`lo que no deberia: ${wrong.length}${wrong.map((x) => `\n  ${x}`).join('')}`);
      expect(states).toBeGreaterThan(60);
      expect(small).toEqual([]);
      expect(wrong).toEqual([]);
    });
  });
}

// ------------------------------------------------------------------ cada zona

/** Lo que mide la zona de cada control como poco (el alto y el ancho que da elementFromPoint):
 *  24 con el raton y 44 con el dedo, salvo donde no cabe. */
function least(zone: string, coarse: boolean): number {
  if (!coarse) return 24;
  // Las migas: 24, como con raton (bms.css): dos lineas de migas quedan a 10 px (a 400 px, la
  // ficha de un proveedor), y mas alto, Chromium daba a la de abajo toques de las de arriba.
  if (zone === 'las migas de Documentos') return 24;
  // Los tiradores: el de abajo, al principio de la pista, llega al borde de la ventana a 400 px.
  if (zone === 'los tiradores del importe') return 24;
  // «Abrir la ficha»: encima pinta la sombra de la carpeta (bms.css).
  if (zone === '«Abrir la ficha» de una carpeta') return 39;
  // «Filters wissen»: mas alta, Chromium le daba toques del borde de arriba del campo de la empresa.
  if (zone === '«Filters wissen» de la busqueda') return 32;
  return 44;
}

/** La ventana con las zonas y sin ellas: los mismos pixeles (los lienzos, que se mueven solos,
 *  tapados en las dos). Si cambia algo, se repite: cuenta solo lo que cambia con la zona y no lo
 *  que cambia solo (dos capturas seguidas con ella, iguales; sin ella, distinta). */
async function samePixels(page: Page, what: string): Promise<void> {
  const shot = async () => decodePng(await page.screenshot({ caret: 'hide', animations: 'disabled', mask: [page.locator('canvas')], maskColor: '#ff00ff' }));
  let message = '';
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await settled(page);
    const withArea = await shot();
    await withoutHitArea(page, true, 'nuevas');
    const without = await shot();
    await withoutHitArea(page, false, 'nuevas');
    const n = differingPixels(withArea, without, { tolerance: 0 });
    if (n === 0) return;
    // Lo que cambia solo (una animacion): otra captura con la zona, distinta de la primera.
    if (differingPixels(withArea, await shot(), { tolerance: 0 }) > 0) continue;
    // Donde: la caja de los pixeles distintos, para encontrarlos.
    let [x0, y0, x1, y1] = [Infinity, Infinity, -1, -1];
    for (let y = 0; y < withArea.height; y += 1)
      for (let x = 0; x < withArea.width; x += 1) {
        const i = (y * withArea.width + x) * 4;
        if ([0, 1, 2].some((c) => withArea.data[i + c] !== without.data[i + c])) [x0, y0, x1, y1] = [Math.min(x0, x), Math.min(y0, y), Math.max(x1, x), Math.max(y1, y)];
      }
    message = `${what}: ${n} pixeles cambian con la zona, entre (${x0}, ${y0}) y (${x1}, ${y1})`;
    break;
  }
  expect(message, what).toBe('');
}

/** Los controles con zona nueva que se ven, tres de cada como mucho; primero los de una lista
 *  abierta (el foco en otro sitio la cierra). Cada uno se trae a la vista al mirarlo (`inView`). */
async function zoneControls(page: Page): Promise<{ zone: string; el: Locator }[]> {
  const out: { zone: string; el: Locator }[] = [];
  for (const z of ZONES.slice(1).sort((a, b) => Number(!a.selector.includes('ui-command')) - Number(!b.selector.includes('ui-command')))) {
    const all = page.locator(z.selector);
    for (let i = 0, n = 0; i < (await all.count()) && n < 3; i += 1) {
      const el = all.nth(i);
      if (await el.evaluate((e) => e.checkVisibility({ visibilityProperty: true }) && e.getBoundingClientRect().width > 0)) (out.push({ zone: z.name, el }), (n += 1));
    }
  }
  return out;
}

/** El control en el centro de la vista (a 400 px, los tiradores y las carpetas quedan debajo):
 *  si su centro es suyo, se puede mirar. */
async function inView(page: Page, el: Locator): Promise<boolean> {
  await el.evaluate((e) => e.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }));
  await settled(page);
  return el.evaluate((e) => {
    const r = e.getBoundingClientRect();
    const [x, y] = [r.left + r.width / 2, r.top + r.height / 2];
    return x >= 0 && y >= 0 && x < innerWidth && y < innerHeight && e.contains(document.elementFromPoint(x, y));
  });
}

for (const size of [
  { width: 1440, height: 900 },
  { width: 400, height: 860 },
]) {
  for (const pointer of ['raton', 'dedo'] as const) {
    test(`las zonas tactiles a ${size.width} px con el ${pointer}: su tamano, sin pisar nada, sin desplazar ni verse`, async ({ page, baseUrl }) => {
      test.setTimeout(1_500_000);
      await page.setViewportSize(size);
      await page.goto(`${baseUrl}/app`);
      await coarsePointer(page, pointer === 'dedo');
      const coarse = pointer === 'dedo';
      const sizes = new Map<string, Target['hit']>();
      const taken: Record<string, number> = {};
      let compared = 0;
      const focused = new Set<string>();
      for (const theme of ['dark', 'light'] as const) {
        if (theme === 'light') {
          await chooseTheme(page, 'light');
          await signOut(page);
        }
        await zoneTour(page, async (state) => {
          const where = `${state} (${theme}, ${size.width} px, ${pointer})`;
          // No pisa a nadie: a donde va un clic, punto a punto.
          const changes = await hitChanges(page);
          expect(changes.wrong, `${where}: lo que cambia y no deberia`).toEqual([]);
          for (const [k, n] of Object.entries(changes.taken)) taken[k] = (taken[k] ?? 0) + n;
          // Lo que se desplaza, igual.
          expect(await scrollChanges(page), `${where}: las medidas de desplazamiento`).toEqual([]);
          // Su tamano medido.
          // (Lo tapado en parte por una lista abierta no cuenta, como en la guarda.)
          for (const m of (await measureTargets(page)).filter((x) => x.zone && !x.underPopover)) {
            const need = least(m.zone!, coarse);
            expect(Math.min(m.hit.width, m.hit.height), `${where}: ${m.what} (${m.zone}) mide ${m.hit.width} × ${m.hit.height}`).toBeGreaterThanOrEqual(need);
            expect(m.square, `${where}: ${m.what} (${m.zone}), su mayor cuadrado`).toBeGreaterThanOrEqual(24);
            const seen = sizes.get(`${m.zone}: ${m.what}`);
            if (!seen || m.hit.width * m.hit.height < seen.width * seen.height) sizes.set(`${m.zone}: ${m.what}`, m.hit);
          }
          // Los mismos pixeles: en reposo, con el raton encima de cada control y con su foco.
          await page.mouse.move(1, 1);
          await samePixels(page, where);
          compared += 1;
          for (const { zone, el } of await zoneControls(page)) {
            if (!(await inView(page, el))) continue;
            const label = `${where}, ${await el.evaluate((e) => e.getAttribute('aria-label') ?? (e as HTMLElement).innerText.trim())}`;
            const box = (await el.boundingBox())!;
            if (!coarse) {
              await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
              await samePixels(page, `${label}, con el raton encima`);
              await page.mouse.move(1, 1);
              compared += 1;
            }
            // El foco del teclado (Tab y luego el control: asi se ve su anillo).
            await page.keyboard.press('Tab');
            await el.focus();
            expect(await el.evaluate((e) => e.matches(':focus-visible')), `${label}: su anillo`).toBe(true);
            await samePixels(page, `${label}, con el foco`);
            focused.add(zone);
            compared += 1;
            await el.blur();
          }
        });
      }
      await coarsePointer(page, false);
      // Cada zona nueva, comparada con su foco (la del control de la hoja plegada, en documents.spec.ts).
      expect([...focused].sort()).toEqual(ZONES.slice(1).map((z) => z.name).sort());
      // Para el registro.
      console.log(`a ${size.width} px con el ${pointer}: ${compared} capturas iguales; ${[...sizes].map(([k, v]) => `${k} ${v.width} × ${v.height}`).join(' · ')}`);
      console.log(`lo que pasa a ser de una zona: ${Object.entries(taken).map(([k, n]) => `${k}: ${n}`).join(' · ')}`);
    });
  }
}

// ------------------------------------------------------------------ con el dedo

/** Un toque cerca del borde de la zona (a 2 px de su esquina de abajo a la derecha, o de la que
 *  se pida, o a `inset`), fuera de lo que se ve: el punto es del control. */
async function tapEdge(page: Page, control: Locator, corner: 'abajo-derecha' | 'abajo-izquierda' | 'arriba-derecha' = 'abajo-derecha', inset = 2): Promise<void> {
  await control.evaluate((e) => e.scrollIntoView({ block: 'center', inline: 'nearest' }));
  await settled(page);
  const { box, area } = await areaOf(control);
  const x = corner === 'abajo-izquierda' ? area.x + inset : area.x + area.width - inset;
  const y = corner === 'arriba-derecha' ? area.y + inset : area.y + area.height - inset;
  const outside = x < box.x || x > box.x + box.width || y < box.y || y > box.y + box.height;
  expect(outside, `el toque (${x.toFixed(1)}, ${y.toFixed(1)}) cae fuera de lo que se ve`).toBe(true);
  expect(await control.evaluate((e, [px, py]) => e.contains(document.elementFromPoint(px!, py!)), [x, y]), 'el punto es del control').toBe(true);
  await page.touchscreen.tap(x, y);
}

test.describe('con el dedo, a 400 px', () => {
  test.use({ viewport: { width: 400, height: 860 }, hasTouch: true, isMobile: true });

  test('un toque en el borde de cada zona, fuera de lo que se ve, hace lo que un toque en el control', async ({ page, baseUrl }) => {
    test.setTimeout(600_000);
    await page.goto(`${baseUrl}/app`);
    expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
    // Los idiomas de la entrada.
    await tapEdge(page, page.getByRole('button', { name: 'English', exact: true }), 'abajo-izquierda');
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await tapEdge(page, page.getByRole('button', { name: 'Nederlands', exact: true }), 'arriba-derecha');
    await expect(page.locator('html')).toHaveAttribute('lang', 'nl');
    await login(page);
    // La ✕ del panel: a la rueda.
    await openEntry(page, 'settings');
    await tapEdge(page, panel(page).getByRole('button', { name: t.aurora.panel.close }));
    await expect(panel(page)).toHaveCount(0);
    await expect(wheel(page)).toBeVisible();
    // La ✕ de la tarjeta de una fila: se cierra la tarjeta, el panel sigue.
    await openEntry(page, 'home');
    await openGroup(page, t.aurora.home.first);
    await openCard(page, panel(page).locator('.doc-list button.doc').first());
    await tapEdge(page, detail(page).locator('.detail-close'), 'abajo-izquierda');
    await expect(detail(page)).toHaveCount(0);
    await expect(panel(page)).toBeVisible();
    // Los tiradores del importe: el toque lo agarra (el foco) y no lo mueve.
    await openEntry(page, 'search');
    await page.locator('.filters-toggle').click();
    await expect(page.locator('#search-filters')).toBeVisible();
    await settled(page);
    for (const [i, corner] of [[0, 'abajo-derecha'], [1, 'abajo-izquierda']] as const) {
      const thumb = page.locator('.amount-thumb').nth(i);
      const value = await thumb.getAttribute('aria-valuenow');
      await tapEdge(page, thumb, corner);
      await expect(thumb).toBeFocused();
      await expect(thumb).toHaveAttribute('aria-valuenow', value!);
    }
    // El buscador de una lista: el foco va a su caja.
    await page.locator('#search-filters .party-combobox button').click();
    const input = page.locator('.ui-popover .ui-command-input input');
    await expect(input).toBeVisible();
    await input.evaluate((e) => (e as HTMLElement).blur());
    await tapEdge(page, input);
    await expect(input).toBeFocused();
    await page.keyboard.press('Escape');
    // «Filters wissen»: los filtros se quitan.
    await openEntry(page, 'receivables');
    await panelRow(page, t.aurora.money.overdue).click();
    await expect(page.locator('.active-filter-chips')).toBeVisible();
    await tapEdge(page, page.locator('.filters-reset'), 'abajo-izquierda');
    await expect(page.locator('.active-filter-chips')).toHaveCount(0);
    // «Terug naar de werkruimte»: la rueda, sin la conversacion.
    await toHome(page);
    await ask(page, 'Geef me een overzicht');
    await tapEdge(page, page.getByRole('button', { name: t.aurora.chat.back }));
    await expect(page.locator('.conversation')).toHaveCount(0);
    await expect(wheel(page)).toBeVisible();
    // «Kaart openen» de una carpeta: su ficha.
    await openDocuments(page);
    const caption = page.locator('.ws-folder-caption > a').first();
    const name = (await caption.evaluate((a) => a.closest('[data-testid=folder-cell]')!.querySelector('.gf-title')!.textContent)) ?? '';
    await tapEdge(page, caption);
    await expect(folderProfile(page, name)).toBeVisible();
    // «Terug naar Aurora» sobre la miga de la pagina (a 400 px, la ficha de un cliente): sus zonas
    // quedan a 3 px sin pisarse, y un toque a 1,5-2,5 px del borde de abajo de la de «Terug naar
    // Aurora» le llega, de punta a punta salvo la esquina de abajo a la izquierda; uno igual de
    // cerca del borde de arriba de la miga, a la miga. Con la capa (::before), Chromium acercaba
    // muchos a la miga de debajo (cuenta la caja de cada uno, no su ::before); con relleno y margen
    // (bms.css), la caja es la zona. En la esquina (sus 6 px), lo mas del dedo cae en la miga y
    // Chromium se lo da a ella, como en dos zonas cualesquiera que lindan. Los clics, parados.
    await openFolder(page, HAVEN, 'client');
    const home = page.locator('a.ws-home');
    await home.evaluate((e) => e.scrollIntoView({ block: 'center' }));
    await settled(page);
    const crumb = page.locator('.ws-breadcrumbs a[aria-current=page]');
    const { area: homeArea } = await areaOf(home);
    const { area: crumbArea } = await areaOf(crumb);
    const gap = crumbArea.y - (homeArea.y + homeArea.height);
    expect(gap, 'la zona queda a 3 px de la de la miga, sin pisarla').toBeGreaterThan(2.95);
    expect(gap, 'la zona queda a 3 px de la de la miga, sin pisarla').toBeLessThan(3.05);
    await page.evaluate(() => {
      const w = window as unknown as { __toques: string[]; __toque: (e: Event) => void; __para: (e: Event) => void };
      w.__toques = [];
      w.__toque = (e) => {
        const el = e.target as Element;
        w.__toques.push(el.closest('a.ws-home') ? 'ws-home' : el.closest('.ws-breadcrumbs a[aria-current=page]') ? 'miga' : (el.closest('a, button')?.textContent ?? 'nada'));
      };
      w.__para = (e) => (e.preventDefault(), e.stopPropagation());
      document.addEventListener('pointerdown', w.__toque, true);
      document.addEventListener('click', w.__para, true);
    });
    const expected: string[] = [];
    for (let x = homeArea.x + 7.5; x <= homeArea.x + homeArea.width - 1.5; x += 6)
      for (const d of [1.5, 2, 2.5]) {
        await page.touchscreen.tap(x, homeArea.y + homeArea.height - d);
        expected.push('ws-home');
        if (x > crumbArea.x + 1.5 && x < crumbArea.x + crumbArea.width - 1.5) (await page.touchscreen.tap(x, crumbArea.y + d), expected.push('miga'));
      }
    const homeTaps = await page.evaluate(() => {
      const w = window as unknown as { __toques: string[]; __toque: (e: Event) => void; __para: (e: Event) => void };
      document.removeEventListener('pointerdown', w.__toque, true);
      document.removeEventListener('click', w.__para, true);
      return w.__toques;
    });
    expect(homeTaps, 'los toques del borde de abajo, en «Terug naar Aurora»; los del borde de arriba de la miga, en ella').toEqual(expected);
    await expect(folderProfile(page, HAVEN)).toBeVisible();
    // La miga «Documenten»: la rejilla, sin ficha.
    await openFolder(page, JV, 'provider');
    // Por arriba (sus zonas crecen 2 px: el toque, a 1 del borde): a 400 px, la ficha deja las
    // migas en dos lineas a 10 px (sus zonas, a 6) y un toque del hueco va a la que mas cae bajo el
    // dedo (abajo, la prueba de los toques junto a las zonas).
    await tapEdge(page, page.locator('.ws-breadcrumbs a').nth(1), 'arriba-derecha', 1);
    await expect(page.locator('.ws-profile')).toHaveCount(0);
    await expect(page.locator('.ws-breadcrumbs [aria-current=page]')).toHaveText(t.nav.documents.label);
    // La ✕ de la tarjeta de una fila de la hoja: se cierra la tarjeta y la hoja sigue.
    await openInvoice(page, N.oost);
    const card = await openSheetRow(page, t.aurora.sheet.more);
    await tapEdge(page, card.locator('.detail-close'), 'abajo-izquierda');
    await expect(sheetDialog(page).locator('.detail')).toHaveCount(0);
    await expect(sheetDialog(page)).toBeVisible();
    // La ✕ de la hoja: se cierra.
    await sheetDialog(page).evaluate((d) => (d.scrollTop = 0));
    await tapEdge(page, sheetDialog(page).locator('.ws-dialog-top button'), 'abajo-izquierda');
    await expect(sheetDialog(page)).toHaveCount(0);
    await expectAccessible(page, 'Documentos con el dedo');
    // «Terug naar Aurora»: el inicio.
    await tapEdge(page, page.locator('a.ws-home'), 'abajo-izquierda');
    await expect(page.locator('[data-aurora-root]')).toHaveAttribute('data-screen', 'home');
    // «Terug naar start» de Procesar: el inicio.
    await openEntry(page, 'process');
    await processLanded(page);
    await tapEdge(page, page.locator('.processing-back'));
    await expect(page.locator('[data-aurora-root] .app')).not.toHaveClass(/\bprocess-mode\b/);
    // Con el inicio ya quieto (el texto discreto entra con un fundido).
    await settled(page);
    await expectAccessible(page, 'el inicio con el dedo');
  });
  // Lo que elementFromPoint no ve (la guarda): Chromium acerca un toque al objetivo que mejor cae
  // bajo el dedo, su caja entera, aunque el punto sea de otro. Donde una zona linda con otra cosa,
  // se toca punto a punto con las zonas y sin ellas (como en 1cc96b0), con los clics parados: cada
  // toque va adonde iba, o a una zona si antes no hacia nada (nada, o la miga de la pagina en que
  // se esta). Una sola excepcion, igual para quien toca: bajo la carpeta, lo que iba a la carpeta
  // y ahora va a su «Kaart … openen» abre la misma ficha (las dos llaman a onOpen).
  test('los toques junto a las zonas van adonde iban en 1cc96b0, o a la zona si no hacian nada', async ({ page, baseUrl }) => {
    test.setTimeout(1_500_000);
    await page.goto(`${baseUrl}/app`);
    await login(page);
    const wrong: string[] = [];
    const nothing = (s: string) => s.startsWith('nada') || s.startsWith('sin clic (nada') || s.endsWith('(la pagina en que se esta)');
    const [pre, post] = t.aurora.archive.openProfileNamed.split('{name}') as [string, string];
    const sameFolder = (c: TapChange) => {
      const m = c.after.match(/^a «(.*)» \[zona\]$/);
      if (!m || !m[1]!.startsWith(pre) || !m[1]!.endsWith(post)) return false;
      const name = m[1]!.slice(pre.length, m[1]!.length - post.length);
      return c.before.startsWith(`button.gf-hit «${name} `) && c.after === `a «${fill(t.aurora.archive.openProfileNamed, { name })}» [zona]`;
    };
    // El margen de una hoja junto a su ✕: el clic en el dialogo la cerraba y ahora la cierra la ✕.
    const sameClose = (c: TapChange) => c.before.startsWith('cierra la hoja') && c.after === `button «${t.aurora.archive.closePreview}» [zona]`;
    // En el hueco entre dos zonas (de ninguna), la frontera entre las dos puede moverse.
    let gaps: DOMRect[] = [];
    let moved = 0;
    const inGap = (c: TapChange) => c.before.endsWith('[zona]') && c.after.endsWith('[zona]') && !gaps.some((r) => c.x >= r.left && c.x <= r.right && c.y >= r.top && c.y <= r.bottom);
    const check = (where: string, changes: TapChange[], points: number) => {
      const groups = new Map<string, TapChange[]>();
      let fine = 0;
      for (const c of changes) {
        if ((nothing(c.before) && c.after.endsWith('[zona]')) || sameFolder(c) || sameClose(c)) {
          fine += 1;
          continue;
        }
        if (inGap(c)) {
          moved += 1;
          continue;
        }
        const k = `${c.before} → ${c.after}`;
        groups.set(k, [...(groups.get(k) ?? []), c]);
      }
      wrong.push(...[...groups].map(([k, v]) => `${where}: ${k} (${v.length} puntos, p. ej. (${v[0]!.x}, ${v[0]!.y}))`));
      const shown = changes.filter((c) => !(nothing(c.before) && c.after.endsWith('[zona]')) && !sameFolder(c) && !sameClose(c));
      console.log(`${where}: ${points} toques, ${fine} pasan a una zona (o a la ficha de la misma carpeta), ${moved} en el hueco entre dos zonas cambian de una a otra, ${changes.length - fine - moved} sin permiso${shown.map((c) => `\n  (${c.x}, ${c.y}) ${c.before} → ${c.after}`).join('')}`);
      moved = 0;
    };
    // Alrededor de la caja de un control (traido al centro): de dx0 a dx1 y de dy0 a dy1 px de su
    // esquina de arriba a la izquierda (o de la de abajo a la derecha, los positivos que pasan de
    // su ancho o su alto se cuentan desde ahi).
    const around = async (el: Locator, x0: number, x1: number, dx: number, y0: number, y1: number, dy: number) => {
      await el.evaluate((e) => e.scrollIntoView({ block: 'center', behavior: 'instant' }));
      await settled(page);
      const b = (await el.boundingBox())!;
      return grid(b.x + x0, b.x + b.width + x1, dx, b.y + y0, b.y + b.height + y1, dy);
    };
    // La busqueda con la lista de las empresas abierta sobre los tiradores (a 400 px, el de abajo
    // queda debajo de su borde izquierdo): alrededor de cada tirador.
    await openEntry(page, 'search');
    await page.locator('.filters-toggle').click();
    await expect(page.locator('#search-filters')).toBeVisible();
    await page.locator('#search-filters .party-combobox button').click();
    await expect(page.locator('.ui-popover')).toBeVisible();
    await settled(page);
    await page.locator('.amount-thumb').first().evaluate((e) => e.scrollIntoView({ block: 'center', behavior: 'instant' }));
    await settled(page);
    for (const i of [0, 1]) {
      const b = (await page.locator('.amount-thumb').nth(i).boundingBox())!;
      const points = grid(b.x - 30, b.x + b.width + 30, 3, b.y - 30, b.y + b.height + 30, 3);
      check(`la lista de las empresas, el tirador ${i + 1}`, await tapChanges(page, points), points.length);
    }
    await expect(page.locator('.ui-popover')).toBeVisible();
    await page.keyboard.press('Escape');
    // «Filters wissen» con los filtros abiertos: 33 px por debajo, la etiqueta del campo de la
    // empresa (un toque en ella abre la lista). Con 44 de alto, Chromium le daba los toques de
    // encima de la etiqueta, que en 1cc96b0 iban a ella: quitaba los filtros.
    await openEntry(page, 'receivables');
    await panelRow(page, t.aurora.money.overdue).click();
    await expect(page.locator('.active-filter-chips')).toBeVisible();
    await page.locator('.filters-toggle').click();
    await expect(page.locator('#search-filters')).toBeVisible();
    await settled(page);
    const reset = await around(page.locator('.filters-reset'), -30, 16, 3, -24, 32, 2);
    check('«Filters wissen» sobre el campo de la empresa', await tapChanges(page, reset), reset.length);
    await expect(page.locator('.active-filter-chips')).toBeVisible();
    // La ✕ de la tarjeta de una fila en un panel: su esquina, dentro y fuera de la tarjeta.
    await openEntry(page, 'home');
    await openGroup(page, t.aurora.home.first);
    await openCard(page, panel(page).locator('.doc-list button.doc').first());
    const corner = (close: Locator) => around(close, -46, 20, 3, -20, 46, 2);
    const inPanel = await corner(detail(page).locator('.detail-close'));
    check('la ✕ de la tarjeta de una fila, en un panel', await tapChanges(page, inPanel), inPanel.length);
    await expect(detail(page)).toBeVisible();
    // Documentos: «Kaart … openen» bajo la primera carpeta (y la carpeta encima).
    await openDocuments(page);
    const caption = page.locator('.ws-folder-caption > a').first();
    await caption.evaluate((e) => e.scrollIntoView({ block: 'center', behavior: 'instant' }));
    await settled(page);
    const { box, area } = await areaOf(caption);
    const band = grid(area.x - 10, area.x + area.width + 10, 5, area.y - 16, box.y + 2, 1);
    check('la rejilla, «Kaart … openen»', await tapChanges(page, band), band.length);
    // La ficha de un proveedor: las migas en dos lineas, a 10 px (sus zonas, a 6).
    await openFolder(page, JV, 'provider');
    const crumbs = await page.locator('.ws-breadcrumbs a').evaluateAll((all) => all.map((a) => a.getBoundingClientRect().toJSON() as DOMRect));
    const last = crumbs[crumbs.length - 1]!;
    expect(last.top - crumbs[0]!.top, 'las migas, en dos lineas').toBeGreaterThan(20);
    const border = Math.max(...crumbs.filter((c) => c.top < last.top - 5).map((c) => c.bottom));
    const lines = grid(0, Math.max(...crumbs.map((c) => c.right)) + 5, 5, border - 12, border + 12, 1);
    gaps = crumbs;
    check('la ficha de un proveedor, las dos lineas de migas', await tapChanges(page, lines), lines.length);
    gaps = [];
    // La ✕ de la tarjeta de una fila de la hoja: fuera de la tarjeta, el margen del dialogo (un
    // toque ahi cierra la hoja entera; con la zona hasta el borde de la tarjeta, Chromium se lo
    // daba a la ✕, y uno en lo redondeado de su esquina, a la hoja).
    await openInvoice(page, N.oost);
    const card = await openSheetRow(page, t.aurora.sheet.more);
    const inSheet = await corner(card.locator('.detail-close'));
    check('la ✕ de la tarjeta de una fila, en la hoja', await tapChanges(page, inSheet), inSheet.length);
    await expect(card).toBeVisible();
    expect(wrong).toEqual([]);
  });
});

