// Lo que se pulsa, medido como lo pulsa una persona (peticion del dueno del 02-11-2026: «Sí,
// amplía también esos controles»; WCAG 2.2, 2.5.8): cada elemento que se pulsa (un boton, un
// enlace, un campo, un rol de control o algo con tabindex) y la zona en que un clic le llega de
// verdad, medida con document.elementFromPoint y no con su caja: una capa transparente la agranda
// (bms.css, «Las zonas tactiles») y algo encima la recorta. Lo que esta fuera de la vista se trae
// al centro (scrollIntoView) y luego se deja como estaba; las bandas del servidor no cuentan.
import { expect, type Locator, type Page } from '@playwright/test';
import { login, settled } from './fixtures';
import {
  TEXTS,
  ask,
  closeSheet,
  detail,
  entryLabel,
  openCard,
  openDocuments,
  openEntry,
  openFolder,
  openGroup,
  openInvoice,
  openSettingsRow,
  openSheetRow,
  panel,
  panelRow,
  panelTitle,
  profileRow,
  sheetDialog,
  toHome,
  treeItem,
  unfold,
  wheel,
} from './nav';
import { ZONES, withoutHitArea, type Box } from './zona-tactil';

/** Lo que se pulsa (la lista de la peticion, y los nodos del arbol de Documentos). */
export const INTERACTIVE =
  'button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=option], [role=menuitem], [role=switch], [role=checkbox], [role=radio], [role=link], [role=treeitem], [tabindex]:not([tabindex^="-"])';

export interface Target {
  /** Que es: etiqueta, clases y lo que dice (o su aria-label). */
  what: string;
  /** Su caja, lo que se ve (ancho × alto). */
  box: { width: number; height: number };
  /** La zona en que un clic le llega: la fila y la columna de puntos mas largas (px, al pixel). */
  hit: { width: number; height: number };
  /** Si tiene zona tactil (bms.css), cual. */
  zone?: string;
  /** Tapado en parte por una lista abierta (un calendario, un desplegable) de la que no es. */
  underPopover?: true;
}

/**
 * Cada elemento que se pulsa en la pantalla de ahora y su zona medida. Solo cuenta lo que se
 * puede pulsar en algun punto (lo tapado entero, lo de una pantalla que se va y lo inerte, no).
 * Con caja de 24 × 24 o mas, basta con que los puntos de un cuadrado de 24 en su centro sean
 * suyos; si no, se mide la zona entera (32 px alrededor de la caja, punto a punto).
 */
