// Los tiempos de Aurora (paso 17, especificacion §6.2): cada transicion de la tabla T01–T33, medida
// por los instantes en que su cambio pasa por el 5, el 50 y el 95 % (e2e/aurora/cruces.ts), contra
// los de la curva del codigo del dueno: ±10 % o una muestra. La medida es en la linea de tiempo de
// la animacion del navegador (se para y se lleva a cada instante: un cuadro lento de esta maquina
// no cambia la curva); lo que no es del navegador (el texto que se escribe, la cifra de puntos de
// Finance Bento) se muestrea cuadro a cuadro con el reloj virtual. La misma herramienta se paso
// antes por el prototipo del dueno (e2e/aurora/tiempos.json): todas sus filas dan lo de la curva
// del codigo, y donde la tabla de §6.2 decia otra curva, manda el codigo (T06 la onda, T10, T13 la
// opacidad, T19 el aura, T25, T27 y T33: ease o ease-out, no la del orbe ni easeInOut). Los muelles
// de motion (el titulo, T26 y T32), contra lo medido en Aurora.
// T01, T11 y T17 venian de aurora-paridad.spec.ts (con el vuelo quieto al aterrizar, que sigue alli).
import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { expect, login, settled, test } from './fixtures';
import { TEXTS, entryButton, landed, openMenu, processLanded, setLang, treeItem } from './nav';
import { CURVES, curveErrors, measured, sampleInPage, seekWhenRunning, theory, type Curve, type Found, type SampleSpec, type SeekSpec, type Series } from './aurora/cruces';

const t = TEXTS.es;

/** Lo medido en el prototipo de Aurora (herramientas/tiempos-aurora.mts). */
const AURORA = JSON.parse(readFileSync(new URL('./aurora/tiempos.json', import.meta.url), 'utf8')) as Record<
  string,
  { measured?: { to50: number; to95: number; gap: number } | null; theory?: { to50: number; to95: number } | null; length?: number; charsPerSecond?: number; firstText?: number }
>;

/** Lo que falla de las medidas de una prueba, y lo medido (para el registro). */
class Timings {
  errors: string[] = [];
  lines: string[] = [];
  constructor(private readonly page: Page) {}

  /** Mide una animacion del navegador que empieza con `trigger` (o que ya va a empezar). */
  async seek(id: string, spec: SeekSpec, want: Curve | { to50: number; to95: number } | null, trigger: () => Promise<unknown> = async () => {}, timeout = 6000): Promise<Found | null> {
    const pending = this.page.evaluate(seekWhenRunning, { ...spec, timeout });
    await trigger();
    const found = await pending;
    if (!found) {
      this.errors.push(`${id}: no se encontro la animacion (${JSON.stringify(spec)})`);
      return null;
    }
    this.check(id, found.series, want, spec.duration || found.duration);
    return found;
  }

  check(id: string, series: Series, want: Curve | { to50: number; to95: number } | null, duration: number): void {
    const m = measured(series);
    if (want === null) {
      this.lines.push(`${id}: ${m ? `${m.to50.toFixed(0)} / ${m.to95.toFixed(0)} ms` : 'sin cruces'}`);
      return;
    }
    const target = Array.isArray(want) || typeof want === 'string' ? theory(want as Curve, duration) : (want as { to50: number; to95: number });
    this.errors.push(...curveErrors(id, target, series));
    this.lines.push(`${id}: ${m ? `${m.to50.toFixed(0)} / ${m.to95.toFixed(0)}` : '—'} ms (teorico ${target.to50.toFixed(0)} / ${target.to95.toFixed(0)})`);
  }

  done(what: string): void {
    console.log(`${what}\n  ${this.lines.join('\n  ')}`);
    expect(this.errors, what).toEqual([]);
  }
}

/** Lo medido en Aurora para una fila. */
function aurora(id: string): { to50: number; to95: number } {
  const m = AURORA[id]?.measured;
  if (!m) throw new Error(`sin la medida de Aurora: ${id}`);
  return m;
}

async function enter(page: Page, baseUrl: string): Promise<void> {
  await page.goto(`${baseUrl}/app`);
  await setLang(page, 'es');
  await login(page);
  await settled(page);
}

async function wheel(page: Page, dy: number): Promise<void> {
  const box = (await page.locator('.marquee').boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, dy);
  await page.waitForTimeout(400);
}

