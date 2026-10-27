// La base de la app: la entrada, el marco con todas las areas, NL | EN, las pestanas (una
// fila abre su ficha; si ya esta abierta, se va a ella), que las pestanas se guardan al
// recargar y que salir borra el token. Captura de cada pantalla en los dos idiomas.
import type { Page } from '@playwright/test';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token } from './fixtures';

const NAV = [
  ['overview', 'Overzicht', 'Overview'],
  ['work-queue', 'Werklijst', 'Work queue'],
  ['exceptions', 'Uitzonderingen', 'Exceptions'],
  ['iban-checks', 'IBAN-controles', 'IBAN checks'],
  ['invoices-in', 'Inkomend', 'In'],
  ['invoices-out', 'Uitgaand', 'Out'],
  ['providers', 'Leveranciers', 'Providers'],
  ['clients', 'Klanten', 'Clients'],
  ['objects', 'Objecten', 'Objects'],
  ['purchase-orders', 'Inkooporders', 'Purchase orders'],
  ['cash-flow', 'Kasstroom', 'Cash flow'],
  ['vat', 'Btw', 'VAT'],
  ['import', 'Importeren', 'Import'],
  ['read-invoices', 'Facturen lezen', 'Read invoices'],
  ['settings', 'Instellingen', 'Settings'],
] as const;

test('la entrada, en neerlandes por defecto y en ingles', async ({ page, baseUrl, watch }) => {
  watch.expectHttpErrors(401);
  await page.goto(`${baseUrl}/app`);
  // La banda de datos de prueba la pone el servidor, por encima de la app.
  await expect(page.locator('#datos-de-prueba')).toContainText('TESTGEGEVENS · TEST DATA');
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'nl');
  await expect(page.getByText('Je persoonlijke code is een lange reeks tekens')).toBeVisible();
  await expectAccessible(page, 'entrada nl');
  await capture(page, 'nl-login');

  await page.getByRole('button', { name: 'English' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Log in' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await capture(page, 'en-login');

  // Ni <form> ni campo de contrasena: Edge no ofrece guardar el token en su gestor de
  // contrasenas. Los caracteres van tapados igual.
  await expect(page.locator('form')).toHaveCount(0);
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await expect(page.locator('#token')).toHaveAttribute('autocomplete', 'one-time-code');
  expect(await page.locator('#token').evaluate((el) => getComputedStyle(el).getPropertyValue('-webkit-text-security'))).toBe('disc');

  // Un token que no vale: lo dice, y el campo se vacia. Intro tambien entra.
  await page.locator('#token').fill('bms_no-vale');
  await page.locator('#token').press('Enter');
  await expect(page.getByRole('alert').filter({ hasText: 'This code is not valid' })).toBeVisible();
  await page.locator('#token').fill('bms_no-vale');
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'This code is not valid' })).toBeVisible();
  await expect(page.locator('#token')).toHaveValue('');
  await expectAccessible(page, 'entrada con error');
  await capture(page, 'en-login-error');
  // El aviso cambia de idioma con la app.
  await page.getByRole('button', { name: 'Nederlands' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Deze code is niet geldig' })).toBeVisible();
});

test('el marco con todas las areas, en los dos idiomas', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await expect(page.getByTestId('test-data-chip')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Accountmenu van Ana Demo' })).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Hoofdmenu' });
  // Insignias solo para lo que pide hacer algo: bloqueadas, excepciones, IBAN.
  await expect(nav.getByRole('button', { name: /Werklijst/ })).toContainText('geblokkeerd');

  for (const [lang, index] of [['nl', 1], ['en', 2]] as const) {
    // El de la cabecera (Instellingen lleva otro igual).
    if (lang === 'en') await page.getByRole('button', { name: 'English' }).first().click();
    const menu = page.getByRole('navigation', { name: lang === 'nl' ? 'Hoofdmenu' : 'Main menu' });
    for (const entry of NAV) {
      const [id] = entry;
      const label = entry[index];
      await menu.getByRole('button', { name: new RegExp(`^${label}\\b`) }).click();
      await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
      await expect(page.getByRole('tab', { selected: true })).toContainText(label);
      if (id === 'work-queue') await expect(page.getByRole('table')).toBeVisible();
      await expectAccessible(page, `${lang} ${id}`);
      await expectNoLeftovers(page, lang, `${lang} ${id}`);
      await capture(page, `${lang}-${id}`);
    }
  }
  await page.getByRole('button', { name: 'Nederlands' }).first().click();
});

