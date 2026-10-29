// La base de la app (paso 17): la de Aurora. La entrada en el mismo sitio que el inicio (L0); el
// inicio con el saludo, el orbe, «Druk om te navigeren» y la caja (E0); la rueda de Aurora con
// las ocho entradas (E1): cada una abre a la primera, la rueda del raton, las flechas, Tab y el
// dedo giran; los paneles (E2) con su ✕, Escape y el orbe; las pantallas de trabajo con el vuelo
// del orbe, las migas y «Terug naar Aurora»; Ajustes (idioma, tema, cuenta, sistema y salir);
// que nada se guarda del token ni de donde se estaba. Captura de cada pantalla en los tres
// idiomas (los dos temas, en themes.spec.ts). La regla del dueno (o el menu o una pantalla), en
// exclusividad.spec.ts; las medidas contra Aurora, en aurora-paridad.spec.ts.
import type { Locator, Page } from '@playwright/test';
import { capture, expect, expectAccessible, expectNoLeftovers, login, outsideTheWindow, settled, test, token } from './fixtures';
import {
  ENTRIES,
  TEXTS,
  app,
  auroraRoot,
  centre,
  crumbs,
  crumbsNav,
  entryButton,
  entryLabel,
  fill,
  greeting,
  landed,
  openCard,
  openDocuments,
  openEntry,
  openFolder,
  openGroup,
  openMenu,
  openSettingsRow,
  orb,
  panel,
  panelRow,
  panelTitle,
  processLanded,
  profileRow,
  readCount,
  setLang,
  sheetDialog,
  signOut,
  toHome,
  tourAll,
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
  // Los idiomas, en la linea discreta de Aurora: «Español · Nederlands · English», con el mismo
  // aire a los dos lados de cada punto.
  const gaps = await page.locator('.discreet-languages').evaluate((group) => {
    const buttons = Array.from(group.querySelectorAll('button')).map((b) => b.getBoundingClientRect());
    const dots: DOMRect[] = [];
    const walker = document.createTreeWalker(group, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode as Text;
      const at = node.data.indexOf('·');
      if (at < 0) continue;
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + 1);
      dots.push(range.getBoundingClientRect());
    }
    return dots.map((d, i) => ({ before: d.left - buttons[i]!.right, after: buttons[i + 1]!.left - d.right, y: Math.abs(d.y + d.height / 2 - (buttons[i]!.y + buttons[i]!.height / 2)) }));
  });
  expect(gaps).toHaveLength(2);
  for (const g of gaps) {
    expect(g.before, 'aire antes del punto').toBeGreaterThan(1);
    expect(Math.abs(g.before - g.after), `el mismo aire a los dos lados (${g.before.toFixed(1)} y ${g.after.toFixed(1)} px)`).toBeLessThanOrEqual(1);
    expect(g.y, 'el punto, en la misma linea').toBeLessThanOrEqual(2);
  }
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
  // (Con el panel ya quieto: si Playwright pulsa la ✕ mientras el panel entra, la busca
  // desplazando la pagina, y la prueba de abajo mira que la pagina no se mueva.)
  await settled(page);
  await panel(page).getByRole('button', { name: t.aurora.panel.close }).click();
  await expect(wheel(page)).toBeVisible();
  expect(await activeEntry(page)).toBe('payables');
  await settled(page);
  await entryButton(page, 'vat').click();
  await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel('vat') })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(panel(page)).toHaveCount(0);
  expect(await activeEntry(page)).toBe('vat');

  // La rueda del raton gira un paso por gesto y la pagina no se mueve. (Playwright, al pulsar una
  // entrada del borde de la rueda, la acerca a la vista y puede desplazar la pagina lo que ocupan
  // las bandas del servidor, lo unico que sobra: se mide desde arriba.)
  await settled(page);
  await page.evaluate(() => window.scrollTo(0, 0));
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

