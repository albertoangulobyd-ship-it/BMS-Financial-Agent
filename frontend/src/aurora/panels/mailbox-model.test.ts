// El buzon de facturas y la lectura automatica (paso 18, especificacion §6.1 a §6.4), sin React:
// el estado y su tono, los dias del certificado, el texto de cada correo y cada factura que
// espera, la parada de la automatica, la linea de Procesar, que nada sale en la nativa y el
// formulario de la autorizacion con las reglas del servidor.
import { describe, expect, it } from 'vitest';
import { rowTone, statusRule } from '@/components/status-pill';
import { MESSAGES } from '@/i18n';
import type { AutoReadingStatus, MailMessage, Mailbox } from '@/lib/api-types';
import { NBSP } from '@/lib/format';
import {
  AUTO_DEFAULTS,
  adviceFor,
  attachmentText,
  autoReadState,
  autoReadStateText,
  certState,
  certText,
  checkForm,
  exclusionText,
  foldedText,
  formValues,
  formatGigabytes,
  knownInstant,
  mailboxAvailable,
  mailboxErrorText,
  mailboxStateText,
  parseUsd,
  readableByHand,
  resumable,
  stopText,
  stripOf,
  systemRowsOf,
  usdInput,
  waitingCount,
} from './mailbox-model';

const nl = MESSAGES.nl;
const en = MESSAGES.en;
const es = MESSAGES.es;
const usd = (text: string) => `$${NBSP}${text}`;

function auto(extra: Partial<AutoReadingStatus> = {}): AutoReadingStatus {
  return {
    activa: true,
    autorizacion_id: 4,
    tope_dia_usd_micro: 2_000_000,
    tope_mes_usd_micro: 25_000_000,
    max_documentos: 20,
    max_por_documento_usd_micro: 500_000,
    fijada_en: '2026-11-20T09:00:00+00:00',
    gastado_hoy_usd_micro: 400_000,
    gastado_mes_usd_micro: 3_100_000,
    queda_hoy_usd_micro: 1_600_000,
    parada: null,
    motivo_codigo: null,
    desde: null,
    proximo_intento: null,
    hasta: null,
    pendientes: 3,
    elegibles: 3,
    elegible_mas_antigua: '2026-11-24T07:00:00+00:00',
    ...extra,
  };
}

function message(extra: Partial<MailMessage> = {}): MailMessage {
  return {
    mensaje_id: 9,
    recibido_en: '2026-11-24T07:00:00+00:00',
    carpeta: 'bandeja',
    remitente_doc: 'facturen@leverancier.example',
    asunto_doc: 'Factuur 118',
    adjuntos: [{ nombre_doc: 'factuur.pdf', resultado: 'documento', bytes: 120_000, documento_id: 31 }],
    ...extra,
  };
}

function mailbox(extra: Partial<Mailbox> = {}): Mailbox {
  return {
    configurado: true,
    entorno: 'contenedor',
    estado: 'al_dia',
    error_codigo: null,
    error_desde: null,
    ultima_consulta: '2026-11-24T09:41:00+00:00',
    ultima_buena: '2026-11-24T09:41:00+00:00',
    retenido_hasta: null,
    alcance: { comprobado_en: '2026-11-24T09:00:00+00:00', bien: true },
    credencial: { caduca_en: '2028-11-23T09:55:00+00:00', dias: 729 },
    aviso_volumen: false,
    hoy: { mensajes: 4, pdf_nuevos: 3, bytes: 400_000 },
    ciclo: { visto_en: '2026-11-24T09:40:00+00:00', variante: 'docker', pausado: false, pausado_desde: null, disco_libre_bytes: 80 * 1024 ** 3, disco_bajo: false },
    recientes: [message()],
    esperan_persona: { correos: [], correos_total: 0, documentos: [], documentos_total: 0 },
    lectura_automatica: { ...auto(), fijada_por: { id: 7, nombre: 'Ana Demo' }, cola: [] },
    ...extra,
  };
}