export async function measureTargets(page: Page): Promise<Target[]> {
  return page.evaluate(({ selector, zones }) => {
    // Las bandas del servidor (datos de prueba, aislamiento; .bms-banda, pegadas arriba) no son de
    // la app: mientras se mide, no tapan (siguen ocupando su sitio).
    const bands = new CSSStyleSheet();
    bands.replaceSync('.bms-banda{visibility:hidden!important}');
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, bands];
    const out: Target[] = [];
    const vw = innerWidth;
    const vh = innerHeight;
    const describe = (el: Element) => {
      const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 3).join('.') : '';
      const label = el.getAttribute('aria-label') ?? (el as HTMLElement).innerText ?? (el as HTMLInputElement).value ?? '';
      return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''} «${label.replace(/\s+/g, ' ').trim().slice(0, 40)}»`;
    };
    // Lo que un clic en (x, y) pulsa: el control mas cercano al elemento de debajo (o el campo de
    // la etiqueta que se pulsa).
    const targetAt = (x: number, y: number): Element | null => {
      const hit = document.elementFromPoint(x, y);
      if (!hit) return null;
      const label = hit.closest('label');
      if (label?.control && !hit.closest(selector)) return label.control;
      return hit.closest(selector);
    };
    // Lo que se desplaza por encima del elemento, para dejarlo como estaba.
    const scrollers = (el: Element) => {
      const list: [Element, number, number][] = [];
      for (let p = el.parentElement; p; p = p.parentElement) list.push([p, p.scrollTop, p.scrollLeft]);
      list.push([document.scrollingElement!, document.scrollingElement!.scrollTop, document.scrollingElement!.scrollLeft]);
      return list;
    };
    // Recortado por la ventana (con 22 px alrededor, lo que puede crecer su zona) o por lo que lo
    // contiene con overflow.
    const clipped = (el: Element, r: DOMRect) => {
      if (r.left < 22 || r.top < 22 || r.right > vw - 22 || r.bottom > vh - 22) return true;
      for (let p = el.parentElement; p; p = p.parentElement) {
        const o = getComputedStyle(p);
        if (o.overflowX === 'visible' && o.overflowY === 'visible') continue;
        const c = p.getBoundingClientRect();
        if (r.left < c.left - 0.5 || r.top < c.top - 0.5 || r.right > c.right + 0.5 || r.bottom > c.bottom + 0.5) return true;
      }
      return false;
    };
    for (const el of Array.from(document.querySelectorAll(selector))) {
      if (el.closest('[inert], [aria-hidden=true]')) continue;
      if ((el as HTMLButtonElement).disabled || el.getAttribute('aria-disabled') === 'true') continue;
      if (!el.checkVisibility({ visibilityProperty: true })) continue;
      let r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      let restore: [Element, number, number][] | null = null;
      if (clipped(el, r)) {
        restore = scrollers(el);
        el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
        r = el.getBoundingClientRect();
      }
      const ours = (x: number, y: number) => targetAt(x, y) === el;
      let hit = { width: 0, height: 0 };
      // Un cuadrado de 24 en el centro, entero suyo: basta.
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      let square = r.width >= 24 && r.height >= 24;
      if (square) {
        for (let i = -11.5; i <= 11.5 && square; i += 5.75) for (let j = -11.5; j <= 11.5 && square; j += 5.75) if (!ours(cx + i, cy + j)) square = false;
      }
      if (square) hit = { width: r.width, height: r.height };
      else {
        // La zona entera: las filas y las columnas de puntos, al pixel (en su centro).
        const x0 = Math.max(0, Math.floor(r.left - 32));
        const x1 = Math.min(vw - 1, Math.ceil(r.right + 32));
        const y0 = Math.max(0, Math.floor(r.top - 32));
        const y1 = Math.min(vh - 1, Math.ceil(r.bottom + 32));
        const rowStep = Math.max(1, Math.ceil((y1 - y0) / 80));
        const colStep = Math.max(1, Math.ceil((x1 - x0) / 80));
        for (let y = y0; y <= y1; y += rowStep) {
          let run = 0;
          for (let x = x0; x <= x1; x += 1) {
            run = ours(x + 0.5, y + 0.5) ? run + 1 : 0;
            if (run > hit.width) hit.width = run;
          }
        }
        for (let x = x0; x <= x1; x += colStep) {
          let run = 0;
          for (let y = y0; y <= y1; y += 1) {
            run = ours(x + 0.5, y + 0.5) ? run + 1 : 0;
            if (run > hit.height) hit.height = run;
          }
        }
      }
      if (restore) for (const [p, top, left] of restore) (p.scrollTop = top), (p.scrollLeft = left);
      // Lo que no se pulsa en ningun punto no es un objetivo (tapado, o de una pantalla que se va).
      if (hit.width === 0 || hit.height === 0) continue;
      const zone = zones.find((z) => el.matches(z.selector))?.name;
      const under = Array.from(document.querySelectorAll('.ui-popover')).some((p) => {
        const q = p.getBoundingClientRect();
        return !p.contains(el) && q.left < r.right && q.right > r.left && q.top < r.bottom && q.bottom > r.top;
      });
      out.push({ what: describe(el), box: { width: Math.round(r.width * 100) / 100, height: Math.round(r.height * 100) / 100 }, hit, ...(zone ? { zone } : {}), ...(under ? { underPopover: true as const } : {}) });
    }
    document.adoptedStyleSheets = document.adoptedStyleSheets.filter((x) => x !== bands);
    return out;
  }, { selector: INTERACTIVE, zones: ZONES.map((z) => ({ name: z.name, selector: z.selector })) });
}

const HAVEN = 'Demo Havenbedrijf BV';
const JV = 'J. Voorbeeld Beveiliging (zzp)';

/** Abre la primera orden de una tarjeta, si tiene (sus botones, despues de «Abrir la factura» y
 *  «Descargar el original»): su formulario, sin mandar nada. */
async function openFirstOrder(card: Locator): Promise<boolean> {
  const t = TEXTS.nl;
  const skip = new Set([t.aurora.card.openInvoice, t.aurora.card.downloadOriginal]);
  const buttons = card.locator(':scope > div > button.primary, :scope > div > button.outline');
  for (let i = 0; i < (await buttons.count()); i += 1) {
    const b = buttons.nth(i);
    if (skip.has(((await b.textContent()) ?? '').trim()) || (await b.isDisabled())) continue;
    await b.click();
    if (await card.locator('.order-form').count()) return true;
  }
  return false;
}

/**
 * La gira de los estados principales (la de la peticion): la entrada con sus idiomas, el inicio,
 * la rueda, cada panel en reposo y en su segundo nivel con la tarjeta de una fila abierta (y su
 * orden, si tiene), Ajustes con el tema y el idioma, la conversacion con el resumen, la busqueda
 * con sus filtros, Documentos (la rejilla, el arbol, las fichas de un proveedor y de un cliente,
 * la hoja de una factura plegada, desplegada y con una tarjeta, un Object y una PO) y Procesar.
 * Empieza en la entrada (sin haber entrado) y en neerlandes; `visit` mide cada estado.
 */
export async function tour(page: Page, visit: (state: string) => Promise<void>): Promise<void> {
  const t = TEXTS.nl;
  await expect(page.locator('#token')).toBeVisible();
  await settled(page);
  await visit('L0 la entrada');
  await login(page);
  await visit('E0 el inicio');
  await page.getByRole('button', { name: t.aurora.home.navigate }).click();
  await expect(wheel(page)).toBeVisible();
  await settled(page);
  await visit('E1 la rueda');

  // Ajustes: en reposo, el idioma y el tema (su segundo nivel), la cuenta y el sistema (tarjetas).
  await openEntry(page, 'settings');
  await visit('E2-A Ajustes');
  for (const row of ['language', 'theme', 'account', 'system'] as const) {
    await openSettingsRow(page, row);
    await visit(`E2-A ${row}`);
  }

  // Los paneles: en reposo, cada vista de grupo y la tarjeta de su primera fila (y su orden).
  const groups: Record<'home' | 'receivables' | 'payables' | 'vat', string[]> = {
    home: [t.aurora.home.first, t.nav['work-queue'].label, t.nav.exceptions.label, t.aurora.home.iban, t.nav['cash-flow'].label],
    receivables: [t.aurora.money.proposals, t.aurora.money.unmatched, t.money.ageing.title],
    payables: [t.aurora.money.proposals, t.aurora.money.unmatched, t.aurora.money.week, t.money.week.held, t.money.ageing.title],
    vat: [t.aurora.vat.older],
  };
  for (const [entry, labels] of Object.entries(groups) as [keyof typeof groups, string[]][]) {
    await openEntry(page, entry);
    await visit(`E2 ${entry}`);
    const rest = panel(page).locator('.doc-list button.doc');
    for (const label of labels) {
      if (!(await panelRow(page, label).count())) continue;
      // Una fila de grupo abre su vista (o lleva a la busqueda, como la semana de Pagar).
      await panelRow(page, label).click();
      await expect.poll(async () => (await panel(page).count()) === 0 || (await panelTitle(page).textContent()) === label).toBe(true);
      await settled(page);
      await visit(`E2 ${entry} · ${label}`);
      if (!(await panel(page).count())) {
        await openEntry(page, entry);
        continue;
      }
      const rows = panel(page).locator('.doc-list button.doc');
      if (await rows.count()) {
        // Una fila abre su tarjeta o lleva a otro sitio (la busqueda, con la semana del flujo).
        await rows.first().click();
        await expect.poll(async () => (await detail(page).count()) > 0 || (await panel(page).count()) === 0).toBe(true);
        await settled(page);
        if (await panel(page).count()) {
          const card = detail(page);
          await visit(`E2 ${entry} · ${label} · tarjeta`);
          if (await openFirstOrder(card)) {
            await settled(page);
            await visit(`E2 ${entry} · ${label} · orden`);
          }
        } else await visit(`E2 ${entry} · ${label} · su fila`);
      }
      if (await panel(page).count()) {
        await page.keyboard.press('Escape');
        await settled(page);
      }
      if (!(await panel(page).count()) || (await panelTitle(page).textContent()) !== entryLabel(entry)) await openEntry(page, entry);
    }
    // Una fila del reposo que abre su tarjeta ahi mismo (IVA: el trimestre).
    if (entry === 'vat' && (await rest.count())) {
      await openCard(page, rest.first());
      await visit('E2 vat · tarjeta');
    }
  }
  // Importar, desde Cobrar.
  await openEntry(page, 'receivables');
  await panel(page).getByRole('button', { name: t.aurora.money.import }).click();
  await expect(panelTitle(page)).toHaveText(t.nav.import.label);
  await settled(page);
  await visit('E2-C importar');

  // La busqueda, y con sus filtros abiertos (Vervallen, desde Cobrar).
  await openEntry(page, 'search');
  await visit('E5 la busqueda');
  await page.locator('.filters-toggle').click();
  await expect(page.locator('#search-filters')).toBeVisible();
  await settled(page);
  await visit('E5 los filtros');
  // El calendario de la fecha y las listas (el tipo y la empresa), abiertos.
  await page.locator('#search-filters .filter-date-trigger').click();
  await expect(page.locator('.calendar-popover')).toBeVisible();
  await settled(page);
  await visit('E5 el calendario');
  await page.keyboard.press('Escape');
  await expect(page.locator('.calendar-popover')).toHaveCount(0);
  for (const [trigger, name] of [['.party-combobox button', 'la empresa'], ['.filter-combo-trigger', 'el tipo']] as const) {
    await page.locator(`#search-filters ${trigger}`).click();
    await expect(page.locator('.ui-popover')).toBeVisible();
    await settled(page);
    await visit(`E5 la lista de ${name}`);
    await page.keyboard.press('Escape');
    await expect(page.locator('.ui-popover')).toHaveCount(0);
  }
  // Con algo escrito (la ✕ de la caja).
  await page.getByRole('textbox').first().fill('Demo');
  await settled(page);
  await visit('E5 con algo escrito');
  await openEntry(page, 'receivables');
  await panelRow(page, t.aurora.money.overdue).click();
  await expect(page.locator('.active-filter-chips')).toBeVisible();
  await settled(page);
  await visit('E5-p con filtros');

  // La conversacion con el resumen (bento), y una respuesta con filas.
  await toHome(page);
  await ask(page, 'Geef me een overzicht');
  await expect(page.locator('.finance-bento')).toBeVisible();
  await settled(page);
  await visit('E4 la conversacion con el resumen');
  await toHome(page);
  await ask(page, 'DBO-2026-0417');
  await settled(page);
  await visit('E4 una respuesta con filas');

  // Documentos: la rejilla y el arbol, el arbol abierto, las fichas, las hojas.
  await openDocuments(page);
  await visit('E6 Documentos');
  await treeItem(page, t.documents.providers).first().click();
  await settled(page);
  await visit('E6 el arbol abierto');
  await openFolder(page, JV, 'provider');
  await visit('E6 la ficha de un proveedor');
  await profileRow(page, `${t.documents.types.factura_compra} JV-2026-001`).click();
  await expect(sheetDialog(page)).toBeVisible();
  await settled(page);
  await visit('E6 la hoja de una factura');
  await closeSheet(page);
  await openFolder(page, HAVEN, 'client');
  await visit('E6 la ficha de un cliente');
  await profileRow(page, `${t.records.object.label} HAVEN-NOORD`).click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('HAVEN-NOORD');
  await settled(page);
  await visit('E6 un Object');
  await closeSheet(page);
  await profileRow(page, `${t.records['purchase-order'].label} PO-DEMO-4501`).click();
  await expect(sheetDialog(page).getByRole('heading', { level: 2 })).toHaveText('PO-DEMO-4501');
  await settled(page);
  await visit('E6 una PO');
  await closeSheet(page);
  await openInvoice(page, 'DBO-2026-0417');
  await visit('E6-h plegada');
  await unfold(page);
  await settled(page);
  await visit('E6-h desplegada');
  const card = await openSheetRow(page, t.aurora.sheet.more);
  await visit('E6-h con una tarjeta');
  await card.getByRole('button', { name: t.notes.add, exact: true }).click();
  await expect(card.locator('.order-form')).toBeVisible();
  await settled(page);
  await visit('E6-o una orden en la hoja');
  await closeSheet(page);

  // Procesar.
  await openEntry(page, 'process');
  await visit('E7 Procesar');
  await toHome(page);
}