test('una fila abre su ficha en una pestana, y otra vez la misma pestana', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const menu = page.getByRole('navigation', { name: 'Hoofdmenu' });
  await menu.getByRole('button', { name: /^Werklijst/ }).click();
  const first = page.getByRole('table').getByRole('row').nth(1).getByRole('button');
  // El boton de la fila lleva el numero (en mono) y la relacion debajo.
  const number = (await first.locator('.font-mono').textContent())!.trim();
  await first.click();
  await expect(page.getByRole('heading', { level: 1, name: `Factuur ${number}` })).toBeVisible();
  const tabs = page.getByRole('tab');
  await expect(tabs).toHaveCount(2);
  await expect(page.getByRole('tab', { selected: true })).toContainText(number);
  await expectAccessible(page, 'ficha de factura');
  await capture(page, 'nl-invoice');

  // Volver a la lista y abrir la misma fila: se va a su pestana, no se abre otra.
  await tabs.first().click();
  await page.getByRole('table').getByRole('row').nth(1).getByRole('button').click();
  await expect(tabs).toHaveCount(2);
  await expect(page.getByRole('tab', { selected: true })).toContainText(number);

  // Los detalles van plegados; se abren con el teclado.
  const details = page.getByRole('button', { name: /^Velden/ });
  await expect(details).toHaveAttribute('aria-expanded', 'false');
  await details.focus();
  await page.keyboard.press('Enter');
  await expect(details).toHaveAttribute('aria-expanded', 'true');
});

test('las pestanas vuelven al recargar; el token no', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const menu = page.getByRole('navigation', { name: 'Hoofdmenu' });
  // Abrir rapido una pestana nueva con Kasstroom y dejar otra en Btw.
  await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).click();
  await page.getByRole('menuitem', { name: 'Nieuw tabblad' }).click();
  await menu.getByRole('button', { name: /^Kasstroom/ }).click();
  await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).click();
  await page.getByRole('menuitem', { name: 'Nieuw tabblad' }).click();
  await menu.getByRole('button', { name: /^Btw/ }).click();
  const before = await page.getByRole('tab').allTextContents();
  expect(before.length).toBeGreaterThanOrEqual(3);
  await expect(page.getByRole('tab', { selected: true })).toContainText('Btw');
  // La barra lateral plegada tambien se guarda.
  await page.getByRole('button', { name: 'Zijbalk inklappen' }).click();
  await expect(page.getByRole('button', { name: 'Zijbalk uitklappen' })).toBeVisible();
  await capture(page, 'nl-sidebar-collapsed');

  await page.reload();
  // Recargar es empezar de nuevo: el token no estaba en ningun sitio del navegador.
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  const stored = await page.evaluate(() => ({
    local: JSON.stringify({ ...localStorage }),
    session: sessionStorage.length,
    cookie: document.cookie,
    url: location.href,
  }));
  expect(stored.local).not.toContain(token('ana'));
  expect(stored.local).not.toContain('bms_');
  expect(stored.session).toBe(0);
  expect(stored.cookie).toBe('');
  expect(stored.url).not.toContain(token('ana'));

  await login(page);
  expect(await page.getByRole('tab').allTextContents()).toEqual(before);
  await expect(page.getByRole('tab', { selected: true })).toContainText('Btw');
  await expect(page.getByRole('button', { name: 'Zijbalk uitklappen' })).toBeVisible();
  await page.getByRole('button', { name: 'Zijbalk uitklappen' }).click();

  // Otra persona en el mismo ordenador no ve las pestanas de Ana.
  await page.getByRole('button', { name: 'Accountmenu van Ana Demo' }).click();
  await page.getByRole('menuitem', { name: 'Uitloggen' }).click();
  await login(page, 'bram');
  await expect(page.getByRole('tab')).toHaveCount(1);
  await expect(page.getByRole('heading', { level: 1, name: 'Overzicht' })).toBeVisible();
});