test('T01–T10: el menu, un paso de la rueda, Procesar en el centro y un panel, con las curvas de Aurora', async ({ page, baseUrl }) => {
  test.setTimeout(180_000);
  await enter(page, baseUrl);
  const m = new Timings(page);
  // T01 y T02: abrir el menu (el orbe a la izquierda, la rueda aparece).
  await Promise.all([
    m.seek('T02 la rueda aparece', { selector: '.navigation', duration: 600, name: 'appear', measure: 'opacity' }, CURVES.ease),
    m.seek('T01 el orbe al abrir', { selector: '.aurora', duration: 850, property: 'left', measure: 'cx' }, CURVES.orb, () => page.getByRole('button', { name: t.aurora.home.navigate }).click()),
  ]);
  await settled(page);
  // T04 y T05: un paso de la rueda (la pista y el color de la nueva activa).
  await Promise.all([
    m.seek('T05 el color de la activa', { selector: '.nav-item.selected', duration: 300, property: 'color', measure: 'color' }, CURVES.ease),
    m.seek('T04 la pista', { selector: '.marquee-track', duration: 650, property: 'transform', measure: 'y' }, CURVES.track, () => wheel(page, 120)),
  ]);
  await settled(page);
  // T03: cerrar el menu con el orbe.
  await m.seek('T03 el orbe al cerrar', { selector: '.aurora', duration: 850, property: 'left', measure: 'cx' }, CURVES.orb, () => page.locator('button.aurora').click());
  await settled(page);
  // T06 y T07: Procesar en el centro (el orbe de particulas entra, la onda sale, el morado).
  await openMenu(page, 'es');
  await wheel(page, 120);
  await wheel(page, 120);
  await settled(page);
  expect(await page.locator('[data-aurora-root] .app').getAttribute('data-active')).toBe('vat');
  await Promise.all([
    m.seek('T06 la onda sale', { selector: '.aurora .hero-wave', duration: 650, property: 'opacity', measure: 'opacity' }, CURVES.easeOut),
    m.seek('T06 el orbe de particulas crece', { selector: '.aurora .hero-orb', duration: 900, property: 'transform', measure: 'scale' }, CURVES.particles),
    m.seek('T06 el orbe de particulas aparece', { selector: '.aurora .hero-orb', duration: 900, property: 'opacity', measure: 'opacity' }, CURVES.particles),
    m.seek('T07 el morado de Procesar', { selector: '.nav-item.selected', duration: 450, property: 'color', measure: 'color' }, CURVES.ease, () => wheel(page, 120)),
  ]);
  await settled(page);
  // T08, T09 y T10: abrir un panel (IVA, un paso arriba).
  await wheel(page, -120);
  await settled(page);
  await Promise.all([
    m.seek('T08 el panel', { selector: '.panel', duration: 500, name: 'appear', measure: 'opacity' }, CURVES.ease),
    m.seek('T09 el orbe con el panel', { selector: '.aurora', duration: 850, property: 'left', measure: 'cx' }, CURVES.orb),
    m.seek('T09 el orbe a 0,75', { selector: '.aurora', duration: 850, property: 'transform', measure: 'scale' }, CURVES.orb),
    m.seek('T10 la caja con el panel', { selector: '.composer-area', duration: 850, property: 'width', measure: 'w' }, CURVES.ease, () => entryButton(page, 'vat').click()),
  ]);
  m.done('T01–T10');
});