describe('solo Docker: en la nativa no hay correo ni lectura automatica', () => {
  it('lo dice el entorno de /api/v2/correo', () => {
    expect(mailboxAvailable(mailbox())).toBe(true);
    expect(mailboxAvailable(mailbox({ entorno: 'local' }))).toBe(true);
    expect(mailboxAvailable(mailbox({ entorno: 'nativo', configurado: false, estado: 'sin_configurar' }))).toBe(false);
    expect(mailboxAvailable(null)).toBe(false);
    expect(mailboxAvailable(undefined)).toBe(false);
  });

  it('en la nativa, ni la linea de Procesar (aunque la automatica diga algo)', () => {
    expect(stripOf(auto(), mailbox({ entorno: 'nativo' }), nl)).toBeNull();
    expect(stripOf(auto(), null, nl)).toBeNull();
  });

  it('en la nativa, Systeem se queda con sus filas de siempre y sin tarjetas del buzon (revision del paso 12)', () => {
    // Lo que ensena settings-panel.tsx: no tiene otra regla.
    expect(systemRowsOf(true, mailbox())).toEqual({ rows: ['company', 'isolation', 'people', 'backups', 'mailbox', 'autoRead'], mail: mailbox() });
    expect(systemRowsOf(false, mailbox({ entorno: 'local' })).rows).toEqual(['company', 'isolation', 'backups', 'mailbox', 'autoRead']);
    expect(systemRowsOf(true, mailbox({ entorno: 'nativo' }))).toEqual({ rows: ['company', 'isolation', 'people', 'backups'], mail: null });
    expect(systemRowsOf(false, mailbox({ entorno: 'nativo' }))).toEqual({ rows: ['company', 'isolation', 'backups'], mail: null });
    expect(systemRowsOf(true, null)).toEqual({ rows: ['company', 'isolation', 'people', 'backups'], mail: null });
  });

  it('en la nativa, Inicio no gana la fila de lo que espera, aunque la respuesta diga algo', () => {
    const waiting = { correos: [], correos_total: 2, documentos: [], documentos_total: 3 };
    expect(waitingCount(mailbox({ esperan_persona: waiting }))).toBe(5);
    expect(waitingCount(mailbox({ entorno: 'local', esperan_persona: waiting }))).toBe(5);
    expect(waitingCount(mailbox({ entorno: 'nativo', esperan_persona: waiting }))).toBe(0);
  });
});

describe('las listas de las tarjetas (revision del paso 12)', () => {
  it('si la API no las trae todas, no dice "Alle N": cuantas de cuantas, y abierta, cuantas faltan', () => {
    // 61 correos esperan; la API trae 50.
    expect(foldedText(50, 61, false, nl)).toEqual({ toggle: '50 van 61 tonen', more: null });
    expect(foldedText(50, 61, true, nl)).toEqual({ toggle: 'Minder tonen', more: 'en nog 11' });
    expect(foldedText(50, 51, true, en)).toEqual({ toggle: en.aurora.mailbox.showLess, more: 'and 1 more' });
    expect(foldedText(50, 61, false, es).toggle).toBe('Ver 50 de 61');
    // Todas: "Alle 12 tonen", sin "en nog".
    expect(foldedText(12, 12, false, nl)).toEqual({ toggle: 'Alle 12 tonen', more: null });
    expect(foldedText(12, 12, true, nl)).toEqual({ toggle: 'Minder tonen', more: null });
    // Cinco o menos: ni boton.
    expect(foldedText(5, 5, false, nl)).toEqual({ toggle: null, more: null });
    expect(foldedText(3, 3, false, nl)).toEqual({ toggle: null, more: null });
  });
});

