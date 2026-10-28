// La base de la app (paso 17): la de Aurora. La entrada en el mismo sitio que el inicio (L0); el
// inicio con el saludo, el orbe, «Druk om te navigeren» y la caja (E0); la rueda de Aurora con
// las ocho entradas (E1): cada una abre a la primera, la rueda del raton, las flechas, Tab y el
// dedo giran; los paneles (E2) con su ✕, Escape y el orbe; las pantallas de trabajo con el vuelo
// del orbe, las migas y «Terug naar Aurora»; Ajustes (idioma, tema, cuenta, sistema y salir);
// que nada se guarda del token ni de donde se estaba. Captura de cada pantalla en los tres
// idiomas (los dos temas, en themes.spec.ts). La regla del dueno (o el menu o una pantalla), en
// exclusividad.spec.ts; las medidas contra Aurora, en aurora-paridad.spec.ts.
import type { Locator, Page } from '@playwright/test';
import { VIEW_IDS } from '../src/screens/sections';
import { capture, expect, expectAccessible, expectNoLeftovers, login, outsideTheWindow, settled, test, token } from './fixtures';
import {
  ENTRIES,
  TEXTS,
  app,
  auroraRoot,
  back,
  centre,
  crumbs,
  crumbsNav,
  entryButton,
  entryLabel,
  go,
  greeting,
  landed,
  openEntry,
  openMenu,
  openSettingsRow,
  orb,
  panel,
  panelRow,
  readBadge,
  setLang,
  signOut,
  toHome,
  viewHeading,
  wheel,
} from './nav';

/** La caja de una cosa en la pagina. */
async function box(locator: Locator) {
  const b = await locator.boundingBox();
  expect(b, 'se ve').not.toBeNull();
  return b!;
}

/** La entrada que esta en el centro de la rueda (la activa). */
async function activeEntry(page: Page): Promise<string | null> {
  return app(page).getAttribute('data-active');
}

const t = TEXTS.nl;

/** Que el foco se ve: el contorno de Aurora (styles.css) o, en el orbe, su sombra de 1 px. */
async function focusShown(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const cs = getComputedStyle(document.activeElement!);
    return cs.outlineStyle !== 'none' || cs.boxShadow !== 'none';
  });
}

test('la entrada: en el sitio del inicio, en neerlandes por defecto, en ingles y en castellano', async ({ page, baseUrl, watch }) => {
  watch.expectHttpErrors(401);
  await page.goto(`${baseUrl}/app`);
  // La banda de datos de prueba la pone el servidor, por encima de la app.
  await expect(page.locator('#datos-de-prueba')).toContainText('TESTGEGEVENS · TEST DATA');
  await expect(page.getByRole('heading', { level: 1, name: t.aurora.login.welcome })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'nl');
  await expect(page.getByText(t.aurora.login.prompt)).toBeVisible();
  // El orbe esta, pero no se pulsa hasta entrar; ni rueda ni «Druk om te navigeren».
  await expect(orb(page)).toHaveAttribute('aria-hidden', 'true');
  await expect(page.getByRole('button', { name: t.aurora.home.navigate })).toHaveCount(0);
  await expect(wheel(page)).toHaveCount(0);
  await expectAccessible(page, 'entrada nl');
  await capture(page, 'nl-login');

  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: TEXTS.en.aurora.login.welcome })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await capture(page, 'en-login');
  await page.getByRole('button', { name: 'Español', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: TEXTS.es.aurora.login.welcome })).toBeVisible();
  await expectNoLeftovers(page, 'es', 'entrada es');
  await capture(page, 'es-login');
  await page.getByRole('button', { name: 'English', exact: true }).click();

  // Ni <form> ni campo de contrasena: Edge no ofrece guardar el token en su gestor de
  // contrasenas. Los caracteres van tapados igual.
  await expect(page.locator('form')).toHaveCount(0);
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await expect(page.locator('#token')).toHaveAttribute('autocomplete', 'one-time-code');
  expect(await page.locator('#token').evaluate((el) => getComputedStyle(el).getPropertyValue('-webkit-text-security'))).toBe('disc');

  // Un token que no vale: lo dice, y el campo se vacia. Intro tambien entra.
  await page.locator('#token').fill('bms_no-vale');
  await page.locator('#token').press('Enter');
  await expect(page.getByRole('alert').filter({ hasText: TEXTS.en.login.invalid })).toBeVisible();
  await page.locator('#token').fill('bms_no-vale');
  await page.getByRole('button', { name: TEXTS.en.aurora.login.submit }).click();
  await expect(page.getByRole('alert').filter({ hasText: TEXTS.en.login.invalid })).toBeVisible();
  await expect(page.locator('#token')).toHaveValue('');
  await expectAccessible(page, 'entrada con error');
  await capture(page, 'en-login-error');
  // El aviso cambia de idioma con la app.
  await page.getByRole('button', { name: 'Nederlands', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: t.login.invalid })).toBeVisible();
});