test('T19–T22 y T24–T25: la primera tecla, enviar, el mensaje, los puntos, el resumen y volver', async ({ page, baseUrl }) => {
  test.setTimeout(180_000);
  await enter(page, baseUrl);
  const m = new Timings(page);
  const box = page.getByRole('textbox', { name: t.aurora.composer.askLabel });
  // T19: la primera tecla (el orbe a 0,18 y el hueco del aura en la caja).
  await Promise.all([
    m.seek('T19 el orbe a 0,18', { selector: '.aurora', duration: 850, property: 'transform', measure: 'scale' }, CURVES.orb),
    m.seek('T19 el aura de la caja', { selector: '.aura-slot', duration: 850, property: 'width', measure: 'w' }, CURVES.ease, () => box.pressSequentially('h')),
  ]);
  await settled(page);
  // T20, T21 y T22: enviar.
  await box.fill('Dame un resumen general');
  const [, , , dots] = await Promise.all([
    m.seek('T20 la conversacion', { selector: '.conversation', duration: 600, name: 'chat-enter', measure: 'opacity' }, CURVES.track),
    m.seek('T20 la caja', { selector: '.composer-area', duration: 600, property: 'width', measure: 'w' }, CURVES.ease),
    m.seek('T21 el mensaje', { selector: '.chat-message', duration: 400, name: 'chat-message-in', measure: 'opacity' }, CURVES.ease),
    m.seek('T22 los puntos', { selector: '.typing-dots i', duration: 1100, name: 'typing-dot', measure: 'opacity' }, null, () => box.press('Enter')),
  ]);
  // T22: 1,1 s en bucle (ease-in-out por fotograma, como en Aurora).
  expect(dots?.iterations, 'T22: los puntos, en bucle').toBe(Infinity);
  // T24: las tarjetas de Finance Bento salen ya puestas, como en Aurora (la clase `in` llega en el
  // mismo cambio que las tarjetas: su transicion no corre, ni alli ni aqui), con su escalon de
  // 45 ms; la cifra de puntos, con su transicion de 0,26 s y 7 ms por columna.
  await expect(page.locator('.fpb .card').first()).toBeVisible({ timeout: 20_000 });
  const cards = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>('.fpb .card'))
      .slice(0, 3)
      .map((c) => ({ opacity: getComputedStyle(c).opacity, delay: c.style.transitionDelay, anims: c.getAnimations().length }))
  );
  expect(cards, 'T24: las tarjetas, como en Aurora').toEqual(AURORA['T24-tarjetas'] as unknown as typeof cards);
  const circles = await page.evaluate(() => {
    const c = document.querySelectorAll('.fpb svg.dots circle');
    return [0, 7, 70].map((i) => c[i] && { delay: getComputedStyle(c[i]!).transitionDelay, duration: getComputedStyle(c[i]!).transitionDuration });
  });
  expect(circles, 'T24: los puntos de la cifra, como en Aurora').toEqual(AURORA['T24-puntos'] as unknown as typeof circles);
  await settled(page);
  // T25: volver al espacio (la caja vuelve).
  await m.seek('T25 la caja vuelve', { selector: '.composer-area', duration: 850, property: 'width', measure: 'w' }, CURVES.ease, () => page.getByRole('button', { name: t.aurora.chat.back }).click());
  m.done('T19–T22, T24 y T25');
});

test('T22–T24 con el reloj virtual: 650 ms pensando, 4 caracteres cada 16 ms y la cifra de puntos en 0,9 s', async ({ page, baseUrl }) => {
  test.setTimeout(180_000);
  await page.clock.install();
  await enter(page, baseUrl);
  const m = new Timings(page);
  const box = page.getByRole('textbox', { name: t.aurora.composer.askLabel });
  /** Pregunta con el reloj parado y lo lleva de 16 en 16 ms mientras se muestrea. */
  const run = async (question: string, spec: SampleSpec, ms: number): Promise<Series> => {
    await box.fill(question);
    const now = (await page.evaluate(() => Date.now())) as number;
    await page.clock.pauseAt(now + 50);
    const pending = page.evaluate(sampleInPage, spec);
    await box.press('Enter');
    for (let at = 0; at < ms; at += 16) await page.clock.runFor(16);
    const series = await pending;
    await page.clock.resume();
    return series;
  };
  // T22 y T23: lo que no sabe contestar (una frase larga), de 4 en 4 caracteres cada 16 ms, despues
  // de 650 ms pensando.
  const text = await run('xyzzy', { selector: '.conversation', read: 'text', quiet: 300, timeout: 4000 }, 3000);
  const first = text.find((r) => r[1] !== text[0]![1]);
  let chars = 0,
    time = 0;
  for (let i = 1; i < text.length; i += 1) {
    const d = text[i]![1] - text[i - 1]![1];
    if (d > 0 && d <= 8) {
      chars += d;
      time += text[i]![0] - text[i - 1]![0];
    }
  }
  const rate = (chars / time) * 1000;
  console.log(`T23: ${rate.toFixed(1)} caracteres por segundo (Aurora ${AURORA.T23?.charsPerSecond}); el primero a los ${first?.[0].toFixed(0)} ms (Aurora ${AURORA.T23?.firstText})`);
  expect(Math.abs(rate - 250), 'T23: 4 caracteres cada 16 ms').toBeLessThanOrEqual(25);
  expect(first?.[0] ?? 0, 'T22: como minimo 650 ms pensando').toBeGreaterThanOrEqual(650);
  expect(first?.[0] ?? 0, 'T22: y no mucho mas que Aurora').toBeLessThanOrEqual((AURORA.T23?.firstText ?? 671) + 48);
  await page.getByRole('button', { name: t.aurora.chat.back }).click();
  await settled(page);
  // T24: la cifra de puntos cuenta en 0,9 s con 1 − (1 − t)³.
  const value = await run('Dame un resumen general', { selector: '.fpb svg.dots', read: 'dots', quiet: 300, timeout: 4000 }, 3000);
  expect(value.length, 'T24: la cifra, cuadro a cuadro').toBeGreaterThan(30);
  m.check('T24 la cifra de puntos', value, 'cubic-out', 900);
  m.check('T24 la cifra de puntos, contra Aurora', value, aurora('T24-cifra'), 900);
  m.done('T22–T24');
});