/** Lo que cambia al poner las zonas: los puntos cuyo clic va a otro sitio. */
export interface HitChanges {
  /** Cada cambio permitido, «lo de antes → la zona», con cuantos puntos. */
  taken: Record<string, number>;
  /** Lo que no deberia pasar: un punto de otro control (o de algo que hacia otra cosa) que ahora
   *  es de una zona, o uno que cambia sin ser de ninguna. */
  wrong: string[];
  /** Cuantos puntos se han mirado. */
  points: number;
}

/**
 * Compara, punto a punto, a donde va un clic con las zonas y sin las nuevas (como en 1cc96b0, con
 * la del control de la hoja plegada): la ventana entera cada 3 px y la zona de cada control (y 3 px alrededor) cada pixel.
 * Un punto solo puede pasar a ser de una zona si antes no era de nadie o era algo que hacia lo
 * mismo: el propio dialogo para la ✕ de una hoja (un clic en el margen del dialogo tambien la
 * cierra) y la pista del importe para sus tiradores (un clic en ella mueve el tirador mas
 * cercano; en la zona, se agarra sin saltar). Lo demas, en `wrong`.
 */
export async function hitChanges(page: Page): Promise<HitChanges> {
  // La hoja que deja lo de 1cc96b0 (sin las zonas nuevas), hecha y quitada.
  await withoutHitArea(page, true, 'nuevas');
  await withoutHitArea(page, false, 'nuevas');
  return page.evaluate(
    ({ selector, zones }) => {
      const sheet = (window as unknown as { __bmsSinZona: Record<string, CSSStyleSheet> }).__bmsSinZona['nuevas']!;
      const ids = new Map<Element, number>();
      const id = (e: Element) => (ids.has(e) ? ids.get(e)! : (ids.set(e, ids.size), ids.size - 1));
      const zoneOf = (e: Element) => zones.find((z) => e.matches(z.selector));
      const describe = (e: Element) => {
        const z = zoneOf(e);
        if (z) return z.name;
        const label = e.getAttribute('aria-label') ?? (e as HTMLElement).innerText ?? '';
        return `${e.tagName.toLowerCase()} «${label.replace(/\s+/g, ' ').trim().slice(0, 30)}»`;
      };
      const classify = (x: number, y: number): string => {
        const h = document.elementFromPoint(x, y);
        if (!h) return 'nada';
        const label = h.closest('label');
        const t = label?.control && !h.closest(selector) ? label.control : h.closest(selector);
        if (t) return `#${id(t)}`;
        if (h.matches('dialog')) return 'dialogo';
        if (h.closest('.amount-slider')) return 'pista';
        if (h.closest('.navigation')) return 'rueda';
        // Algo que no es un control pero cuyo clic hace algo: un manejador de React (onClick,
        // onMouseDown...) en el elemento o en uno de los de encima. No cuentan los de captura (los
        // de Radix, que solo apuntan que el clic fue dentro, y el de la rueda, que olvida la fila
        // apoyada) ni el del dialogo de una hoja, que solo cierra con el clic en el mismo dialogo
        // (document-workspace.tsx: e.target === e.currentTarget; eso es 'dialogo', arriba).
        for (let e: Element | null = h; e; e = e.parentElement) {
          if (e.matches('dialog.ws-dialog')) continue;
          const key = Object.keys(e).find((k) => k.startsWith('__reactProps$'));
          const props = key ? ((e as unknown as Record<string, Record<string, unknown>>)[key] ?? {}) : {};
          if (Object.keys(props).some((k) => /^on(Click|MouseDown|MouseUp|PointerDown|PointerUp|TouchStart|TouchEnd)$/.test(k) && props[k])) {
            const cls = typeof e.className === 'string' ? e.className.split(/\s+/)[0] : '';
            return `manejador:${e.tagName.toLowerCase()}${cls ? '.' + cls : ''}`;
          }
        }
        return 'nada';
      };
      const name = (c: string) =>
        c.startsWith('#')
          ? describe(Array.from(ids.keys())[Number(c.slice(1))]!)
          : c.startsWith('manejador:')
            ? `${c.slice(10)} (su clic hace algo)`
            : ({ nada: 'nada', dialogo: 'el dialogo (cierra la hoja)', pista: 'la pista del importe', rueda: 'la rueda' }[c] ?? c);
      // Los puntos: la ventana cada 3 px y cada zona (con 3 px alrededor) cada pixel.
      const pts: [number, number][] = [];
      for (let y = 1.5; y < innerHeight; y += 3) for (let x = 1.5; x < innerWidth; x += 3) pts.push([x, y]);
      for (const z of zones) {
        for (const el of Array.from(document.querySelectorAll(z.selector))) {
          const r = el.getBoundingClientRect();
          if (r.width === 0) continue;
          for (let y = Math.max(0, Math.floor(r.top - 28)); y < Math.min(innerHeight, r.bottom + 28); y += 1)
            for (let x = Math.max(0, Math.floor(r.left - 40)); x < Math.min(innerWidth, r.right + 40); x += 1) pts.push([x + 0.5, y + 0.5]);
        }
      }
      const after = pts.map(([x, y]) => classify(x, y));
      document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
      const before = pts.map(([x, y]) => classify(x, y));
      document.adoptedStyleSheets = document.adoptedStyleSheets.filter((s) => s !== sheet);
      const taken: Record<string, number> = {};
      const wrong = new Map<string, number>();
      for (let i = 0; i < pts.length; i += 1) {
        const [b, a] = [before[i]!, after[i]!];
        if (a === b) continue;
        const el = a.startsWith('#') ? Array.from(ids.keys())[Number(a.slice(1))]! : null;
        const zone = el ? zoneOf(el) : undefined;
        const ok = zone && (b === 'nada' || (b === 'dialogo' && zone.selector === '.ws-dialog-top button') || (b === 'pista' && zone.selector === '.amount-thumb'));
        const key = `${name(b)} → ${name(a)}`;
        if (ok) taken[key] = (taken[key] ?? 0) + 1;
        else wrong.set(key, (wrong.get(key) ?? 0) + 1);
      }
      return { taken, wrong: Array.from(wrong, ([k, n]) => `${k} (${n} puntos)`), points: pts.length };
    },
    { selector: INTERACTIVE, zones: ZONES.map((z) => ({ name: z.name, selector: z.selector })) }
  );
}