describe('el buzon', () => {
  it('cada estado con su texto y su tono: al dia en verde, sin funcionar en rojo y latiendo', () => {
    const states = ['al_dia', 'retrasado', 'retenido', 'error', 'sin_configurar'] as const;
    expect(states.map((s) => mailboxStateText(s, nl))).toEqual(['Bijgewerkt', 'Al een tijd niet gecontroleerd', 'Voor vandaag gepauzeerd', 'Werkt niet', 'Niet ingesteld']);
    expect(states.map((s) => rowTone('correo', s))).toEqual(['paid', '', '', 'blocked', '']);
    expect(statusRule('correo', 'error')).toEqual({ variant: 'error', ping: true });
    expect(statusRule('correo', 'retrasado').variant).toBe('warning');
    expect(mailboxStateText('error', es)).toBe('No funciona');
  });

  it('cada error con lo que hay que hacer; sin configurar, como configurarlo; uno raro, "interno"', () => {
    const codes = ['credencial', 'reloj', 'permiso', 'alcance', 'control_no_existe', 'sin_conexion', 'limitado', 'aislamiento', 'salida', 'disco', 'interno'] as const;
    for (const t of [nl, en, es]) {
      const texts = codes.map((c) => mailboxErrorText(c, t));
      expect(new Set(texts).size).toBe(codes.length);
    }
    expect(mailboxErrorText('credencial', nl)).toContain('{mailCert}');
    // Solo Docker: ningun error del buzon manda a un script que solo tiene la nativa (revision
    // del paso 12: el aislamiento decia "Voer comprobar.bat uit").
    for (const t of [nl, en, es]) {
      for (const c of [...codes, 'sin_configurar']) expect(mailboxErrorText(c, t), c).not.toMatch(/\{check\}|comprobar\.bat|clave\.bat/);
    }
    expect(mailboxErrorText('sin_configurar', nl)).toBe(nl.aurora.mailbox.notSetUp);
    expect(mailboxErrorText('otra_cosa', en)).toBe(en.aurora.mailbox.errors.interno);
    expect(mailboxErrorText(null, nl)).toBeNull();
  });

  it('el certificado: ambar a 60 dias o menos, rojo caducado, con su fecha', () => {
    expect([null, 61, 60, 30, 0, -1].map((d) => certState(d))).toEqual([null, 'vigente', 'caduca_pronto', 'caduca_pronto', 'caduca_pronto', 'caducado']);
    expect(statusRule('certificado', 'caduca_pronto')).toEqual({ variant: 'warning', ping: false });
    expect(statusRule('certificado', 'caducado')).toEqual({ variant: 'error', ping: true });
    const caduca = '2027-01-03T10:00:00+00:00';
    expect(certText({ caduca_en: caduca, dias: 40 }, nl)).toBe('Certificaat verloopt over 40 dagen (03-01-2027)');
    expect(certText({ caduca_en: caduca, dias: 1 }, nl)).toBe('Certificaat verloopt over 1 dag (03-01-2027)');
    expect(certText({ caduca_en: caduca, dias: 0 }, en)).toBe('Certificate expires today (03-01-2027)');
    expect(certText({ caduca_en: caduca, dias: -2 }, es)).toBe('El certificado ha caducado: no entra nada');
    expect(certText({ caduca_en: null, dias: null }, nl)).toBeNull();
  });

  it('que texto toca a cada correo que espera: no deseado, sin PDF o lo de sus adjuntos', () => {
    expect(adviceFor(message({ carpeta: 'no_deseado', adjuntos: [{ nombre_doc: 'f.pdf', resultado: 'no_deseado', bytes: 1, documento_id: null }] }), nl)).toBe(nl.aurora.mailbox.junk);
    expect(adviceFor(message({ adjuntos: [] }), nl)).toBe(nl.aurora.mailbox.noPdf);
    expect(adviceFor(message({ adjuntos: [{ nombre_doc: 'f.xml', resultado: 'xml', bytes: 1, documento_id: null }] }), en)).toBe(en.aurora.mailbox.noPdf);
    // Con un PDF recibido y otro adjunto que no se trajo: lo dice ese adjunto.
    expect(adviceFor(message({ adjuntos: [...message().adjuntos, { nombre_doc: 'link', resultado: 'enlace', bytes: null, documento_id: null }] }), nl)).toBeNull();
    const results = ['documento', 'no_es_pdf', 'demasiado_grande', 'xml', 'reenvio', 'no_pdf', 'enlace', 'no_deseado', 'de_prueba', 'error'] as const;
    for (const t of [nl, en, es]) expect(new Set(results.map((r) => attachmentText(r, t))).size).toBe(results.length);
    expect(attachmentText('reenvio', nl)).toBe('Doorgestuurd als bijlage: stuur de pdf zelf door als gewone bijlage');
  });

  it('las facturas apartadas: por que, y si se pueden leer a mano desde Procesar', () => {
    expect(['grande', 'fallo', 'rechazado_api', 'persona'].map((c) => exclusionText(c, nl))).toEqual([
      'Te duur om vanzelf te lezen',
      'Twee keer mislukt bij automatisch lezen',
      'De API neemt deze pdf niet aan (te groot, te veel pagina’s of beveiligd)',
      'Door iemand apart gezet',
    ]);
    expect(['grande', 'fallo', 'rechazado_api', 'persona'].map(readableByHand)).toEqual([true, true, false, false]);
  });

  it('lo que espera a una persona (Inicio), el disco y las fechas que no se saben', () => {
    expect(waitingCount(mailbox({ esperan_persona: { correos: [], correos_total: 2, documentos: [], documentos_total: 3 } }))).toBe(5);
    expect(waitingCount(null)).toBe(0);
    expect(formatGigabytes(9.9 * 1024 ** 3)).toBe('9 GB');
    expect(formatGigabytes(null)).toBe('—');
    expect(knownInstant('1970-01-01T00:00:00Z')).toBeNull();
    expect(knownInstant('2026-11-24T07:00:00+00:00')).toBe('2026-11-24T07:00:00+00:00');
    expect(knownInstant(null)).toBeNull();
  });
});