test('al apoyar el raton en una entrada, pasa al centro como en Aurora, y el clic abre esa aunque se suelte sobre otra', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openMenu(page);
  expect(await activeEntry(page)).toBe('home');
  // Te betalen, dos filas por debajo del centro.
  const target = await box(entryButton(page, 'payables'));
  const point = { x: target.x + target.width / 2, y: target.y + target.height / 2 };
  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  // Al apoyar: la activa (main.tsx:32, el foco), y la pista se desliza hasta ponerla en el centro.
  await expect.poll(() => activeEntry(page)).toBe('payables');
  await settled(page);
  const under = await page.evaluate((p) => document.elementFromPoint(p.x, p.y)?.closest('.nav-item')?.getAttribute('data-entry') ?? null, point);
  expect(under, 'bajo el raton, ahora otra fila').toBe('process');
  // Se suelta encima de Verwerken: se abre la que se apoyo.
  await page.mouse.up();
  await expect(panel(page).getByRole('heading', { level: 2, name: entryLabel('payables') })).toBeVisible();
  expect(await activeEntry(page)).toBe('payables');
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
  // Lo que pide hacer algo, con su numero en la fila de su grupo (el panel Inicio).
  await openEntry(page, 'home');
  await expect.poll(() => readCount(page, t.nav['work-queue'].label)).toBeGreaterThan(0);
  await expect(panelRow(page, t.nav['work-queue'].label)).toContainText('geblokkeerd');
  await expect.poll(() => readCount(page, t.nav.exceptions.label)).toBeGreaterThan(0);
  await expect.poll(() => readCount(page, t.aurora.home.iban)).toBeGreaterThan(0);
  // Un grupo abre su vista dentro del panel, y "Terug naar Start" (o Escape) vuelve.
  await openGroup(page, t.nav['work-queue'].label);
  await expect(wheel(page)).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(entryLabel('home'));
});

test('una factura del panel abre su hoja con el vuelo del orbe; «Terug naar Aurora», la miga Start y el orbe vuelven', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openEntry(page, 'payables');
  await openGroup(page, t.aurora.money.week);
  const card = await openCard(page, panel(page).locator('.doc-list button.doc').first());
  await card.getByRole('button', { name: t.aurora.card.openInvoice }).click();
  // El vuelo: una copia de la onda va del centro al orbe pequeno de la esquina.
  await expect(page.locator('.aurora-route-flight')).toHaveCount(1);
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await landed(page);
  await expect(sheetDialog(page)).toBeVisible();
  await expect(page.locator('.ws-companion')).toBeVisible();
  // Ni la rueda ni el panel: una pantalla.
  await expect(wheel(page)).toHaveCount(0);
  await expect(panel(page)).toHaveCount(0);
  expect((await crumbs(page))[0]).toBe(t.nav.documents.label);
  await expectAccessible(page, 'pantalla de trabajo');
  await capture(page, 'nl-work-invoice');
  await page.keyboard.press('Escape');
  await page.getByRole('link', { name: t.aurora.work.back }).click();
  await expect(page.locator('.aurora-route-flight')).toHaveCount(1);
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await landed(page);
  await expect(greeting(page)).toBeVisible();
  await expect(wheel(page)).toHaveCount(0);
  // La miga «Start» y el orbe pequeno, igual.
  await openDocuments(page);
  await crumbsNav(page).getByRole('link', { name: t.aurora.work.home }).click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await landed(page);
  // Procesar no es una pantalla de trabajo: es el espacio central sin orbe (como en Aurora), y
  // «Terug naar start» vuelve al inicio, sin vuelo.
  await openEntry(page, 'process');
  await expect(page.locator('.ws-companion')).toHaveCount(0);
  await page.locator('.processing-back').click();
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await expect(app(page)).not.toHaveClass(/\bprocess-mode\b/);
  await expect(greeting(page)).toBeVisible();
});

test('cada sitio de la app se alcanza desde la rueda, en los tres idiomas', async ({ page, baseUrl }) => {
  test.setTimeout(600_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  for (const lang of ['nl', 'en', 'es'] as const) {
    await setLang(page, lang);
    await tourAll(page, lang, async (what) => {
      await expectAccessible(page, `${lang} ${what}`);
      await expectNoLeftovers(page, lang, `${lang} ${what}`);
      await capture(page, `${lang}-${what.replace(/[^\p{L}\d-]+/gu, '-').toLowerCase()}`);
    });
  }
  await setLang(page, 'nl');
});

test('en Documentos las migas dicen donde se esta; la miga anterior y Alt+← vuelven', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openDocuments(page);
  expect(await crumbs(page)).toEqual([t.nav.documents.label]);
  // Una carpeta y una factura suya: las migas crecen con lo que se abre. (Los clientes de la base
  // de prueba no tienen documentos: sus facturas de venta llegan de Exact, sin PDF.)
  const folder = 'Proefwacht Security VOF';
  await openFolder(page, folder, 'provider');
  expect(await crumbs(page)).toEqual([t.nav.documents.label, t.documents.providers, folder]);
  await profileRow(page, /^Inkoopfactuur PW26/).first().click();
  await expect(sheetDialog(page)).toBeVisible();
  const trail = await crumbs(page);
  expect(trail.slice(0, 3)).toEqual([t.nav.documents.label, t.documents.providers, folder]);
  expect(trail[3]).toMatch(/PW26/);
  await expectAccessible(page, 'hoja de factura');
  await capture(page, 'nl-invoice');
  // Escape cierra la hoja; la miga anterior vuelve a la categoria.
  await page.keyboard.press('Escape');
  await expect(sheetDialog(page)).toHaveCount(0);
  await crumbsNav(page).getByRole('link', { name: t.documents.providers }).click();
  expect(await crumbs(page)).toEqual([t.nav.documents.label, t.documents.providers]);
  // Alt + flecha izquierda vuelve al inicio.
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
});

