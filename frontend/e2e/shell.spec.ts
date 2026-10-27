// La base de la app (paso 16): la entrada; el inicio con la rueda de Aurora (las seis entradas a
// la vista, un clic abre cualquiera, la rueda del raton, las flechas, el dedo, Tab e Intro, sin
// tapar el saludo ni la caja); las seis entradas en pequeno en las demas pantallas; las fichas
// dentro de su seccion con migas y "Volver"; Ctrl+K; el menu del nombre (Ajustes, idioma, tema y
// Salir); que nada se guarda de las pestanas ni del token. Captura de cada pantalla en los tres
// idiomas (los dos temas, en themes.spec.ts).
import type { Locator, Page } from '@playwright/test';
import { SECTION_IDS, SECTION_VIEWS, VIEW_IDS } from '../src/screens/sections';
import { capture, expect, expectAccessible, expectNoLeftovers, login, settled, test, token } from './fixtures';
import {
  TEXTS,
  back,
  crumbs,
  go,
  mainMenu,
  openSection,
  readBadge,
  sectionButton,
  sectionMenu,
  setLang,
  signOut,
  viewHeading,
} from './nav';

/** La caja de una cosa en la pagina. */
async function box(locator: Locator) {
  const b = await locator.boundingBox();
  expect(b, 'se ve').not.toBeNull();
  return b!;
}

/** Que dos cajas no se pisan. */
function apart(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }) {
  return a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y;
}

/** La entrada de la rueda que esta en el centro (la activa). */
async function activeWheelEntry(page: Page): Promise<string> {
  return ((await page.locator('[data-wheel-entry][data-distance="0"]').textContent()) ?? '').trim();
}