test('salir vuelve a la entrada y olvida el token', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await page.getByRole('button', { name: 'Accountmenu van Ana Demo' }).click();
  await expect(page.getByRole('menu')).toContainText('Ingelogd als');
  await capture(page, 'nl-account-menu');
  await page.getByRole('menuitem', { name: 'Uitloggen' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Je bent uitgelogd.' })).toBeVisible();
  await expect(page.locator('#token')).toHaveValue('');
  const local = await page.evaluate(() => JSON.stringify({ ...localStorage }));
  expect(local).not.toContain(token('ana'));
});

test('el idioma es de cada persona', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  // Ana entra en neerlandes (el de la entrada) y ese queda como el suyo.
  await login(page, 'ana');
  await expect(page.getByRole('heading', { level: 1, name: 'Overzicht' })).toBeVisible();
  await page.getByRole('button', { name: 'Accountmenu van Ana Demo' }).click();
  await page.getByRole('menuitem', { name: 'Uitloggen' }).click();
  // Bram elige ingles; al recargar, la entrada sale en el ultimo idioma usado, y el suyo vuelve.
  await login(page, 'bram');
  await page.getByRole('button', { name: 'English' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Log in' })).toBeVisible();
  await login(page, 'bram');
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible();
  await page.getByRole('button', { name: 'Account menu for Bram Demo' }).click();
  await page.getByRole('menuitem', { name: 'Log out' }).click();
  // Ana vuelve a tener el suyo.
  await login(page, 'ana');
  await expect(page.getByRole('heading', { level: 1, name: 'Overzicht' })).toBeVisible();
});

test('una sesion que caduca vuelve a la entrada con el aviso', async ({ page, baseUrl, watch }) => {
  watch.expectHttpErrors(401);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // El Overzicht tambien lee las facturas: que termine antes de que el servidor "retire"
  // el token, para que el 401 llegue al abrir la Werklijst.
  await expect(page.getByRole('heading', { level: 2, name: 'Als eerste' })).toBeVisible();
  // El servidor dice 401 (como si el token se hubiera retirado): la app sale sola.
  await page.route('**/api/v2/facturas', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"x"}' })
  );
  await page.getByRole('navigation', { name: 'Hoofdmenu' }).getByRole('button', { name: /^Werklijst/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Je sessie is beëindigd' })).toBeVisible();
});

test('a 1024 px se usa igual, y en estrecho el menu va en una hoja', async ({ page, baseUrl }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const menu = page.getByRole('navigation', { name: 'Hoofdmenu' });
  await menu.getByRole('button', { name: /^Werklijst/ }).click();
  await expect(page.getByRole('table')).toBeVisible();
  // A 768 px de alto se ven todos los apartados de la barra lateral, Instellingen el ultimo.
  for (const label of ['Facturen lezen', 'Instellingen']) {
    const box = await menu.getByRole('button', { name: new RegExp(`^${label}`) }).boundingBox();
    expect(box, label).not.toBeNull();
    expect(box!.y + box!.height, label).toBeLessThanOrEqual(768);
  }
  await capture(page, 'nl-work-queue-1024');

  // Con una ficha abierta, + y ... no se tapan; con muchas pestanas, un fundido dice que hay
  // mas a un lado.
  await menu.getByRole('button', { name: /^Leveranciers/ }).click();
  await page.getByRole('table').getByRole('button').first().click();
  await expect(page.getByRole('tab')).toHaveCount(2);
  const plus = (await page.getByRole('button', { name: 'Nieuw tabblad' }).boundingBox())!;
  const more = (await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).boundingBox())!;
  expect(plus.x + plus.width, '+ antes de ...').toBeLessThanOrEqual(more.x);
  for (const label of ['Klanten', 'Objecten', 'Inkooporders', 'Kasstroom', 'Btw', 'Importeren']) {
    await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).click();
    await page.getByRole('menuitem', { name: 'Nieuw tabblad' }).click();
    await menu.getByRole('button', { name: new RegExp(`^${label}`) }).click();
    await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
  }
  await expect(page.getByTestId('tabs-fade-left')).toBeVisible();
  const plusAfter = (await page.getByRole('button', { name: 'Nieuw tabblad' }).boundingBox())!;
  const moreAfter = (await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).boundingBox())!;
  expect(plusAfter.x + plusAfter.width).toBeLessThanOrEqual(moreAfter.x);
  // La pestana activa se ve entera.
  const strip = (await page.getByRole('tablist').locator('xpath=..').boundingBox())!;
  const active = (await page.getByRole('tab', { selected: true }).boundingBox())!;
  expect(active.x).toBeGreaterThanOrEqual(strip.x - 1);
  // (las curvas de la pestana de Chrome salen 1-2 px del borde: no tapan nada)
  expect(active.x + active.width).toBeLessThanOrEqual(strip.x + strip.width + 4);
  await capture(page, 'nl-tabs-1024');
  await expectAccessible(page, '1024 con muchas pestanas');
  await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).click();
  await page.getByRole('menuitem', { name: 'Alle tabbladen sluiten' }).click();

  await page.setViewportSize({ width: 700, height: 900 });
  await page.getByRole('button', { name: 'Menu openen' }).click();
  const sheet = page.getByRole('dialog', { name: 'Navigatie' });
  await expect(sheet).toBeVisible();
  await capture(page, 'nl-mobile-menu');
  await sheet.getByRole('button', { name: /^Klanten/ }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByRole('heading', { level: 1, name: 'Klanten' })).toBeVisible();
  await expectAccessible(page, 'estrecho');
});