test('T26–T28 y T32: la busqueda (el titulo, su muelle, el orbe, el glifo, los filtros y un desplegable) y la entrada', async ({ page, baseUrl }) => {
  test.setTimeout(180_000);
  await page.goto(`${baseUrl}/app`);
  await setLang(page, 'es');
  const m = new Timings(page);
  // T32: la entrada (L0 → E0), el cambio del saludo: el de la busqueda de Aurora.
  await page.locator('#token').fill(process.env.BMS_E2E_TOKEN_ANA ?? '');
  await Promise.all([
    m.seek('T32 el saludo aparece', { selector: '.welcome-line > div', duration: 300, property: 'opacity', measure: 'opacity' }, CURVES.motionOpacity),
    m.seek('T32 el saludo sube (muelle)', { selector: '.welcome-line > div', duration: 0, property: 'transform', measure: 'y' }, aurora('T26-titulo-muelle'), () => page.locator('#login-submit').click()),
  ]);
  await expect(page.locator('#token')).toHaveCount(0);
  await settled(page);
  // T26: la busqueda.
  await openMenu(page, 'es');
  await Promise.all([
    m.seek('T26 el titulo aparece', { selector: '.welcome-line > div', duration: 300, property: 'opacity', measure: 'opacity' }, CURVES.motionOpacity),
    m.seek('T26 el titulo sube (muelle)', { selector: '.welcome-line > div', duration: 0, property: 'transform', measure: 'y' }, aurora('T26-titulo-muelle')),
    m.seek('T26 el orbe a 0,58', { selector: '.aurora', duration: 850, property: 'transform', measure: 'scale' }, CURVES.orb),
    m.seek('T26 el glifo de la caja', { selector: '.composer-glyph', duration: 180, property: 'opacity', measure: 'opacity' }, CURVES.easeOut, async () => {
      await entryButton(page, 'search').focus();
      await settled(page);
      await entryButton(page, 'search').click();
    }),
  ]);
  await settled(page);
  // T27 y T28: los filtros y el desplegable del tipo de documento.
  await m.seek('T27 los filtros', { selector: '.search-filters', duration: 250, property: 'opacity', measure: 'opacity' }, CURVES.easeOut, () => page.getByRole('button', { name: new RegExp(t.aurora.search.filters) }).first().click());
  await settled(page);
  await m.seek('T28 el desplegable', { selector: '.ui-popover', duration: 180, name: 'search-popover', measure: 'opacity' }, CURVES.ease, () => page.locator(`.search-filters [aria-label="${t.aurora.search.kind}"]`).first().click());
  await page.keyboard.press('Escape');
  m.done('T26–T28 y T32');
});