/**
 * Lo que cambia en las medidas de desplazamiento (scrollWidth, scrollHeight, clientWidth y
 * clientHeight) de la pagina y de todo lo que se desplaza o recorta, con las zonas y sin las
 * nuevas (como en 1cc96b0). Las tres medidas (con, sin y con otra vez) van en una sola tarea, sin
 * esperar entre ellas: nada de la app (React, un temporizador, un observador) puede cambiar la
 * pagina en medio, como el orbe de la busqueda, que se va al terminar de pensar y antes se colaba
 * entre dos medidas. Las transiciones, quitadas mientras tanto (si no, un relleno que cambia
 * empezaria en su valor de antes y las dos medidas saldrian iguales). Se compara elemento a
 * elemento; uno que no mide igual con las zonas las dos veces tambien se apunta.
 */
export async function scrollChanges(page: Page): Promise<string[]> {
  // La hoja que deja lo de 1cc96b0 (sin las zonas nuevas), hecha y quitada.
  await withoutHitArea(page, true, 'nuevas');
  await withoutHitArea(page, false, 'nuevas');
  return page.evaluate(() => {
    const sheet = (window as unknown as { __bmsSinZona: Record<string, CSSStyleSheet> }).__bmsSinZona['nuevas']!;
    const still = new CSSStyleSheet();
    still.replaceSync('*,*::before,*::after{transition:none!important}');
    const measure = (): Map<Element, string> => {
      const out = new Map<Element, string>();
      for (const el of [document.scrollingElement!, ...Array.from(document.querySelectorAll('*'))]) {
        const s = getComputedStyle(el);
        // Tambien lo de overflow: hidden (scrollIntoView lo desplaza).
        if (el !== document.scrollingElement && !/(auto|scroll|hidden)/.test(s.overflowX + s.overflowY)) continue;
        out.set(el, `${el.scrollWidth}×${el.scrollHeight} (${el.clientWidth}×${el.clientHeight})`);
      }
      return out;
    };
    const name = (el: Element) => {
      const cls = typeof el.className === 'string' ? el.className.split(/\s+/).slice(0, 2).join('.') : '';
      return `${el.tagName.toLowerCase()}.${cls}`;
    };
    // Una copia: adoptedStyleSheets es un arreglo vivo.
    const base = [...document.adoptedStyleSheets];
    document.adoptedStyleSheets = [...base, still];
    const withArea = measure();
    document.adoptedStyleSheets = [...base, still, sheet];
    const without = measure();
    document.adoptedStyleSheets = [...base, still];
    const again = measure();
    document.adoptedStyleSheets = base;
    const wrong: string[] = [];
    if (withArea.size !== without.size || withArea.size !== again.size) wrong.push(`lo que se desplaza: ${withArea.size} elementos con las zonas, ${without.size} sin ellas`);
    for (const [el, a] of withArea) {
      const [b, c] = [without.get(el), again.get(el)];
      if (b !== a) wrong.push(`${name(el)}: ${a} con las zonas, ${b ?? 'no se desplaza'} sin ellas`);
      else if (c !== a) wrong.push(`${name(el)}: ${a} y luego ${c ?? 'no se desplaza'}, con las zonas las dos veces`);
    }
    return wrong;
  });
}