test('el teclado llega a todo y se ve donde esta', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // La pestana activa: con el teclado se cierra (Supr) y se pasa de una a otra (flechas).
  await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).click();
  await page.getByRole('menuitem', { name: 'Nieuw tabblad' }).click();
  await expect(page.getByRole('tab')).toHaveCount(2);
  await page.getByRole('tab', { selected: true }).focus();
  await page.keyboard.press('Delete');
  await expect(page.getByRole('tab')).toHaveCount(1);
  // El foco se ve: un contorno de 2 px en el elemento enfocado.
  await page.getByRole('button', { name: 'Nederlands' }).focus();
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle);
  expect(outline).not.toBe('none');
});

/**
 * Lo que se sale de la ventana por los lados: cada elemento visible que pasa del borde y no
 * esta dentro de algo que se desplaza en horizontal (la tira de pestanas, una tabla en su
 * caja). Lo que recorta un overflow hidden no cuenta como desplazable: tambien es estar fuera.
 */
async function outsideTheWindow(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const width = window.innerWidth;
    const out: string[] = [];
    if (document.documentElement.scrollWidth > width) out.push(`html ${document.documentElement.scrollWidth}`);
    if (document.body.scrollWidth > width) out.push(`body ${document.body.scrollWidth}`);
    const scrolls = (el: Element) => {
      const x = getComputedStyle(el).overflowX;
      return x === 'auto' || x === 'scroll';
    };
    for (const el of Array.from(document.body.querySelectorAll('*'))) {
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

/** El titulo de la ficha de una factura ("Factuur KT-202608"). */
function invoiceTitle(number: string, word = 'Factuur'): RegExp {
  return new RegExp(`^${word} ${number.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`);
}

// En el movil (de 360 a 430 px): la tira de pestanas se ve y se toca. Antes la cabecera (el
// menu, las pestanas, + y ..., la marca de prueba, el idioma y la persona) iba en una fila y
// a la tira le quedaba una rendija: las pestanas no se veian ni se podian tocar.
for (const size of [
  { width: 400, height: 860 },
  { width: 360, height: 740 },
] as const) {
  test.describe(`${size.width} × ${size.height}`, () => {
    test.use({ viewport: size, hasTouch: true, isMobile: true });

    test(`en el movil (${size.width} px) las pestanas se ven y se tocan`, async ({ page, baseUrl }) => {
      await page.goto(`${baseUrl}/app`);
      await login(page);
      expect(await outsideTheWindow(page), 'fuera de la ventana').toEqual([]);

      await page.getByRole('button', { name: 'Menu openen' }).tap();
      await page.getByRole('dialog', { name: 'Navigatie' }).getByRole('button', { name: /^Werklijst/ }).tap();
      await expect(page.getByRole('heading', { level: 1, name: 'Werklijst' })).toBeVisible();

      // Dos facturas distintas, cada una en su pestana.
      const rows = page.getByRole('table').getByRole('row');
      const numbers: string[] = [];
      for (let i = 1; numbers.length < 2; i += 1) {
        const n = (await rows.nth(i).getByRole('button').locator('.font-mono').textContent())!.trim();
        if (!numbers.includes(n)) numbers.push(n);
      }
      const tabs = page.getByRole('tab');
      const tabOf = (n: string) => tabs.filter({ hasText: n });
      for (const n of numbers) {
        if (n === numbers[1]) await tabs.first().tap();
        await expect(page.getByRole('heading', { level: 1, name: 'Werklijst' })).toBeVisible();
        await page.getByRole('table').getByRole('button', { name: `Factuur ${n} openen` }).first().tap();
        await expect(page.getByRole('heading', { level: 1, name: invoiceTitle(n) })).toBeVisible();
      }
      await expect(tabs).toHaveCount(3);

      const strip = page.getByRole('tablist').locator('xpath=..');
      // La pestana activa entera dentro de la tira, que deja ver mas de una.
      // (la tira se desplaza con suavidad hasta la activa: se espera a que llegue)
      const activeInStrip = async () => {
        await settled(page);
        await expect
          .poll(async () => {
            const s = (await strip.boundingBox())!;
            const a = (await page.getByRole('tab', { selected: true }).boundingBox())!;
            if (a.x < s.x - 1) return `empieza fuera: ${a.x} < ${s.x}`;
            // (las curvas de la pestana de Chrome salen unos px del borde: no tapan nada)
            if (a.x + a.width > s.x + s.width + 4) return `acaba fuera: ${a.x + a.width} > ${s.x + s.width}`;
            return 'dentro';
          }, { message: 'la pestana activa, entera dentro de la tira' })
          .toBe('dentro');
        return (await strip.boundingBox())!;
      };
      const s = await activeInStrip();
      expect(s.width, 'la tira deja sitio para dos pestanas').toBeGreaterThanOrEqual(2 * 96);
      expect(s.x + s.width).toBeLessThanOrEqual(size.width);
      for (const tab of await tabs.all()) {
        const box = (await tab.boundingBox())!;
        expect(box.width, 'una pestana no es una rendija').toBeGreaterThanOrEqual(96);
        // (WCAG 2.5.8 pide 24 px; la del dueno mide unos 40)
        expect(box.height, 'una pestana se puede tocar').toBeGreaterThanOrEqual(36);
      }
      // + y ... fuera de la tira, despues de ella y dentro de la ventana.
      const plus = (await page.getByRole('button', { name: 'Nieuw tabblad' }).boundingBox())!;
      const more = (await page.getByRole('button', { name: 'Meer opties voor tabbladen' }).boundingBox())!;
      expect(plus.x).toBeGreaterThanOrEqual(s.x + s.width - 1);
      expect(plus.x + plus.width).toBeLessThanOrEqual(more.x);
      expect(more.x + more.width).toBeLessThanOrEqual(size.width);
      expect(await outsideTheWindow(page), 'fuera de la ventana').toEqual([]);
      await capture(page, `nl-mobile-tabs-${size.width}`);

      // De una a otra tocando la pestana; la que se toca se ve entera.
      for (const n of [numbers[0]!, numbers[1]!, numbers[0]!]) {
        const tab = tabOf(n);
        await expect(tab).toBeVisible();
        await tab.tap();
        await expect(tab).toHaveAttribute('aria-selected', 'true');
        await expect(page.getByRole('heading', { level: 1, name: invoiceTitle(n) })).toBeVisible();
        await activeInStrip();
      }
      // Tocar una pestana que no es la activa la abre, nunca la cierra (en el movil no hay
      // raton que ensene antes la x).
      await tabs.first().tap();
      await expect(tabs).toHaveCount(3);
      await expect(page.getByRole('heading', { level: 1, name: 'Werklijst' })).toBeVisible();
      await activeInStrip();
      expect(await outsideTheWindow(page), 'fuera de la ventana').toEqual([]);
      await expectAccessible(page, `movil ${size.width}`);
      await capture(page, `nl-mobile-tabs-${size.width}-first`);

      await page.getByRole('button', { name: 'English' }).tap();
      await tabOf(numbers[1]!).tap();
      await expect(page.getByRole('heading', { level: 1, name: invoiceTitle(numbers[1]!, 'Invoice') })).toBeVisible();
      await activeInStrip();
      expect(await outsideTheWindow(page), 'fuera de la ventana').toEqual([]);
      await capture(page, `en-mobile-tabs-${size.width}`);
      await page.getByRole('button', { name: 'Nederlands' }).tap();
    });
  });
}