test('la entrada, en neerlandes por defecto, en ingles y en castellano', async ({ page, baseUrl, watch }) => {
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
  await page.getByRole('button', { name: 'Español' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Entrar' })).toBeVisible();
  await expectNoLeftovers(page, 'es', 'entrada es');
  await capture(page, 'es-login');
  await page.getByRole('button', { name: 'English' }).click();

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

test('el inicio: el saludo con el nombre, la rueda con las seis entradas sin tapar nada y la caja', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await expect(page.getByTestId('test-data-chip')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Accountmenu van Ana Demo' })).toBeVisible();
  // El nombre de quien entro (/api/v2/yo), no el "Alberto" del prototipo.
  await expect(page.getByRole('heading', { level: 1, name: 'Welkom, Ana' })).toBeVisible();
  const wheel = mainMenu(page);
  const entries = wheel.getByRole('button');
  await expect(entries).toHaveCount(6);
  expect(await entries.allTextContents()).toEqual(SECTION_IDS.map((id) => TEXTS.nl.areas[id].label));
  // La entrada del inicio dice que es donde se esta; la rueda dice como se usa.
  await expect(sectionButton(page, 'home')).toHaveAttribute('aria-current', 'page');
  await expect(wheel).toHaveAccessibleDescription(TEXTS.nl.shell.wheel);
  // Las seis, enteras en la ventana, sin pisar el saludo ni la caja.
  const greeting = await box(page.getByRole('heading', { level: 1 }));
  const ask = await box(page.getByRole('textbox', { name: TEXTS.nl.ask.label }));
  for (const entry of await entries.all()) {
    const b = await box(entry);
    expect(b.y).toBeGreaterThanOrEqual(0);
    expect(b.y + b.height).toBeLessThanOrEqual(900);
    expect(apart(b, greeting), 'no pisa el saludo').toBe(true);
    expect(apart(b, ask), 'no pisa la caja').toBe(true);
    expect(await entry.evaluate((el) => getComputedStyle(el).opacity)).toBe('1');
  }
  // Las cuatro tarjetas a la vista sin desplazar, a 1440 × 900.
  await expect(page.getByTestId('summary-card')).toHaveCount(4);
  const lastCard = await box(page.getByTestId('summary-card').last());
  expect(lastCard.y + lastCard.height).toBeLessThanOrEqual(900);
  // Lo que dice la caja: que todavia no contesta preguntas.
  await expect(page.getByText(TEXTS.nl.ask.notYet)).toBeVisible();
  await expectAccessible(page, 'inicio nl');
  await expectNoLeftovers(page, 'nl', 'inicio nl');
  await capture(page, 'nl-home');
});

test('la rueda: un clic abre cualquier entrada a la primera; la rueda del raton y las flechas giran', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // Un clic normal en una entrada que NO es la del centro la abre (en el prototipo solo la
  // centraba y el clic se perdia).
  expect(await activeWheelEntry(page)).toBe('Start');
  await sectionButton(page, 'vat').click();
  await expect(viewHeading(page, 'vat')).toBeVisible();
  // La marca de arriba vuelve al inicio.
  await page.getByRole('button', { name: TEXTS.nl.shell.home }).click();
  await expect(viewHeading(page, 'home')).toBeVisible();
  for (const section of SECTION_IDS.filter((s) => s !== 'home')) {
    await sectionButton(page, section).click();
    await expect(viewHeading(page, SECTION_VIEWS[section][0]!)).toBeVisible();
    await page.getByRole('button', { name: TEXTS.nl.shell.home }).click();
    await expect(viewHeading(page, 'home')).toBeVisible();
  }

  // La rueda del raton gira (un paso por gesto) y la pagina no se desplaza mientras tanto.
  const list = mainMenu(page).getByRole('list');
  const centre = await box(list);
  await page.mouse.move(centre.x + centre.width / 2, centre.y + centre.height / 2);
  await page.mouse.wheel(0, 120);
  await expect.poll(() => activeWheelEntry(page)).toBe('Te ontvangen');
  await page.waitForTimeout(300);
  await page.mouse.wheel(0, 120);
  await expect.poll(() => activeWheelEntry(page)).toBe('Te betalen');
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await capture(page, 'nl-home-wheel-turned');
  await page.waitForTimeout(300);
  await page.mouse.wheel(0, -120);
  await expect.poll(() => activeWheelEntry(page)).toBe('Te ontvangen');

  // Tab llega a las entradas (gira la rueda hasta ella), las flechas mueven, Intro abre; el
  // foco se ve.
  await sectionButton(page, 'home').focus();
  expect(await activeWheelEntry(page)).toBe('Start');
  await page.keyboard.press('Tab');
  await expect(sectionButton(page, 'receivables')).toBeFocused();
  expect(await activeWheelEntry(page)).toBe('Te ontvangen');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  await expect(sectionButton(page, 'documents')).toBeFocused();
  expect(await activeWheelEntry(page)).toBe('Documenten');
  expect(await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle)).not.toBe('none');
  await page.keyboard.press('ArrowUp');
  await expect(sectionButton(page, 'payables')).toBeFocused();
  // De la ultima a la primera, como una rueda.
  await page.keyboard.press('End');
  await expect(sectionButton(page, 'vat')).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(sectionButton(page, 'home')).toBeFocused();
  await page.keyboard.press('ArrowUp');
  await expect(sectionButton(page, 'vat')).toBeFocused();
  await capture(page, 'nl-home-wheel-focus');
  await page.keyboard.press('Enter');
  await expect(viewHeading(page, 'vat')).toBeVisible();
  // Despues de cambiar de sitio, el foco va al contenido (no se queda en un boton que ya no esta).
  await expect(page.locator('#contenido')).toBeFocused();
});

test('con "menos movimiento" la rueda gira sin animacion y el orbe no se mueve', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const entry = sectionButton(page, 'payables');
  // Sin transicion (la regla general de "menos movimiento" deja 0.01 ms: nada que se vea).
  const instant = (el: Element) => getComputedStyle(el).transitionDuration.split(',').every((d) => parseFloat(d) < 0.001);
  expect(await entry.evaluate(instant)).toBe(true);
  expect(await entry.locator('.wheel-label').evaluate(instant)).toBe(true);
  await entry.focus();
  expect(await activeWheelEntry(page)).toBe('Te betalen');
  expect(await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running').length)).toBe(0);
  await expect(page.locator('[data-orb]').first()).toHaveAttribute('data-moving', 'false');
});

test('las seis entradas siguen a un clic en todas las pantallas, y cada vista de cada seccion, en los tres idiomas', async ({
  page,
  baseUrl,
}) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // Insignias solo para lo que pide hacer algo: bloqueadas, excepciones, IBAN.
  await go(page, 'work-queue');
  await expect(sectionMenu(page, 'home').getByRole('button', { name: /^Werklijst/ })).toContainText('geblokkeerd');
  await expect.poll(() => readBadge(page, 'exceptions')).toBeGreaterThan(0);
  await go(page, 'invoices-in');
  await expect.poll(() => readBadge(page, 'iban-checks')).toBeGreaterThan(0);

  for (const lang of ['nl', 'en', 'es'] as const) {
    await setLang(page, lang);
    for (const view of VIEW_IDS) {
      await go(page, view, lang);
      if (view !== 'home') {
        // La entrada de la seccion, marcada; las seis, a un clic.
        await expect(mainMenu(page, lang).getByRole('button')).toHaveCount(6);
      }
      if (view === 'work-queue') await expect(page.getByRole('table')).toBeVisible();
      await expectAccessible(page, `${lang} ${view}`);
      await expectNoLeftovers(page, lang, `${lang} ${view}`);
      await capture(page, `${lang}-${view}`);
    }
  }
  await setLang(page, 'nl');
});

test('una fila abre su ficha dentro de su seccion, con migas y Volver; la lista sigue como estaba', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'work-queue');
  await page.getByRole('group', { name: 'Toon' }).getByRole('button', { name: /^Urgent/ }).click();
  const first = page.getByRole('table').getByRole('row').nth(1).getByRole('button');
  const number = (await first.locator('.font-mono').textContent())!.trim();
  await first.click();
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(`${number.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) })).toBeVisible();
  // Donde se esta: Start › Werklijst › el numero; la entrada Start sigue marcada.
  expect(await crumbs(page)).toEqual(['Start', 'Werklijst', number]);
  await expect(sectionButton(page, 'home')).toHaveAttribute('aria-current', 'page');
  await expectAccessible(page, 'ficha de factura');
  await capture(page, 'nl-invoice');

  // Los detalles van plegados; se abren con el teclado.
  const details = page.getByRole('button', { name: /^Velden/ });
  await expect(details).toHaveAttribute('aria-expanded', 'false');
  await details.focus();
  await page.keyboard.press('Enter');
  await expect(details).toHaveAttribute('aria-expanded', 'true');

  // Volver: la lista con el mismo filtro.
  await back(page);
  await expect(viewHeading(page, 'work-queue')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Toon' }).getByRole('button', { name: /^Urgent/ })).toHaveAttribute('aria-pressed', 'true');

  // Una miga vuelve a ese paso: un cliente, su factura, y de vuelta al cliente por la miga.
  await go(page, 'clients');
  await page.getByRole('table').getByRole('button', { name: /Gemeente Demodorp/ }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: 'Gemeente Demodorp' })).toBeVisible();
  // La factura abierta sale en su seccion de la ficha y en la tabla: la primera vale.
  await page.getByRole('button', { name: 'Factuur VD26-306 openen' }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: /VD26-306$/ })).toBeVisible();
  expect(await crumbs(page)).toEqual(['Te ontvangen', 'Klanten', 'Gemeente Demodorp', 'VD26-306']);
  await page.getByRole('navigation', { name: TEXTS.nl.shell.breadcrumbs }).getByRole('button', { name: 'Gemeente Demodorp' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Gemeente Demodorp' })).toBeVisible();
  // Alt + flecha izquierda tambien vuelve, como en un navegador.
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(viewHeading(page, 'clients')).toBeVisible();
  // Otra entrada empieza un camino nuevo: sin migas.
  await openSection(page, 'vat');
  await expect(page.getByRole('navigation', { name: TEXTS.nl.shell.breadcrumbs })).toHaveCount(0);
});

test('Ctrl+K abre cualquier pantalla o ficha escribiendo', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'vat');
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog', { name: TEXTS.nl.palette.title });
  await expect(dialog).toBeVisible();
  const input = dialog.getByRole('combobox');
  await expect(input).toBeFocused();
  // Una pantalla por su nombre en cualquier idioma ("receivables" en neerlandes tambien).
  await input.fill('receivables');
  await expect(dialog.getByRole('option').first()).toContainText('Verkoopfacturen');
  await input.press('Enter');
  await expect(dialog).toBeHidden();
  await expect(viewHeading(page, 'invoices-out')).toBeVisible();
  // Una ficha: un cliente por su nombre, dentro de su seccion.
  await page.getByRole('button', { name: 'Zoeken' }).click();
  await input.fill('demodorp');
  await expect(dialog.getByRole('group', { name: 'Klanten' }).getByRole('option')).toContainText(['Gemeente Demodorp']);
  await expectAccessible(page, 'ctrl+k');
  await capture(page, 'nl-quick-open');
  await dialog.getByRole('group', { name: 'Klanten' }).getByRole('option').first().click();
  await expect(page.getByRole('heading', { level: 1, name: 'Gemeente Demodorp' })).toBeVisible();
  expect(await crumbs(page)).toEqual(['Te ontvangen', 'Klanten', 'Gemeente Demodorp']);
  // Una factura por su numero, con las flechas; Esc cierra sin hacer nada.
  await page.keyboard.press('Control+k');
  await input.fill('KT-2026');
  await expect(dialog.getByRole('group', { name: 'Facturen' }).getByRole('option').first()).toContainText('KT-202608');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await page.keyboard.press('Control+k');
  await input.fill('KT-202608');
  await expect(dialog.getByRole('group', { name: 'Facturen' }).getByRole('option').first()).toContainText('KT-202608');
  for (let i = 0; i < 6 && (await dialog.getByRole('option', { selected: true }).textContent())?.includes('KT-202608') !== true; i += 1) {
    await input.press('ArrowDown');
  }
  await input.press('Enter');
  await expect(page.getByRole('heading', { level: 1, name: /KT-202608$/ })).toBeVisible();
  expect(await crumbs(page)).toEqual(['Te betalen', 'Inkoopfacturen', 'KT-202608']);
  // Nada que encontrar: lo dice.
  await page.keyboard.press('Control+k');
  await input.fill('zzzz-niets');
  await expect(dialog).toContainText('Niets gevonden voor “zzzz-niets”.');
});

test('la caja del inicio busca y lo dice: todavia no contesta preguntas', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  const ask = page.getByRole('textbox', { name: TEXTS.nl.ask.label });
  await ask.fill('Gemeente Demodorp');
  await ask.press('Enter');
  const results = page.locator('section[aria-labelledby="ask-results"]');
  await expect(results).toContainText('Gevonden voor “Gemeente Demodorp”');
  await expect(results.getByRole('button', { name: /^Gemeente Demodorp/ }).first()).toBeVisible();
  await expect(results.getByRole('button', { name: /^VD26-306/ })).toBeVisible();
  await expectAccessible(page, 'caja con resultados');
  await capture(page, 'nl-home-ask');
  await results.getByRole('button', { name: /^VD26-306/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: /VD26-306$/ })).toBeVisible();
  expect(await crumbs(page)).toEqual(['Te ontvangen', 'Verkoopfacturen', 'VD26-306']);
  // Una pregunta: no se inventa una respuesta.
  await page.getByRole('button', { name: TEXTS.nl.shell.home }).click();
  await ask.fill('Hoeveel moeten klanten ons nog betalen?');
  await ask.press('Enter');
  await expect(results).toContainText('Niets gevonden voor “Hoeveel moeten klanten ons nog betalen?”.');
  await expect(page.getByText(TEXTS.nl.ask.notYet)).toBeVisible();
  await expect(results).not.toContainText('€');
  // Una pantalla por su nombre.
  await ask.fill('btw');
  await ask.press('Enter');
  await results.getByRole('button', { name: /^Btw/ }).first().click();
  await expect(viewHeading(page, 'vat')).toBeVisible();
});

test('al recargar se vuelve a entrar, en el inicio; el token y las pantallas no se guardan', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'vat');
  await page.getByRole('table').getByRole('button').first().click();
  await page.reload();
  // Recargar es empezar de nuevo: el token no estaba en ningun sitio del navegador.
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  const stored = await page.evaluate(() => ({
    local: JSON.stringify({ ...localStorage }),
    keys: Object.keys(localStorage),
    session: sessionStorage.length,
    cookie: document.cookie,
    url: location.href,
  }));
  expect(stored.local).not.toContain(token('ana'));
  expect(stored.local).not.toContain('bms_');
  // Solo comodidades de cada persona: el idioma y el tema (ninguna pestana, ninguna ficha).
  for (const key of stored.keys) expect(key).toMatch(/^bms-app:v1:((demo|real):\d+:)?(lang|theme)$/);
  expect(stored.session).toBe(0);
  expect(stored.cookie).toBe('');
  expect(stored.url).not.toContain(token('ana'));
  await login(page);
  await expect(viewHeading(page, 'home')).toBeVisible();
});

test('el menu del nombre: quien eres, Ajustes, idioma, tema y salir (que olvida el token)', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await page.getByRole('button', { name: 'Accountmenu van Ana Demo' }).click();
  const menu = page.getByRole('menu');
  await expect(menu).toContainText('Ingelogd als');
  await expect(menu).toContainText('Beheerder');
  await expect(menu.getByRole('group', { name: 'Taal' }).getByRole('menuitemradio')).toHaveText(['Nederlands', 'English', 'Español']);
  await expect(menu.getByRole('group', { name: 'Thema' }).getByRole('menuitemradio')).toHaveText(['Donker', 'Licht', 'Volg Windows']);
  await capture(page, 'nl-account-menu');
  await menu.getByRole('menuitem', { name: 'Instellingen' }).click();
  await expect(viewHeading(page, 'settings')).toBeVisible();
  // Ajustes no es de ninguna entrada: ninguna marcada.
  await expect(mainMenu(page).locator('[aria-current]')).toHaveCount(0);
  await signOut(page);
  await expect(page.getByRole('status').filter({ hasText: 'Je bent uitgelogd.' })).toBeVisible();
  await expect(page.locator('#token')).toHaveValue('');
  const local = await page.evaluate(() => JSON.stringify({ ...localStorage }));
  expect(local).not.toContain(token('ana'));
});

test('el idioma es de cada persona', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  // Ana entra en neerlandes (el de la entrada) y ese queda como el suyo.
  await login(page, 'ana');
  await expect(page.getByRole('heading', { level: 1, name: 'Welkom, Ana' })).toBeVisible();
  await signOut(page);
  // Bram elige ingles; al recargar, la entrada sale en el ultimo idioma usado, y el suyo vuelve.
  await login(page, 'bram');
  await setLang(page, 'en');
  await expect(page.getByRole('heading', { level: 1, name: 'Welcome, Bram' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Log in' })).toBeVisible();
  await login(page, 'bram');
  await expect(page.getByRole('heading', { level: 1, name: 'Welcome, Bram' })).toBeVisible();
  await signOut(page, 'en');
  // Ana vuelve a tener el suyo.
  await login(page, 'ana');
  await expect(page.getByRole('heading', { level: 1, name: 'Welkom, Ana' })).toBeVisible();
});

test('una sesion que caduca vuelve a la entrada con el aviso', async ({ page, baseUrl, watch }) => {
  watch.expectHttpErrors(401);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // El inicio tambien lee las facturas: que termine antes de que el servidor "retire" el token,
  // para que el 401 llegue al abrir la Werklijst.
  await expect(page.getByRole('heading', { level: 2, name: 'Als eerste' })).toBeVisible();
  // El servidor dice 401 (como si el token se hubiera retirado): la app sale sola.
  await page.route('**/api/v2/facturas', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"x"}' })
  );
  await page.getByRole('navigation', { name: TEXTS.nl.home.alsoHere }).getByRole('button', { name: /^Werklijst/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inloggen' })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Je sessie is beëindigd' })).toBeVisible();
});

/**
 * Lo que se sale de la ventana por los lados: cada elemento visible que pasa del borde y no
 * esta dentro de algo que se desplaza en horizontal (una tabla en su caja). Lo que recorta un
 * overflow hidden no cuenta como desplazable: tambien es estar fuera.
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

test('a 1024 px las seis entradas caben en una fila y nada se sale de la ventana', async ({ page, baseUrl }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  expect(await outsideTheWindow(page), 'inicio').toEqual([]);
  for (const lang of ['nl', 'es'] as const) {
    await setLang(page, lang);
    await go(page, 'work-queue', lang);
    const entries = mainMenu(page, lang).getByRole('button');
    await expect(entries).toHaveCount(6);
    const tops = new Set<number>();
    for (const e of await entries.all()) tops.add(Math.round((await box(e)).y));
    expect(tops.size, `${lang}: una sola fila`).toBe(1);
    expect(await outsideTheWindow(page), `${lang} werklijst`).toEqual([]);
    await capture(page, `${lang}-work-queue-1024`);
  }
  await setLang(page, 'nl');
  await go(page, 'providers');
  await page.getByRole('table').getByRole('button').first().click();
  expect(await outsideTheWindow(page), 'ficha').toEqual([]);
  await capture(page, 'nl-provider-1024');
  await expectAccessible(page, '1024');
});

// En el movil (de 360 a 430 px): el inicio con la rueda, que se mueve con el dedo, y las seis
// entradas en dos filas en las demas pantallas, todo dentro de la ventana y a un toque.
for (const size of [
  { width: 400, height: 860 },
  { width: 360, height: 740 },
] as const) {
  test.describe(`${size.width} × ${size.height}`, () => {
    test.use({ viewport: size, hasTouch: true, isMobile: true });

    test(`en el movil (${size.width} px) las seis entradas se ven y se tocan`, async ({ page, baseUrl }) => {
      await page.goto(`${baseUrl}/app`);
      await login(page);
      expect(await outsideTheWindow(page), 'inicio').toEqual([]);
      const entries = mainMenu(page).getByRole('button');
      await expect(entries).toHaveCount(6);
      for (const e of await entries.all()) {
        const b = await box(e);
        expect(b.x).toBeGreaterThanOrEqual(0);
        expect(b.x + b.width).toBeLessThanOrEqual(size.width);
        // (WCAG 2.5.8 pide 24 px)
        expect(b.height).toBeGreaterThanOrEqual(32);
      }
      await capture(page, `nl-mobile-home-${size.width}`);

      // Deslizar el dedo hacia arriba sobre la rueda la gira (sin abrir nada).
      const list = await box(mainMenu(page).getByRole('list'));
      const x = list.x + list.width / 2;
      const y = list.y + list.height - 20;
      const client = await page.context().newCDPSession(page);
      await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
      for (let i = 1; i <= 8; i += 1) {
        await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y - i * 10 }] });
      }
      // El dedo se para antes de soltar: si se suelta en marcha, Chromium sigue el gesto (un
      // "fling") y el primer toque que llega justo despues solo lo para, sin clic, como en una
      // lista que se desliza.
      await page.waitForTimeout(200);
      await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y - 80 }] });
      await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      await expect.poll(() => activeWheelEntry(page)).not.toBe('Start');
      await expect(viewHeading(page, 'home')).toBeVisible();

      // Un toque en una entrada la abre.
      await sectionButton(page, 'payables').tap();
      await expect(viewHeading(page, 'invoices-in')).toBeVisible();
      // Fuera del inicio, las seis en pequeno, enteras en la ventana y a un toque.
      const compact = mainMenu(page).getByRole('button');
      await expect(compact).toHaveCount(6);
      for (const e of await compact.all()) {
        const b = await box(e);
        expect(b.x).toBeGreaterThanOrEqual(0);
        expect(b.x + b.width).toBeLessThanOrEqual(size.width);
        expect(b.height).toBeGreaterThanOrEqual(24);
      }
      expect(await outsideTheWindow(page), 'inkoopfacturen').toEqual([]);
      await page.getByRole('table').getByRole('button').first().tap();
      await expect(page.getByRole('button', { name: 'Terug', exact: true })).toBeVisible();
      expect(await outsideTheWindow(page), 'factuur').toEqual([]);
      await expectAccessible(page, `movil ${size.width}`);
      await capture(page, `nl-mobile-invoice-${size.width}`);
      await page.getByRole('button', { name: 'Terug', exact: true }).tap();
      await expect(viewHeading(page, 'invoices-in')).toBeVisible();
      await sectionButton(page, 'documents').tap();
      await expect(viewHeading(page, 'documents')).toBeVisible();
      await setLang(page, 'es');
      expect(await outsideTheWindow(page), 'documentos es').toEqual([]);
      await capture(page, `es-mobile-documents-${size.width}`);
      await setLang(page, 'nl');
    });
  });
}

test('el teclado llega a todo y se ve donde esta', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // El primer Tab ofrece saltar al contenido.
  await page.keyboard.press('Tab');
  await expect(page.getByText(TEXTS.nl.shell.skipToContent)).toBeFocused();
  await go(page, 'invoices-out');
  // Las entradas, las vistas de la seccion y el menu del nombre, todos con el foco a la vista.
  for (const target of [
    sectionButton(page, 'vat'),
    sectionMenu(page, 'receivables').getByRole('button', { name: /^Klanten/ }),
    page.getByRole('button', { name: 'Accountmenu van Ana Demo' }),
    page.getByRole('button', { name: 'Zoeken' }),
  ]) {
    await target.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(target).toBeFocused();
    expect(await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle)).not.toBe('none');
  }
  await settled(page);
});
