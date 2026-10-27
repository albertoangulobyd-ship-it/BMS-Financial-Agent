// La tabla de estados de components/status-pill.tsx: cada estado de cada grupo de los
// catalogos tiene su variante (ninguno cae en el gris de "no se conoce"), solo laten los
// que piden hacer algo ya, y cada uno tiene su texto en neerlandes y en ingles.
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider, LANGS, MESSAGES, type Lang } from '@/i18n';
import { catalogFor } from '@/i18n/domain';
import { PingScope, STATUS_GROUPS, STATUS_RULES, StatusPill, pings, statusLabel, statusRule, type StatusGroup } from './status-pill';

type Catalog = ReturnType<typeof catalogFor>;

/** Los grupos que salen de un catalogo, y de donde. */
const FROM_CATALOG: Partial<Record<StatusGroup, (c: Catalog) => string[]>> = {
  prioridad: (c) => Object.keys(c.prioridad),
  veredicto: (c) => Object.keys(c.veredicto),
  severidad: (c) => Object.keys(c.severidades),
  calidad: (c) => Object.keys(c.calidad),
  hallazgo: (c) => Object.keys(c.estados.hallazgo),
  pago: (c) => Object.keys(c.estados.pago),
  revision: (c) => Object.keys(c.estados.revision),
  excepcion: (c) => Object.keys(c.estados.excepcion),
  cuenta: (c) => Object.keys(c.estados.cuenta),
  relacion: (c) => Object.keys(c.estados.relacion),
  turno: (c) => Object.keys(c.estados.turno),
  btw: (c) => Object.keys(c.estados.btw),
  po: (c) => Object.keys(c.estados.po),
  importacion: (c) => Object.keys(c.estados.importacion),
};

/** Lo que la API no manda tal cual: se deriva en la pantalla (y esta dicho en la tabla). */
const DERIVED: Partial<Record<StatusGroup, string[]>> = {
  btw: ['plazo_cerca', 'plazo_vencido'],
  iban_control: ['por_verificar', 'sin_telefono'],
  iban_tecleado: ['coincide', 'difiere'],
  aislamiento: ['correcto', 'falla', 'sin_comprobar', 'caducada'],
  fuente: ['al_dia', 'caducada', 'sin_limite'],
  importar_prueba: ['ok', 'avisos', 'errores'],
  lectura: ['en_curso', 'terminada', 'con_errores'],
  datos_prueba: ['demo'],
  btw_config: ['confirmada', 'sin_confirmar'],
  empresa: ['completa', 'incompleta'],
};

/** Lo que el dueno pidio, tal cual (variante y si late). */
const OWNER: Record<string, [string, boolean]> = {
  'prioridad.bloqueada': ['error', true],
  'prioridad.urgente': ['warning', true],
  'prioridad.atencion': ['info', false],
  'prioridad.normal': ['default', false],
  'veredicto.limpia': ['success', false],
  'veredicto.limpia_sin_datos': ['success', false],
  'severidad.bloqueo': ['error', false],
  'severidad.retencion': ['warning', false],
  'severidad.aviso': ['info', false],
  'pago.vencida': ['error', false],
  'pago.pendiente': ['default', false],
  'pago.pagada': ['success', false],
  'pago.anulada': ['default', false],
  'pago.acreditada': ['default', false],
  'revision.necesita_revision': ['warning', false],
  'revision.sin_revisar': ['default', false],
  'revision.revisada': ['success', false],
  'excepcion.abierta': ['warning', false],
  'excepcion.esperando_externo': ['info', false],
  'excepcion.resuelta': ['success', false],
  'calidad.faltante': ['error', false],
  'calidad.dudoso': ['warning', false],
  'calidad.discrepancia': ['warning', false],
  'calidad.anomalia': ['info', false],
  'calidad.verificado': ['success', false],
  'cuenta.registrada': ['warning', true],
  'cuenta.verificada': ['success', false],
  'cuenta.rechazada': ['error', false],
  'iban_control.por_verificar': ['warning', true],
  'aislamiento.correcto': ['success', false],
  'aislamiento.falla': ['error', true],
  'aislamiento.sin_comprobar': ['error', true],
  'aislamiento.caducada': ['error', true],
  'fuente.al_dia': ['success', false],
  'fuente.caducada': ['warning', false],
  'btw.abierto': ['default', false],
  'btw.listo_revision': ['info', false],
  'btw.presentado': ['success', false],
  'btw.plazo_vencido': ['error', false],
  // Las senales de una PO llevan el color de la gravedad de su aviso (revision del paso 15:
  // el mismo aviso salia en dos colores en la misma ficha). Avisan: info; retienen: warning.
  'po_senal.P5': ['info', false],
  'po_senal.P7': ['info', false],
  'po_senal.P9': ['info', false],
  'po_senal.P4': ['warning', false],
  'importar_prueba.ok': ['success', false],
  'importar_prueba.avisos': ['warning', false],
  'importar_prueba.errores': ['error', false],
  'lectura.terminada': ['success', false],
  'lectura.con_errores': ['error', false],
  'lectura.en_curso': ['info', false],
  'datos_prueba.demo': ['warning', false],
  // Los que no estaban en la lista del dueno, con la misma logica (app-local.md, «Alertas y
  // estados»): lo que falta confirmar avisa, lo confirmado va en verde, nada late.
  'btw_config.sin_confirmar': ['warning', false],
  'btw_config.confirmada': ['success', false],
  'empresa.incompleta': ['warning', false],
  'empresa.completa': ['success', false],
  'excepcion.asignada': ['info', false],
  'po.cerrada': ['default', false],
  'po_senal.P6': ['warning', false],
  'po_senal.P8': ['info', false],
  'po_senal.P10': ['warning', false],
};