test('T11–T18 y T33: Documentos (el vuelo, la llegada, las carpetas, la ficha, la bisagra, la vista previa, la vuelta y la pista)', async ({ page, baseUrl }) => {
  test.setTimeout(240_000);
  await enter(page, baseUrl);
  const m = new Timings(page);
  await openMenu(page, 'es');
  await entryButton(page, 'documents').focus();
  await settled(page);
  // T11, T12 y T33: el vuelo, la llegada de Documentos y el fundido de la pantalla que se va.
  await Promise.all([
    m.seek('T33 la pantalla que se va', { selector: '.app-screen', duration: 180, property: 'opacity', measure: 'opacity' }, CURVES.easeOut),
    m.seek('T12 la llegada', { selector: '.ws-title-line', duration: 650, name: 'documents-arrive', measure: 'opacity' }, CURVES.ease),
    m.seek('T11 el vuelo a Documentos', { selector: '.aurora-route-flight', duration: 1050, measure: 'cx' }, CURVES.flight, () => entryButton(page, 'documents').click()),
  ]);
  await landed(page);
  await settled(page);
  // T13: las carpetas al cambiar de categoria (opacidad e y, escalonadas 45 ms).
  // (motion empieza la animacion de y de cada una al acabar su espera: su retraso no va en la de
  // WAAPI, ni aqui ni en Aurora; el de la opacidad si, abajo).
  await Promise.all([
    m.seek('T13 la primera carpeta sube', { selector: '.ws-folder-cell', nth: 0, duration: 400, property: 'transform', measure: 'y' }, CURVES.folder),
    m.seek('T13 la tercera carpeta sube', { selector: '.ws-folder-cell', nth: 2, duration: 400, property: 'transform', measure: 'y' }, CURVES.folder, () => treeItem(page, t.documents.clients).first().click()),
  ]);
  await settled(page);
  const [, thirdOpacity] = await Promise.all([
    m.seek('T13 la primera carpeta aparece', { selector: '.ws-folder-cell', nth: 0, duration: 320, property: 'opacity', measure: 'opacity' }, CURVES.easeOut),
    m.seek('T13 la tercera carpeta aparece', { selector: '.ws-folder-cell', nth: 2, duration: 320, property: 'opacity', measure: 'opacity' }, CURVES.easeOut, () => treeItem(page, t.documents.providers).first().click()),
  ]);
  expect(thirdOpacity?.delay, 'T13: la tercera, 90 ms despues').toBe(90);
  await settled(page);
  await treeItem(page, t.documents.clients).first().click();
  await settled(page);
  // T14 y T15: abrir una carpeta (la ficha y la bisagra del frente).
  await Promise.all([
    m.seek('T15 la bisagra', { selector: '.gf-front', duration: 800, property: 'transform', measure: 'rotateX' }, CURVES.hinge),
    m.seek('T14 la ficha', { selector: '.ws-profile, [class*="profile"]', duration: 280, property: 'opacity', measure: 'opacity' }, CURVES.folder, () => page.locator('.ws-folder-cell').first().locator('.gf-root, button').first().click()),
  ]);
  await settled(page);
  // T16: la vista previa de un documento.
  await m.seek('T16 la vista previa', { selector: '.ws-dialog', duration: 280, name: 'ws-file-open', measure: 'opacity' }, CURVES.easeOut, () => page.locator('.ws-profile .ws-file-table > a').first().click());
  await page.keyboard.press('Escape');
  await settled(page);
  // T17: el vuelo de vuelta.
  await m.seek('T17 el vuelo de vuelta', { selector: '.aurora-route-flight', duration: 1050, measure: 'cx' }, CURVES.flight, () => page.locator('a.ws-home').first().click(), 10000);
  await landed(page);
  await settled(page);
  // T18: la pista a los 12 s: el companero habla 4,2 s (como en Aurora).
  await openMenu(page, 'es');
  await entryButton(page, 'documents').focus();
  await settled(page);
  await entryButton(page, 'documents').click();
  const hint = await page.evaluate(async () => {
    const t0 = performance.now();
    let on = -1,
      off = -1;
    while (performance.now() - t0 < 20000 && off < 0) {
      await new Promise((r) => setTimeout(r, 50));
      const speaking = !!document.querySelector('.ws-companion.ws-speaking');
      if (speaking && on < 0) on = performance.now() - t0;
      if (!speaking && on >= 0) off = performance.now() - t0;
    }
    return { on, off, length: off - on };
  });
  console.log(`T18: la pista a los ${hint.on.toFixed(0)} ms, durante ${hint.length.toFixed(0)} ms (Aurora ${AURORA.T18?.length?.toFixed(0)})`);
  expect(Math.abs(hint.on - 12000), 'T18: a los 12 s').toBeLessThanOrEqual(1200);
  expect(Math.abs(hint.length - 4200), 'T18: durante 4,2 s').toBeLessThanOrEqual(420);
  m.done('T11–T18 y T33');
});

test('T29–T30: el fondo de Procesar y el circulo del boton', async ({ page, baseUrl }) => {
  test.setTimeout(120_000);
  await enter(page, baseUrl);
  const m = new Timings(page);
  await openMenu(page, 'es');
  await entryButton(page, 'process').focus();
  await settled(page);
  // T29: el fondo pasa al de Procesar.
  await m.seek('T29 el fondo de Procesar', { selector: '[data-aurora-root] .app', duration: 450, property: 'background-color', measure: 'background' }, CURVES.ease, () => entryButton(page, 'process').click());
  await processLanded(page);
  // T30: el circulo del FlowButton al pasar el raton.
  await m.seek('T30 el circulo del boton', { selector: '.flow-circle', duration: 800, property: 'width', measure: 'w' }, CURVES.flow, () => page.locator('.processing-workspace .flow-button').hover());
  m.done('T29–T30');
});

// T31 (la centinela 1,2 s y el fundido de 0,3 s de la escena) se mide al final de una lectura de
// verdad, en procesar.spec.ts («pedir, contar, empezar, leer y el resultado»).