/** La caja de un control (lo que se ve) y la de su zona tactil, segun su estilo: la caja misma si
 *  crece con relleno y margen negativo (lo que se ve es su contenido), su ::before si lo tiene, o
 *  las dos («Volver a Aurora» con el dedo a 650 px o menos: el relleno y un pixel de capa). */
export async function areaOf(control: Locator): Promise<{ box: Box; area: Box }> {
  return control.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const c = getComputedStyle(el);
    const grows = parseFloat(c.marginTop) < 0 || parseFloat(c.marginBottom) < 0;
    const [pt, pr, pb, pl] = [c.paddingTop, c.paddingRight, c.paddingBottom, c.paddingLeft].map(parseFloat) as [number, number, number, number];
    const own = { x: r.left, y: r.top, width: r.width, height: r.height };
    const content = { x: r.left + pl, y: r.top + pt, width: r.width - pl - pr, height: r.height - pt - pb };
    const s = getComputedStyle(el, '::before');
    // El buscador y «Abrir la ficha»: sin ::before (antes no tenian relleno).
    if (s.content === 'none' || s.position !== 'absolute') return { box: content, area: own };
    const x = r.left + el.clientLeft + parseFloat(s.left);
    const y = r.top + el.clientTop + parseFloat(s.top);
    const before = { x, y, width: parseFloat(s.width), height: parseFloat(s.height) };
    if (!grows) return { box: own, area: before };
    const [x0, y0] = [Math.min(own.x, before.x), Math.min(own.y, before.y)];
    const [x1, y1] = [Math.max(own.x + own.width, before.x + before.width), Math.max(own.y + own.height, before.y + before.height)];
    return { box: content, area: { x: x0, y: y0, width: x1 - x0, height: y1 - y0 } };
  });
}