test('el inicio (E0): el saludo con el nombre, el orbe, «Druk om te navigeren» y la caja; nada mas', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // El nombre de quien entro (/api/v2/yo), no el "Alberto" del prototipo.
  await expect(page.getByRole('heading', { level: 1, name: 'Welkom, Ana' })).toBeVisible();
  await expect(page.getByText(t.aurora.home.intro)).toBeVisible();
  await expect(orb(page)).toHaveAccessibleName(t.aurora.home.open);
  await expect(page.getByRole('button', { name: t.aurora.home.navigate })).toBeVisible();
  await expect(page.getByRole('textbox', { name: t.aurora.composer.askLabel })).toBeVisible();
  // Ni la rueda, ni un panel, ni tarjetas, ni barra de arriba, ni un boton de buscar a la vista.
  await expect(wheel(page)).toHaveCount(0);
  await expect(panel(page)).toHaveCount(0);
  await expect(page.locator('header')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^(Zoeken|Search|Buscar)$/ })).toHaveCount(0);
  // Una sola pantalla, sin desplazamiento (main{min-height:100dvh;overflow:hidden} de Aurora):
  // solo lo que ocupan las bandas del servidor, encima.
  expect(
    await page.evaluate(() => {
      const bands = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bms-bandas')) || 0;
      return document.documentElement.scrollHeight <= window.innerHeight + bands + 1;
    })
  ).toBe(true);
  await expectAccessible(page, 'inicio nl');
  await expectNoLeftovers(page, 'nl', 'inicio nl');
  await capture(page, 'nl-home');
});

test('la rueda (E1): las ocho entradas en su orden, Inicio en el centro, y el orbe la abre y la cierra', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await page.getByRole('button', { name: t.aurora.home.navigate }).click();
  await expect(wheel(page)).toBeVisible();
  const items = wheel(page).locator('.nav-item');
  await expect(items).toHaveCount(8);
  expect(await items.allTextContents()).toEqual(ENTRIES.map((id) => entryLabel(id)));
  expect(await activeEntry(page)).toBe('home');
  await expect(entryButton(page, 'home')).toHaveAttribute('aria-current', 'true');
  await expect(page.getByRole('group', { name: t.aurora.home.marquee })).toBeVisible();
  // «Druk om te navigeren» se va; el saludo y la caja siguen.
  await expect(page.getByRole('button', { name: t.aurora.home.navigate })).toHaveCount(0);
  await expect(greeting(page)).toBeVisible();
  await expectAccessible(page, 'rueda nl');
  await capture(page, 'nl-menu');
  // El orbe cierra la rueda y la vuelve a abrir, con la misma entrada en el centro.
  await orb(page).click();
  await expect(wheel(page)).toHaveCount(0);
  await orb(page).click();
  await expect(wheel(page)).toBeVisible();
  expect(await activeEntry(page)).toBe('home');
});