test('al recargar se vuelve a entrar, en el inicio; el token y las pantallas no se guardan', async ({ page, baseUrl }) => {
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openEntry(page, 'vat');
  await openCard(page, panel(page).locator('.doc-list button.doc').first());
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
  await expect.poll(() => readCount(page, t.nav['work-queue'].label)).toBeGreaterThan(0);
  await openGroup(page, t.nav['work-queue'].label);
  // El servidor dice 401 (como si el token se hubiera retirado): la app sale sola.
  await page.route('**/api/v2/facturas/**', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":"x"}' }));
  await panel(page).locator('.doc-list button.doc').first().click();
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
    await openEntry(page, 'home', lang);
    await openGroup(page, TEXTS[lang].nav['work-queue'].label);
    expect(await outsideTheWindow(page), `${lang} werklijst`).toEqual([]);
    await capture(page, `${lang}-work-queue-1024`);
  }
  await setLang(page, 'nl');
  await openDocuments(page);
  await openFolder(page, 'J. Voorbeeld Beveiliging (zzp)', 'provider');
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
      // Un grupo, una fila (su tarjeta) y la hoja de su factura: todo con el dedo.
      await panelRow(page, t.aurora.money.week).tap();
      await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(t.aurora.money.week);
      expect(await outsideTheWindow(page), 'deze week').toEqual([]);
      await panel(page).locator('.doc-list button.doc').first().tap();
      await expect(panel(page).locator('.detail')).toBeVisible();
      await panel(page).locator('.detail').getByRole('button', { name: t.aurora.card.openInvoice }).tap();
      await landed(page);
      await expect(sheetDialog(page)).toBeVisible();
      expect(await outsideTheWindow(page), 'factuur').toEqual([]);
      await expectAccessible(page, `movil ${size.width}`);
      await capture(page, `nl-mobile-invoice-${size.width}`);
      await page.keyboard.press('Escape');
      await setLang(page, 'es');
      expect(await outsideTheWindow(page), 'ajustes es').toEqual([]);
      await openDocuments(page, 'es');
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
  // El orbe, la ✕ del panel y las filas: con el foco a la vista.
  await openEntry(page, 'receivables');
  for (const target of [orb(page), panel(page).getByRole('button', { name: t.aurora.panel.close }), panelRow(page, t.aurora.money.proposals)]) {
    await target.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(target).toBeFocused();
    expect(await focusShown(page)).toBe(true);
  }
  // Intro en una fila de grupo abre su vista; Escape vuelve.
  await panelRow(page, t.aurora.money.proposals).focus();
  await page.keyboard.press('Enter');
  await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(t.aurora.money.proposals);
  await page.keyboard.press('Escape');
  await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(entryLabel('receivables'));
  // En una pantalla de trabajo, las migas y «Terug naar Aurora» se alcanzan, con el foco a la vista.
  await openDocuments(page);
  for (const target of [page.getByRole('link', { name: t.aurora.work.back }), crumbsNav(page).getByRole('link', { name: t.aurora.work.home })]) {
    // Con el teclado (no con el raton): el contorno es el de :focus-visible.
    await target.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
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

/** El contraste de dos colores CSS (rgb o rgba sobre opaco), como lo cuenta WCAG. */
function contrast(a: string, b: string): number {
  const lum = (css: string) => {
    const [r, g, bl] = css.match(/[\d.]+/g)!.slice(0, 3).map((v) => Number(v) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r! + 0.7152 * g! + 0.0722 * bl!;
  };
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x! + 0.05) / (y! + 0.05);
}

/** Lo que tiene el foco: su etiqueta, su clase y su texto (para los mensajes). */
const focused = (page: Page) =>
  page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    return el ? `${el.tagName.toLowerCase()}.${el.className} «${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 40)}»` : 'nada';
  });

test('solo con el teclado: la rueda, el nombre del orbe, a donde va el foco, Alt+← y lo que se oye', async ({ page, baseUrl }) => {
  test.setTimeout(240_000);
  await page.goto(`${baseUrl}/app`);
  await login(page);
  // E0: el orbe abre la rueda.
  await expect(orb(page)).toHaveAccessibleName(t.aurora.home.open);
  // «Druk om te navigeren» con Intro: el boton se va y el foco pasa a la entrada activa.
  await page.getByRole('button', { name: t.aurora.home.navigate }).focus();
  await page.keyboard.press('Enter');
  await expect(wheel(page)).toBeVisible();
  await expect(entryButton(page, 'home')).toBeFocused();
  await expect(orb(page)).toHaveAccessibleName(t.aurora.home.close);
  // Dos flechas abajo: la activa es la resaltada y el foco va con ella (la de antes queda fuera).
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => activeEntry(page)).toBe('payables');
  await expect(entryButton(page, 'payables')).toBeFocused();
  // Intro abre la resaltada, y el foco va al titulo del panel, que lo nombra.
  await page.keyboard.press('Enter');
  await expect(panelTitle(page)).toHaveText(entryLabel('payables'));
  await expect(panelTitle(page)).toBeFocused();
  await expect(page.getByRole('complementary', { name: entryLabel('payables') })).toBeVisible();
  await expect(orb(page)).toHaveAccessibleName(t.aurora.home.backHome);
  // Escape lo cierra y el foco vuelve a su entrada de la rueda.
  await page.keyboard.press('Escape');
  await expect(panel(page)).toHaveCount(0);
  await expect(entryButton(page, 'payables')).toBeFocused();
  // Con el foco en la rueda (el grupo), las flechas y Fin/Inicio mueven la activa e Intro la abre.
  await page.locator('.marquee').focus();
  await page.keyboard.press('ArrowUp');
  await expect.poll(() => activeEntry(page)).toBe('receivables');
  await page.keyboard.press('Enter');
  await expect(panelTitle(page)).toHaveText(entryLabel('receivables'));
  // Alt+←: en un panel, lo mismo que Escape; en la rueda, la cierra (E0), con el foco en el orbe.
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(panel(page)).toHaveCount(0);
  await expect(wheel(page)).toBeVisible();
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(wheel(page)).toHaveCount(0);
  await expect(orb(page)).toBeFocused();
  // Con Verwerken en el centro, el orbe entra en Procesar, y lo dice; dentro, el foco va a
  // «Terug naar start», y el estado se anuncia.
  await page.keyboard.press('Enter');
  await expect(wheel(page)).toBeVisible();
  await page.locator('.marquee').focus();
  await page.keyboard.press('End');
  await expect.poll(() => activeEntry(page)).toBe('process');
  await expect(orb(page)).toHaveAccessibleName(fill(t.aurora.home.openWhat, { what: entryLabel('process') }));
  await orb(page).focus();
  await page.keyboard.press('Enter');
  await processLanded(page);
  await expect(page.locator('.processing-back')).toBeFocused();
  await expect(page.locator('main [role=status].sr-only')).toContainText(await page.locator('.welcome-line h1').innerText());
  // «Terug naar start» sobre el negro de Procesar: el contorno del foco se ve (3:1).
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  await expect(page.locator('.processing-back')).toBeFocused();
  const back = await page.locator('.processing-back').evaluate((el) => [getComputedStyle(el).outlineColor, getComputedStyle(el).outlineStyle]);
  expect(back[1]).not.toBe('none');
  expect(contrast(back[0]!, 'rgb(0, 0, 0)'), `el contorno ${back[0]} sobre negro`).toBeGreaterThanOrEqual(3);
  await page.keyboard.press('Enter');
  await expect(app(page)).not.toHaveClass(/\bprocess-mode\b/);
  await expect(orb(page)).toBeFocused();
  // El orbe con el foco: su aro se ve sobre el fondo (3:1).
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  await expect(orb(page)).toBeFocused();
  const ring = await orb(page).evaluate((el) => getComputedStyle(el, '::after').boxShadow);
  expect(ring).not.toBe('none');
  expect(contrast(ring, 'rgb(8, 9, 11)'), `el aro del orbe, ${ring}`).toBeGreaterThanOrEqual(3);
  // La caja, al llegar con Tab: su borde se ve (3:1); con el raton no cambia.
  const ask = page.getByRole('textbox', { name: t.aurora.composer.askLabel });
  const border = () => page.locator('.composer-area .composer').evaluate((el) => getComputedStyle(el).borderTopColor);
  const rest = await border();
  for (let i = 0; i < 6 && !(await ask.evaluate((el) => el === document.activeElement)); i += 1) await page.keyboard.press('Tab');
  await expect(ask).toBeFocused();
  expect(contrast(await border(), 'rgb(8, 9, 11)'), `el borde de la caja con el foco`).toBeGreaterThanOrEqual(3);
  await page.mouse.click(5, 300);
  await ask.click();
  expect(await border()).toBe(rest);
  // Escribiendo (E3): el orbe vuelve al inicio, y Alt+← tambien.
  await ask.fill('IVA');
  await expect(orb(page)).toHaveAccessibleName(t.aurora.home.backHome);
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(app(page)).not.toHaveClass(/\bchatting\b/);
  // La conversacion (E4): la respuesta terminada se anuncia; Alt+← es «Terug naar de werkruimte».
  await ask.fill('Wat is een Object?');
  await ask.press('Enter');
  await expect(page.locator('.conversation')).toBeVisible();
  await expect(page.locator('.typing-dots')).toHaveCount(0, { timeout: 15_000 });
  await expect(page.locator('.conversation [role=status].sr-only')).not.toBeEmpty();
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(page.locator('.conversation')).toHaveCount(0);
  await expect(wheel(page)).toBeVisible();
  // La busqueda (E5): el orbe vuelve al inicio, y Alt+← tambien.
  await centre(page, 'search');
  await entryButton(page, 'search').press('Enter');
  await expect(app(page)).toHaveClass(/\bsearch-mode\b/);
  await expect(orb(page)).toHaveAccessibleName(t.aurora.home.backHome);
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(app(page)).not.toHaveClass(/\bsearch-mode\b/);
  await expect(wheel(page)).toHaveCount(0);
  // Documentos con Intro en su entrada: despues del vuelo, el foco en su titulo; Alt+← vuelve y
  // el foco queda en el orbe.
  await page.getByRole('button', { name: t.aurora.home.navigate }).press('Enter');
  await centre(page, 'documents');
  await entryButton(page, 'documents').press('Enter');
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await landed(page);
  await expect(page.locator('#contenido')).toBeFocused();
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'home');
  await landed(page);
  await expect.poll(() => focused(page)).toContain('button.aurora');
});