/** Los estados donde estan los controles con zona (bms.css): una gira corta, desde la entrada. */
export async function zoneTour(page: Page, visit: (state: string) => Promise<void>): Promise<void> {
  const t = TEXTS.nl;
  await expect(page.locator('#token')).toBeVisible();
  await settled(page);
  await visit('la entrada');
  await login(page);
  await openEntry(page, 'settings');
  await visit('Ajustes');
  await openEntry(page, 'home');
  await openGroup(page, t.aurora.home.first);
  await openCard(page, panel(page).locator('.doc-list button.doc').first());
  await visit('la tarjeta de una fila de Inicio');
  await openEntry(page, 'search');
  await page.locator('.filters-toggle').click();
  await expect(page.locator('#search-filters')).toBeVisible();
  await settled(page);
  await visit('los filtros de la busqueda');
  await page.locator('#search-filters .party-combobox button').click();
  await expect(page.locator('.ui-popover')).toBeVisible();
  await settled(page);
  await visit('la lista de las empresas');
  await page.keyboard.press('Escape');
  await openEntry(page, 'receivables');
  await panelRow(page, t.aurora.money.overdue).click();
  await expect(page.locator('.active-filter-chips')).toBeVisible();
  await settled(page);
  await visit('la busqueda con filtros');
  await toHome(page);
  await ask(page, 'Geef me een overzicht');
  await expect(page.locator('.finance-bento')).toBeVisible();
  await settled(page);
  await visit('la conversacion');
  await openDocuments(page);
  await visit('Documentos');
  await openFolder(page, JV, 'provider');
  await visit('la ficha de un proveedor');
  await profileRow(page, `${t.documents.types.factura_compra} JV-2026-001`).click();
  await expect(sheetDialog(page)).toBeVisible();
  await settled(page);
  await visit('la hoja de una factura');
  await closeSheet(page);
  await openInvoice(page, 'DBO-2026-0417');
  await openSheetRow(page, t.aurora.sheet.more);
  await visit('la tarjeta de una fila de la hoja');
  await closeSheet(page);
  await openEntry(page, 'process');
  await visit('Procesar');
  await toHome(page);
}