describe('la lectura automatica', () => {
  it('apagada, encendida o por que no lee ahora', () => {
    expect(autoReadState(null)).toBe('apagada');
    expect(autoReadState(auto({ activa: false, parada: null }))).toBe('apagada');
    expect(autoReadState(auto())).toBe('encendida');
    expect(autoReadState(auto({ parada: 'persona' }))).toBe('pausada');
    expect(autoReadState(auto({ parada: 'volumen' }))).toBe('pausada');
    expect(autoReadState(auto({ parada: 'fallo' }))).toBe('fallo');
    expect(autoReadState(auto({ parada: 'limite_dia' }))).toBe('limite_dia');
    expect(autoReadState(auto({ parada: 'limite_mes' }))).toBe('limite_mes');
    expect((['encendida', 'apagada', 'pausada', 'fallo', 'limite_dia', 'limite_mes'] as const).map((s) => autoReadStateText(s, nl))).toEqual([
      'Aan',
      'Uit',
      'Gepauzeerd',
      'Gestopt na een fout',
      'Dagplafond bereikt',
      'Maandplafond bereikt',
    ]);
    expect(rowTone('lectura_automatica', 'encendida')).toBe('paid');
    expect(rowTone('lectura_automatica', 'fallo')).toBe('blocked');
  });

  it('la parada en una frase: el tope con lo que cuesta una factura, la pausa y el fallo con el proximo intento', () => {
    const now = new Date('2026-11-24T10:00:00+00:00');
    expect(stopText(auto(), nl, now)).toBeNull();
    expect(stopText(auto({ activa: false, parada: 'persona' }), nl, now)).toBeNull();
    expect(stopText(auto({ parada: 'limite_dia' }), nl, now)).toBe(
      `Er is vandaag minder dan ${usd('0,50')} over voor één factuur: de rest wordt morgen gelezen, of nu via Verwerken.`
    );
    expect(stopText(auto({ parada: 'limite_mes' }), en, now)).toContain('next month');
    expect(stopText(auto({ parada: 'persona' }), nl, now)).toBe(nl.aurora.autoRead.pausedPerson);
    expect(stopText(auto({ parada: 'volumen' }), es, now)).toBe(es.aurora.autoRead.pausedVolume);
    // El fallo de la automatica: el texto que sigue solo, y la hora en Amsterdam.
    expect(stopText(auto({ parada: 'fallo', motivo_codigo: 'saldo', proximo_intento: '2026-11-24T11:00:00+00:00' }), nl, now)).toBe(
      `Gestopt na een fout: ${nl.aurora.process.reasons.saldo} Volgende poging vandaag om 12:00.`
    );
    // Solo Docker: ningun fallo tecnico manda a clave.bat o comprobar.bat (revision del paso 12).
    for (const t of [nl, en, es]) {
      for (const code of ['salida', 'aislamiento', 'clave', 'contar', 'sin_tarifa', 'saldo', 'clave_rechazada', 'api_no_disponible'] as const) {
        expect(stopText(auto({ parada: 'fallo', motivo_codigo: code, proximo_intento: '2026-11-24T11:00:00+00:00' }), t, now), code).not.toMatch(/clave\.bat|comprobar\.bat/);
      }
    }
    expect(stopText(auto({ parada: 'fallo', motivo_codigo: 'clave_rechazada', proximo_intento: '2026-11-24T11:00:00+00:00' }), nl, now)).toContain(
      'docker\\secretos\\anthropic_api_key.txt'
    );
  });

  it('"Weer aanzetten" solo para una pausa (de una persona o de volumen)', () => {
    expect(resumable(auto({ parada: 'persona' }))).toBe(true);
    expect(resumable(auto({ parada: 'volumen' }))).toBe(true);
    for (const parada of [null, 'fallo', 'limite_dia', 'limite_mes'] as const) expect(resumable(auto({ parada })), String(parada)).toBe(false);
    expect(resumable(auto({ activa: false, parada: 'persona' }))).toBe(false);
  });

  it('la linea de Procesar: el estado, lo gastado hoy y la ultima consulta del buzon', () => {
    expect(stripOf(auto(), mailbox(), nl)).toBe(`Automatisch lezen: Aan · vandaag ${usd('0,40')} van ${usd('2,00')} · mailbox gecontroleerd om 10:41`);
    // Sin la de /api/v2/lectura, la de /api/v2/correo.
    expect(stripOf(null, mailbox(), en)).toBe(`Automatic reading: On · today ${usd('0,40')} of ${usd('2,00')} · mailbox checked at 10:41`);
    expect(stripOf(auto({ activa: false }), mailbox(), es)).toBe('Lectura automática: Apagada · buzón consultado a las 10:41');
    // Sin correo configurado y apagada: nada que decir.
    expect(stripOf(auto({ activa: false }), mailbox({ configurado: false, estado: 'sin_configurar', ultima_consulta: null }), nl)).toBeNull();
  });
});