test('con «menos movimiento» no hay vuelo y la rueda gira sin animacion', async ({ page, baseUrl }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${baseUrl}/app`);
  await login(page);
  await openMenu(page);
  const instant = (el: Element) => getComputedStyle(el).transitionDuration.split(',').every((d) => parseFloat(d) < 0.001);
  expect(await page.locator('.marquee-track').evaluate(instant)).toBe(true);
  expect(await orb(page).evaluate(instant)).toBe(true);
  // Lo que mueve motion tampoco se mueve: con Verwerken en el centro, el orbe de particulas sale
  // ya en su sitio (sin girar ni crecer) y el saludo cambia sin desplazarse.
  await entryButton(page, 'process').focus();
  await expect(page.locator('.hero-orb')).toHaveCount(1);
  const still = await page.locator('.hero-orb').evaluate((el) => ({
    running: el.getAnimations().filter((a) => a.playState === 'running').length,
    transform: getComputedStyle(el).transform,
  }));
  expect(still.running, 'el orbe de particulas, sin animacion').toBe(0);
  expect(['none', 'matrix(1, 0, 0, 1, 0, 0)']).toContain(still.transform);
  await entryButton(page, 'documents').focus();
  await expect.poll(() => activeEntry(page)).toBe('documents');
  await entryButton(page, 'documents').click();
  // Sin vuelo: la pantalla de trabajo, a la primera.
  await expect(auroraRoot(page)).toHaveAttribute('data-screen', 'work');
  await expect(page.locator('.aurora-route-flight')).toHaveCount(0);
  await expect(page.locator('.ws-grid')).toBeVisible();
});