test('cada entrada a la vista se abre con el primer clic, y la rueda del raton, las flechas y Tab llegan a las demas', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openMenu(page);
  // Un clic normal en una entrada que NO es la del centro la abre (en Aurora solo la centraba
  // y el clic se perdia).
  expect(await activeEntry(page)).toBe('home');
  await entryButton(page, 'payables').click();
  await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel('payables') })).toBeVisible();
  // La ✕ vuelve a la rueda con esa entrada en el centro; la de al lado, tambien a la primera.
  await panel(page).getByRole('button', { name: t.aurora.panel.close }).click();
  await expect(wheel(page)).toBeVisible();
  expect(await activeEntry(page)).toBe('payables');
  await settled(page);
  await entryButton(page, 'vat').click();
  await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel('vat') })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(panel(page)).toHaveCount(0);
  expect(await activeEntry(page)).toBe('vat');

  // La rueda del raton gira un paso por gesto y la pagina no se mueve.
  await settled(page);
  const marquee = await box(page.locator('.marquee'));
  await page.mouse.move(marquee.x + marquee.width / 2, marquee.y + marquee.height / 2);
  await page.mouse.wheel(0, 120);
  await expect.poll(() => activeEntry(page)).toBe('process');
  await page.waitForTimeout(300);
  // Al final no da la vuelta.
  await page.mouse.wheel(0, 120);
  await page.waitForTimeout(300);
  expect(await activeEntry(page)).toBe('process');
  // Con Procesar en el centro: el morado y el orbe de particulas, como en Aurora.
  await expect(app(page)).toHaveClass(/\bprocess-highlight\b/);
  await expect(page.locator('.hero-orb')).toBeVisible();
  await capture(page, 'nl-menu-process');
  for (let i = 0; i < 7; i += 1) {
    await page.mouse.wheel(0, -120);
    await page.waitForTimeout(260);
  }
  await expect.poll(() => activeEntry(page)).toBe('settings');
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await capture(page, 'nl-menu-settings');

  // Las flechas, con el foco en la rueda.
  await page.locator('.marquee').focus();
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => activeEntry(page)).toBe('search');
  await page.keyboard.press('ArrowUp');
  await expect.poll(() => activeEntry(page)).toBe('settings');
  // Tab llega a cada entrada y la centra; el foco se ve; Intro la abre.
  for (const id of ENTRIES) {
    await entryButton(page, id).focus();
    await expect.poll(() => activeEntry(page)).toBe(id);
  }
  await centre(page, 'receivables');
  await expect(entryButton(page, 'receivables')).toBeFocused();
  expect(await focusShown(page)).toBe(true);
  // La ventana no se ha desplazado con el foco: la entrada sigue en el centro de la rueda.
  const centreRow = await box(entryButton(page, 'receivables'));
  const windowBox = await box(page.locator('.marquee'));
  expect(Math.abs(centreRow.y + centreRow.height / 2 - (windowBox.y + windowBox.height / 2))).toBeLessThanOrEqual(2);
  await capture(page, 'nl-menu-focus');
  await page.keyboard.press('Enter');
  await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel('receivables') })).toBeVisible();
});

test('los paneles: cada entrada el suyo; la ✕ y Escape vuelven a la rueda, el orbe al inicio', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const id of ['settings', 'home', 'receivables', 'payables', 'vat'] as const) {
    await openEntry(page, id);
    const p = panel(page);
    await expect(p).toContainText(t.aurora.panel.workspace);
    // La rueda, oculta mientras hay panel (la regla del dueno).
    await expect(wheel(page)).toBeHidden();
    await expectAccessible(page, `panel ${id}`);
    await expectNoLeftovers(page, 'nl', `panel ${id}`);
    await capture(page, `nl-panel-${id}`);
  }
  // El orbe con un panel abierto: al inicio (E0).
  await orb(page).click();
  await expect(panel(page)).toHaveCount(0);
  await expect(wheel(page)).toHaveCount(0);
  await expect(page.getByRole('button', { name: t.aurora.home.navigate })).toBeVisible();
  // Las insignias de lo que pide hacer algo, en las filas de su panel.
  await expect.poll(() => readBadge(page, 'work-queue')).toBeGreaterThan(0);
  await expect(panelRow(page, t.nav['work-queue'].label)).toContainText(t.badges.blocked);
  await expect.poll(() => readBadge(page, 'exceptions')).toBeGreaterThan(0);
  await expect.poll(() => readBadge(page, 'iban-checks')).toBeGreaterThan(0);
});

test('una fila del panel abre su pantalla con el vuelo del orbe; «Terug naar Aurora» y la miga Start vuelven', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openEntry(page, 'payables');
  await panelRow(page, t.nav['invoices-in'].label).click();
  // El vuelo: una copia de la onda va del centro al orbe pequeno de la esquina.
  await expect(page.locator('.aurora-route-flight')).toHaveCount(1);
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await landed(page);
  await expect(viewHeading(page, 'invoices-in')).toBeVisible();
  await expect(page.locator('.ws-companion')).toBeVisible();
  // Ni la rueda ni el panel: una pantalla.
  await expect(wheel(page)).toHaveCount(0);
  await expect(panel(page)).toHaveCount(0);
  expect(await crumbs(page)).toEqual([t.areas.payables.label, t.nav['invoices-in'].label]);
  await expectAccessible(page, 'pantalla de trabajo');
  await capture(page, 'nl-work-invoices-in');
  await page.getByRole('link', { name: t.aurora.work.back }).click();
  await expect(page.locator('.aurora-route-flight')).toHaveCount(1);
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await landed(page);
  await expect(greeting(page)).toBeVisible();
  await expect(wheel(page)).toHaveCount(0);
  // La miga «Start» y el orbe pequeno, igual.
  await go(page, 'clients');
  await crumbsNav(page).getByRole('link', { name: t.aurora.work.home }).click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await landed(page);
  await go(page, 'vat');
  await page.locator('.ws-companion').click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await landed(page);
});