const PING = [
  'prioridad.bloqueada',
  'prioridad.urgente',
  'cuenta.registrada',
  'iban_control.por_verificar',
  'aislamiento.falla',
  'aislamiento.sin_comprobar',
  'aislamiento.caducada',
];

const all = (): [StatusGroup, string][] =>
  STATUS_GROUPS.flatMap((g) => Object.keys(STATUS_RULES[g]).map((s) => [g, s] as [StatusGroup, string]));

const VALUES = { n: 2, sin_datos: 3 };

describe('status-pill: la tabla de estados', () => {
  it('cada estado de cada grupo de los catalogos tiene su variante, y nada mas que lo derivado', () => {
    for (const lang of LANGS) {
      const c = catalogFor(lang);
      for (const [group, keys] of Object.entries(FROM_CATALOG) as [StatusGroup, (c: Catalog) => string[]][]) {
        const expected = [...keys(c), ...(DERIVED[group] ?? [])].sort();
        expect(Object.keys(STATUS_RULES[group]).sort(), `${lang} ${group}`).toEqual(expected);
      }
      for (const [group, states] of Object.entries(DERIVED) as [StatusGroup, string[]][]) {
        if (FROM_CATALOG[group]) continue;
        expect(Object.keys(STATUS_RULES[group]).sort(), group).toEqual([...states].sort());
      }
    }
  });

  it('las senales de una PO son reglas del catalogo', () => {
    for (const lang of LANGS) {
      const reglas = Object.keys(catalogFor(lang).reglas);
      for (const code of Object.keys(STATUS_RULES.po_senal)) expect(reglas, code).toContain(code);
    }
  });

  it('cada estado lleva la variante que pidio el dueno', () => {
    for (const [key, [variant, ping]] of Object.entries(OWNER)) {
      const [group, state] = key.split('.') as [StatusGroup, string];
      expect(statusRule(group, state), key).toEqual({ variant, ping });
    }
  });

  it('solo late lo que pide hacer algo ya', () => {
    const pinging = all()
      .filter(([g, s]) => statusRule(g, s).ping)
      .map(([g, s]) => `${g}.${s}`)
      .sort();
    expect(pinging).toEqual([...PING].sort());
  });

  it('late en un solo sitio por pantalla: en las listas y tarjetas nada, en la Werklijst lo bloqueado', () => {
    const blocked = statusRule('prioridad', 'bloqueada');
    const urgent = statusRule('prioridad', 'urgente');
    const toCall = statusRule('cuenta', 'registrada');
    // La cabecera de una ficha (y lo demas fuera de una lista): como dice la regla.
    expect(pings(blocked, 'all', 'prioridad', 'bloqueada')).toBe(true);
    expect(pings(urgent, 'all', 'prioridad', 'urgente')).toBe(true);
    // Las filas de la Werklijst: solo lo bloqueado.
    expect(pings(blocked, 'blocked', 'prioridad', 'bloqueada')).toBe(true);
    expect(pings(urgent, 'blocked', 'prioridad', 'urgente')).toBe(false);
    expect(pings(toCall, 'blocked', 'cuenta', 'registrada')).toBe(false);
    // Una lista, una tarjeta, una ficha de relacion: nada late.
    for (const [rule, g, st] of [[blocked, 'prioridad', 'bloqueada'], [urgent, 'prioridad', 'urgente'], [toCall, 'cuenta', 'registrada']] as const) {
      expect(pings(rule, 'none', g, st)).toBe(false);
    }
    // Lo que no late nunca, tampoco con 'all'.
    expect(pings(statusRule('prioridad', 'atencion'), 'all', 'prioridad', 'atencion')).toBe(false);
    // Y en el HTML: dentro de PingScope none, el punto lleva before:animate-none.
    const html = renderToStaticMarkup(
      createElement(I18nProvider, {
        lang: 'nl',
        setLang: () => {},
        children: createElement(PingScope, { scope: 'none', children: createElement(StatusPill, { group: 'prioridad', state: 'bloqueada' }) }),
      } as never)
    );
    expect(html).toContain('before:animate-none');
  });

  it('un estado que no se conoce va en gris, quieto y con su texto', () => {
    expect(statusRule('pago', 'otra_cosa')).toEqual({ variant: 'default', ping: false });
    expect(statusRule('prioridad', null)).toEqual({ variant: 'default', ping: false });
    const html = render('nl', 'pago', 'otra_cosa');
    expect(html).toContain('Onbekend');
  });

  it('cada estado tiene su texto en neerlandes y en ingles', () => {
    for (const lang of LANGS) {
      for (const [group, state] of all()) {
        const label = statusLabel(lang, MESSAGES[lang], group, state, VALUES);
        expect(label, `${lang} ${group}.${state}`).toBeTruthy();
        expect(label, `${lang} ${group}.${state}`).not.toMatch(/[{}]/);
      }
    }
    expect(statusLabel('nl', MESSAGES.nl, 'prioridad', 'bloqueada')).toBe('Geblokkeerd');
    expect(statusLabel('en', MESSAGES.en, 'veredicto', 'limpia')).toBe('No system objections');
    expect(statusLabel('nl', MESSAGES.nl, 'excepcion', 'esperando_externo', { esperando_a: 'proveedor' })).toBe(
      'Wacht op de leverancier'
    );
    // Con su cifra: el plazo dice cuantos dias quedan y lo caducado de cuanto es el limite.
    expect(statusLabel('nl', MESSAGES.nl, 'btw', 'plazo_cerca', { n: 5 })).toBe('Nog 5 dagen');
    expect(statusLabel('en', MESSAGES.en, 'btw', 'plazo_cerca', { n: 1 })).toBe('1 day left');
    expect(statusLabel('en', MESSAGES.en, 'btw', 'plazo_cerca')).toBe('Deadline close');
    expect(statusLabel('nl', MESSAGES.nl, 'fuente', 'caducada', { n: '5 werkdagen' })).toBe('Te oud (meer dan 5 werkdagen)');
    expect(statusLabel('en', MESSAGES.en, 'fuente', 'caducada')).toBe('Too old');
  });

  it('el aislamiento usa los estados que manda la API (app_local.ESTADOS_AISLAMIENTO)', () => {
    expect(Object.keys(STATUS_RULES.aislamiento).sort()).toEqual(['caducada', 'correcto', 'falla', 'sin_comprobar']);
  });

  it('esperando a alguien: "Esperando al proveedor" en castellano, no "a el"', () => {
    // Revision del paso 16: la plantilla era "Esperando a {who}" y el catalogo "el proveedor".
    const said = (lang: Lang, who: string) => statusLabel(lang, MESSAGES[lang], 'excepcion', 'esperando_externo', { esperando_a: who });
    expect(said('es', 'proveedor')).toBe('Esperando al proveedor');
    expect(said('es', 'banco')).toBe('Esperando al banco');
    expect(said('es', 'exact')).toBe('Esperando a Exact');
    expect(said('es', 'otro')).toBe('Esperando a otra persona');
    expect(said('nl', 'proveedor')).toBe('Wacht op de leverancier');
    expect(said('en', 'cliente')).toBe('Waiting on the client');
    for (const who of ['proveedor', 'cliente', 'contable', 'exact', 'trnsprnt', 'banco', 'otro']) expect(said('es', who)).not.toMatch(/\ba el\b/);
    // La pastilla dentro de una tarjeta lleva el texto de su fila (concuerda en castellano).
    const html = renderToStaticMarkup(
      createElement(I18nProvider, {
        lang: 'es',
        setLang: () => {},
        children: createElement(StatusPill, { group: 'prioridad', state: 'bloqueada', label: 'Bloqueadas' }),
      })
    );
    expect(html).toContain('Bloqueadas');
    expect(html).not.toContain('>Bloqueada<');
  });

  it('la pastilla es la del dueno: variante, punto y texto; el punto late solo donde toca', () => {
    for (const [group, state] of all()) {
      const html = render('nl', group, state);
      const rule = statusRule(group, state);
      expect(html).toContain('data-slot="status"');
      expect(html).toContain(`data-variant="${rule.variant}"`);
      expect(html).toContain('data-slot="status-indicator"');
      expect(html).toContain('data-slot="status-label"');
      expect(html.includes('before:animate-ping'), `${group}.${state}`).toBe(rule.ping);
      expect(html).toContain('motion-reduce:before:animate-none');
    }
  });
});

function render(lang: Lang, group: StatusGroup, state: string): string {
  return renderToStaticMarkup(
    createElement(I18nProvider, {
      lang,
      setLang: () => {},
      children: createElement(StatusPill, { group, state, values: VALUES }),
    })
  );
}