describe('el formulario de la autorizacion (con admin)', () => {
  it('dolares en el campo y millonesimas en la orden', () => {
    expect(['2,00', '2.5', '$ 2', '0,50', '  20 ', '1.000', '2,005', 'x', '', '-1'].map(parseUsd)).toEqual([
      2_000_000,
      2_500_000,
      2_000_000,
      500_000,
      20_000_000,
      null,
      null,
      null,
      null,
      null,
    ]);
    expect([2_000_000, 500_000, 25_000_000, 123_456, null].map(usdInput)).toEqual(['2,00', '0,50', '25,00', '0,12', '']);
  });

  it('lo vigente, o lo que se propone si nunca se fijo (2 / 25 / 20 / 0,50)', () => {
    expect(formValues(null)).toEqual({ activa: '1', capDay: '2,00', capMonth: '25,00', maxDocs: '20', maxPerDoc: '0,50' });
    expect(AUTO_DEFAULTS.max_por_documento_usd_micro).toBe(500_000);
    expect(formValues(auto({ activa: false, tope_dia_usd_micro: 3_000_000, max_documentos: 5 }))).toEqual({
      activa: '0',
      capDay: '3,00',
      capMonth: '25,00',
      maxDocs: '5',
      maxPerDoc: '0,50',
    });
  });

  it('las reglas del servidor: el dia hasta 20, el mes del dia a 200, de 1 a 100 facturas, por factura hasta el dia', () => {
    const base = { activa: '1', capDay: '2,00', capMonth: '25,00', maxDocs: '20', maxPerDoc: '0,50' };
    expect(checkForm(base, nl)).toEqual({
      values: { activa: 1, tope_dia_usd_micro: 2_000_000, tope_mes_usd_micro: 25_000_000, max_documentos: 20, max_por_documento_usd_micro: 500_000 },
    });
    expect(checkForm({ ...base, activa: '0' }, nl)).toMatchObject({ values: { activa: 0 } });
    const r = nl.aurora.autoRead;
    expect(checkForm({ ...base, capDay: '20,01' }, nl)).toEqual({ problem: r.invalidDay });
    expect(checkForm({ ...base, capDay: '20,00', capMonth: '20,00', maxPerDoc: '20,00' }, nl)).toHaveProperty('values');
    expect(checkForm({ ...base, capMonth: '1,99' }, nl)).toEqual({ problem: r.invalidMonth });
    expect(checkForm({ ...base, capMonth: '200,01' }, nl)).toEqual({ problem: r.invalidMonth });
    expect(checkForm({ ...base, maxDocs: '0' }, nl)).toEqual({ problem: r.invalidDocs });
    expect(checkForm({ ...base, maxDocs: '101' }, nl)).toEqual({ problem: r.invalidDocs });
    expect(checkForm({ ...base, maxDocs: '2,5' }, nl)).toEqual({ problem: r.invalidDocs });
    expect(checkForm({ ...base, maxPerDoc: '2,01' }, nl)).toEqual({ problem: r.invalidPerDoc });
    expect(checkForm({ ...base, capDay: 'twee' }, nl)).toEqual({ problem: 'Plafond per dag: vul een bedrag in dollars in, bijvoorbeeld 2,00.' });
    expect(checkForm({ ...base, maxPerDoc: '0' }, nl)).toEqual({ problem: 'Maximaal per factuur: vul een bedrag in dollars in, bijvoorbeeld 2,00.' });
  });
});