test('cada pantalla de la app se alcanza desde la rueda, en los tres idiomas', async ({ page, baseUrl }) => {
  test.setTimeout(600_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const lang of ['nl', 'en', 'es'] as const) {
    await setLang(page, lang);
    for (const view of VIEW_IDS) {
      await go(page, view, lang);
      if (view === 'work-queue') await expect(page.getByRole('table')).toBeVisible();
      await expectAccessible(page, `${lang} ${view}`);
      await expectNoLeftovers(page, lang, `${lang} ${view}`);
      await capture(page, `${lang}-${view}`);
    }
  }
  await setLang(page, 'nl');
});

test('una fila abre su ficha en la pantalla de trabajo, con migas; la miga anterior y Alt+← vuelven', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'work-queue');
  await page.getByRole('group', { name: 'Toon' }).getByRole('button', { name: /^Urgent/ }).click();
  const first = page.getByRole('table').getByRole('row').nth(1).getByRole('button');
  const number = (await first.locator('.font-mono').textContent())!.trim();
  await first.click();
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(`${number.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) })).toBeVisible();
  expect(await crumbs(page)).toEqual([t.nav['work-queue'].label, number]);
  await expectAccessible(page, 'ficha de factura');
  await capture(page, 'nl-invoice');

  // Los detalles van plegados; se abren con el teclado.
  const details = page.getByRole('button', { name: /^Velden/ });
  await expect(details).toHaveAttribute('aria-expanded', 'false');
  await details.focus();
  await page.keyboard.press('Enter');
  await expect(details).toHaveAttribute('aria-expanded', 'true');

  // La miga anterior: la lista con el mismo filtro.
  await back(page);
  await expect(viewHeading(page, 'work-queue')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Toon' }).getByRole('button', { name: /^Urgent/ })).toHaveAttribute('aria-pressed', 'true');

  // Un cliente, su factura, y de vuelta al cliente por la miga; Alt + flecha izquierda, a la lista.
  await go(page, 'clients');
  await page.getByRole('table').getByRole('button', { name: /Gemeente Demodorp/ }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: 'Gemeente Demodorp' })).toBeVisible();
  await page.getByRole('button', { name: 'Factuur VD26-306 openen' }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: /VD26-306$/ })).toBeVisible();
  expect(await crumbs(page)).toEqual(['Te ontvangen', 'Klanten', 'Gemeente Demodorp', 'VD26-306']);
  await crumbsNav(page).getByRole('link', { name: 'Gemeente Demodorp' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Gemeente Demodorp' })).toBeVisible();
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(viewHeading(page, 'clients')).toBeVisible();
  // En la raiz, Alt + flecha izquierda vuelve al inicio.
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
});

test('al recargar se vuelve a entrar, en el inicio; el token y las pantallas no se guardan', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await go(page, 'vat');
  await page.getByRole('table').getByRole('button').first().click();
  await page.reload();
  // Recargar es empezar de nuevo: el token no estaba en ningun sitio del navegador.
  await expect(page.getByRole('heading', { level: 1, name: t.aurora.login.welcome })).toBeVisible();
  const stored = await page.evaluate(() => ({
    local: JSON.stringify({ ...localStorage }),
    keys: Object.keys(localStorage),
    session: sessionStorage.length,
    cookie: document.cookie,
    url: location.href,
  }));
  expect(stored.local).not.toContain(token('ana'));
  expect(stored.local).not.toContain('bms_');
  // Solo comodidades de cada persona: el idioma y el tema (ninguna pantalla, ninguna ficha).
  for (const key of stored.keys) expect(key).toMatch(/^bms-app:v1:((demo|real):\d+:)?(lang|theme)$/);
  expect(stored.session).toBe(0);
  expect(stored.cookie).toBe('');
  expect(stored.url).not.toContain(token('ana'));
  await login(page);
  await expect(greeting(page)).toBeVisible();
  await expect(wheel(page)).toHaveCount(0);
});

test('Ajustes (E2-A): idioma, tema, tu cuenta, el sistema y salir (que olvida el token)', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openEntry(page, 'settings');
  const s = t.aurora.settings;
  for (const row of [s.language, s.theme, s.account, s.system]) await expect(panelRow(page, row)).toBeVisible();
  await expect(panelRow(page, s.language)).toContainText('Nederlands');
  await expect(panelRow(page, s.theme)).toContainText(t.theme.dark);
  await expect(panelRow(page, s.account)).toContainText('Ana Demo');
  await expect(panelRow(page, s.account)).toContainText(t.account.roleAdmin);
  // Tu cuenta: la tarjeta con lo que puede hacer.
  await panelRow(page, s.account).click();
  await expect(panel(page).locator('.detail')).toContainText(t.settings.accountHelp);
  await capture(page, 'nl-settings-account');
  // Idioma: la vista del grupo, con «Terug naar Instellingen».
  await openSettingsRow(page, 'language');
  await expect(panel(page).locator('button.doc')).toHaveCount(3);
  await expect(panelRow(page, 'Nederlands')).toContainText(s.inUse);
  await capture(page, 'nl-settings-language');
  await panel(page).getByRole('button', { name: `Terug naar ${t.nav.settings.label}` }).click();
  await expect(panelRow(page, s.system)).toBeVisible();
  // El sistema: bedrijf, afscherming, personen (admin) y back-ups.
  await panelRow(page, s.system).click();
  for (const row of Object.values(s.systemRows)) await expect(panelRow(page, row)).toBeVisible();
  await panelRow(page, s.systemRows.isolation).click();
  await expect(panel(page).locator('.detail')).toBeVisible();
  await expectAccessible(page, 'ajustes sistema');
  await capture(page, 'nl-settings-system');
  // Escape cierra la tarjeta, luego la vista y luego el panel.
  await page.keyboard.press('Escape');
  await expect(panel(page).locator('.detail')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(panelRow(page, s.language)).toBeVisible();
  await signOut(page);
  await expect(page.getByText(t.login.loggedOut)).toBeVisible();
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
  await toHome(page);
  await expect(page.getByRole('heading', { level: 1, name: 'Welcome, Bram' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: TEXTS.en.aurora.login.welcome })).toBeVisible();
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
  await openEntry(page, 'home');
  // Que terminen las lecturas del panel antes de que el servidor "retire" el token.
  await expect.poll(() => readBadge(page, 'work-queue')).toBeGreaterThan(0);
  // El servidor dice 401 (como si el token se hubiera retirado): la app sale sola.
  await page.route('**/api/v2/facturas*', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"x"}' }));
  await panelRow(page, t.nav['work-queue'].label).click();
  await expect(page.getByRole('heading', { level: 1, name: t.aurora.login.welcome })).toBeVisible();
  await expect(page.getByText(t.aurora.login.expired)).toBeVisible();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
});

test('a 1024 px nada se sale de la ventana: inicio, rueda, panel y pantalla de trabajo', async ({ page, baseUrl }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  expect(await outsideTheWindow(page), 'inicio').toEqual([]);
  await openMenu(page);
  expect(await outsideTheWindow(page), 'rueda').toEqual([]);
  for (const lang of ['nl', 'es'] as const) {
    await setLang(page, lang);
    await openEntry(page, 'receivables', lang);
    expect(await outsideTheWindow(page), `${lang} panel`).toEqual([]);
    await go(page, 'work-queue', lang);
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

// En el movil (de 360 a 430 px): lo de Aurora a 700 px o menos. El dedo gira la rueda (un paso
// por gesto) y un toque abre una entrada; todo dentro de la ventana.
for (const size of [
  { width: 400, height: 860 },
  { width: 360, height: 740 },
] as const) {
  test.describe(`${size.width} × ${size.height}`, () => {
    test.use({ viewport: size, hasTouch: true, isMobile: true });

    test(`en el movil (${size.width} px) la rueda se gira con el dedo y cada entrada se toca`, async ({ page, baseUrl }) => {
      await page.goto(`${baseUrl}/app`);
      await login(page);
      expect(await outsideTheWindow(page), 'inicio').toEqual([]);
      await capture(page, `nl-mobile-home-${size.width}`);
      await page.getByRole('button', { name: t.aurora.home.navigate }).tap();
      await expect(wheel(page)).toBeVisible();
      await settled(page);
      // Deslizar el dedo hacia arriba sobre la rueda da un paso (sin abrir nada).
      const list = await box(page.locator('.marquee'));
      const x = list.x + list.width / 2;
      const y = list.y + list.height / 2 + 30;
      const client = await page.context().newCDPSession(page);
      await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
      for (let i = 1; i <= 6; i += 1) {
        await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y - i * 10 }] });
      }
      await page.waitForTimeout(200);
      await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      await expect.poll(() => activeEntry(page)).toBe('receivables');
      await expect(panel(page)).toHaveCount(0);
      await settled(page);
      expect(await outsideTheWindow(page), 'rueda').toEqual([]);
      // Las entradas a la vista miden lo de Aurora (48 px) y se tocan.
      const row = await box(entryButton(page, 'payables'));
      expect(row.height).toBeGreaterThanOrEqual(24);
      await capture(page, `nl-mobile-menu-${size.width}`);
      await entryButton(page, 'payables').tap();
      await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel('payables') })).toBeVisible();
      expect(await outsideTheWindow(page), 'panel').toEqual([]);
      await capture(page, `nl-mobile-panel-${size.width}`);
      await panelRow(page, t.aurora.panel.overview).tap();
      await expect(viewHeading(page, 'payables')).toBeVisible();
      await landed(page);
      expect(await outsideTheWindow(page), 'te betalen').toEqual([]);
      await page.getByTestId('week-clean').getByRole('button').first().tap();
      await expect(crumbsNav(page)).toBeVisible();
      expect(await outsideTheWindow(page), 'factuur').toEqual([]);
      await expectAccessible(page, `movil ${size.width}`);
      await capture(page, `nl-mobile-invoice-${size.width}`);
      await go(page, 'documents');
      await setLang(page, 'es');
      expect(await outsideTheWindow(page), 'ajustes es').toEqual([]);
      await go(page, 'documents', 'es');
      expect(await outsideTheWindow(page), 'documentos es').toEqual([]);
      await capture(page, `es-mobile-documents-${size.width}`);
      await setLang(page, 'nl');
    });
  });
}

test('el teclado llega a todo y se ve donde esta', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // «Naar de inhoud» (el primero de la pagina) se ve al recibir el foco y lleva a la caja.
  const skip = page.getByText(t.shell.skipToContent);
  expect(await skip.evaluate((el) => el.compareDocumentPosition(document.querySelector('[data-aurora-root]')!) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
  await skip.focus();
  const skipBox = await box(skip);
  expect(skipBox.y).toBeGreaterThanOrEqual(0);
  await page.keyboard.press('Enter');
  await expect(page.getByRole('textbox', { name: t.aurora.composer.askLabel })).toBeFocused();
  // El orbe, «Druk om te navigeren», la rueda, la ✕ del panel y las filas: con el foco a la vista.
  await openEntry(page, 'receivables');
  for (const target of [orb(page), panel(page).getByRole('button', { name: t.aurora.panel.close }), panelRow(page, t.nav.clients.label)]) {
    await target.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(target).toBeFocused();
    expect(await focusShown(page)).toBe(true);
  }
  // En una pantalla de trabajo, el foco va al contenido; las migas y «Terug naar Aurora» se alcanzan.
  await panelRow(page, t.nav.clients.label).focus();
  await page.keyboard.press('Enter');
  await expect(viewHeading(page, 'clients')).toBeVisible();
  await landed(page);
  for (const target of [page.getByRole('link', { name: t.aurora.work.back }), crumbsNav(page).getByRole('link', { name: t.aurora.work.home })]) {
    await target.focus();
    await expect(target).toBeFocused();
    expect(await focusShown(page)).toBe(true);
  }
  // En una pantalla de trabajo, «Naar de inhoud» lleva a su cuerpo.
  await skip.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#contenido')).toBeFocused();
  await page.getByRole('link', { name: t.aurora.work.back }).press('Enter');
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await settled(page);
});

test('con «menos movimiento» no hay vuelo y la rueda gira sin animacion', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openMenu(page);
  const instant = (el: Element) => getComputedStyle(el).transitionDuration.split(',').every((d) => parseFloat(d) < 0.001);
  expect(await page.locator('.marquee-track').evaluate(instant)).toBe(true);
  expect(await orb(page).evaluate(instant)).toBe(true);
  await entryButton(page, 'payables').focus();
  await expect.poll(() => activeEntry(page)).toBe('payables');
  await entryButton(page, 'payables').click();
  await panelRow(page, t.aurora.panel.overview).click();
  // Sin vuelo: la pantalla de trabajo, a la primera.
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await expect(page.locator('.aurora-route-flight')).toHaveCount(0);
  await expect(viewHeading(page, 'payables')).toBeVisible();
});
