// El buzon de facturas y la lectura automatica (paso 18, especificacion §6.1 a §6.4), sin React:
// de lo que dice GET /api/v2/correo (y `automatica` de GET /api/v2/lectura) a lo que se ve en
// Instellingen › Systeem, en la linea de Procesar y en la de Inicio. Lo prueba
// mailbox-model.test.ts.
//
// Solo Docker (decision del dueno del 24-11-2026): la instalacion nativa no trae correo ni lee
// sola. Alli /api/v2/correo dice `entorno: 'nativo'` y la app no ensena nada del correo ni de la
// lectura automatica: ni las filas, ni la linea de Procesar, ni la de Inicio.
//
// Lo que llega del buzon (remitente, asunto, nombres de los adjuntos) es texto de quien manda el
// correo: va al DOM como texto, con data-proper-name y la etiqueta "niet gecontroleerd", y nunca
// decide nada. Aqui solo se eligen textos de la app por los codigos de la API.
import { fmt, type Messages } from '@/i18n';
import type {
  AttachmentResult,
  AutoReadingStatus,
  ExclusionReason,
  MailMessage,
  Mailbox,
  MailboxError,
  MailboxState,
} from '@/lib/api-types';
import { NO_VALUE, formatTimeOfDay, formatUsdMicro } from '@/lib/format';
import { reasonOf, timeOf, whenOf } from '../processing/process-texts';

/** Si esta instalacion trae correo: en Docker (y en local, la de las pruebas) si; en la nativa,
 *  no (ni correo ni lectura automatica). Sin la respuesta, tampoco. */
export function mailboxAvailable(m: Pick<Mailbox, 'entorno'> | null | undefined): boolean {
  return !!m && m.entorno !== 'nativo';
}

/** Las filas de Instellingen › Systeem. */
export type SystemRow = 'company' | 'isolation' | 'people' | 'backups' | 'mailbox' | 'autoRead';

/** Systeem: sus filas (Personen solo con admin, que es quien recibe la lista) y el buzon que se
 *  ensena en sus dos filas y sus tarjetas. En la nativa (o sin respuesta de /api/v2/correo), ni
 *  las dos filas ni el buzon: Systeem se queda como estaba (decision del dueno: solo Docker). */
export function systemRowsOf(people: boolean, mailbox: Mailbox | null | undefined): { rows: SystemRow[]; mail: Mailbox | null } {
  const mail = mailbox && mailboxAvailable(mailbox) ? mailbox : null;
  const rows: SystemRow[] = ['company', 'isolation', ...(people ? (['people'] as const) : []), 'backups', ...(mail ? (['mailbox', 'autoRead'] as const) : [])];
  return { rows, mail };
}

// ---------------------------------------------------------------- el buzon

/** El estado del buzon en palabras (Facturenmailbox: Bijgewerkt, Werkt niet...). */
export function mailboxStateText(state: MailboxState, t: Messages): string {
  const s = t.status.mailbox;
  return { al_dia: s.al_dia, retrasado: s.retrasado, retenido: s.retenido, error: s.error, sin_configurar: s.sin_configurar }[state] ?? state;
}

/** Lo que dice cada error del buzon (la lista cerrada de §3.7), con lo que hay que hacer. */
export function mailboxErrorText(code: MailboxError | string | null | undefined, t: Messages): string | null {
  if (!code) return null;
  const e = t.aurora.mailbox.errors;
  const texts: Record<string, string> = {
    sin_configurar: t.aurora.mailbox.notSetUp,
    credencial: e.credencial,
    reloj: e.reloj,
    permiso: e.permiso,
    alcance: e.alcance,
    control_no_existe: e.control_no_existe,
    sin_conexion: e.sin_conexion,
    limitado: e.limitado,
    aislamiento: e.aislamiento,
    salida: e.salida,
    disco: e.disco,
    interno: e.interno,
  };
  return texts[code] ?? e.interno;
}

/** El aviso del certificado empieza a 60 dias (ambar); la banda roja del servidor, a 30. */
export const CERT_WARN_DAYS = 60;

export type CertState = 'vigente' | 'caduca_pronto' | 'caducado';

/** El certificado por los dias que le quedan (negativos: caducado). */
export function certState(days: number | null | undefined): CertState | null {
  if (days === null || days === undefined) return null;
  if (days < 0) return 'caducado';
  return days <= CERT_WARN_DAYS ? 'caduca_pronto' : 'vigente';
}

/** "Certificaat verloopt over 40 dagen (03-01-2027)", o que ya caduco. */
export function certText(credencial: Mailbox['credencial'], t: Messages): string | null {
  const m = t.aurora.mailbox;
  const { dias, caduca_en } = credencial;
  if (dias === null) return null;
  if (dias < 0) return m.certExpired;
  const date = formatTimeOfDay(caduca_en)?.date ?? NO_VALUE;
  if (dias === 0) return fmt(m.certExpiresToday, { date });
  if (dias === 1) return fmt(m.certExpiresOne, { date });
  return fmt(m.certExpires, { days: dias, date });
}

/** Lo que se pudo hacer con un adjunto. */
export function attachmentText(result: AttachmentResult | string, t: Messages): string {
  const a = t.aurora.mailbox.attachment;
  const texts: Record<string, string> = {
    documento: a.documento,
    no_es_pdf: a.no_es_pdf,
    demasiado_grande: a.demasiado_grande,
    xml: a.xml,
    reenvio: a.reenvio,
    no_pdf: a.no_pdf,
    enlace: a.enlace,
    no_deseado: a.no_deseado,
    de_prueba: a.de_prueba,
    error: a.error,
  };
  return texts[result] ?? a.error;
}

/** Que hacer con un correo que el programa no pudo leer (ademas de lo de cada adjunto): el de
 *  "no deseado", pasarlo a la bandeja en Outlook; uno de la bandeja sin ningun PDF, traer la
 *  factura a mano. */
export function adviceFor(message: Pick<MailMessage, 'carpeta' | 'adjuntos'>, t: Messages): string | null {
  if (message.carpeta === 'no_deseado') return t.aurora.mailbox.junk;
  if (!message.adjuntos.some((a) => a.resultado === 'documento')) return t.aurora.mailbox.noPdf;
  return null;
}

/** Por que una factura no se lee sola. */
export function exclusionText(code: ExclusionReason | string, t: Messages): string {
  const x = t.aurora.mailbox.excluded;
  const texts: Record<string, string> = { grande: x.grande, fallo: x.fallo, rechazado_api: x.rechazado_api, persona: x.persona };
  return texts[code] ?? code;
}

/** Lo grande y lo que fallo leyendose solo, si se puede leer desde Procesar (con el si de una
 *  persona); lo que la API no acepta, no (lectura_automatica.FUERA_DE_PROCESAR). */
export function readableByHand(code: ExclusionReason | string): boolean {
  return code === 'grande' || code === 'fallo';
}

/** Un instante que se sabe: lo de antes de 2000 es "no se sabe" (el correo escribe
 *  1970-01-01T00:00:00Z cuando Microsoft no da una fecha que se pueda leer, §3.8 paso 4). */
export function knownInstant(value: string | null | undefined): string | null {
  return value && /^\d{4}-/.test(value) && value.slice(0, 4) >= '2000' ? value : null;
}

/** Cuantos correos y facturas esperan a una persona (la linea de Inicio). En la nativa, 0: alli
 *  no hay correo y Inicio no gana la fila. */
export function waitingCount(m: Pick<Mailbox, 'entorno' | 'esperan_persona'> | null | undefined): number {
  if (!m || !mailboxAvailable(m)) return 0;
  return m.esperan_persona.correos_total + m.esperan_persona.documentos_total;
}

/** Lo que dice una lista plegada de la tarjeta (los 5 primeros y el boton). `shown`: las filas
 *  que trajo la API (como mucho 50); `total`: las que hay. Si la API no las trajo todas, el
 *  boton no dice "Alle N" (escondia las demas) sino cuantas de cuantas, y abierta dice cuantas
 *  faltan. */
export function foldedText(shown: number, total: number, open: boolean, t: Messages, first = 5): { toggle: string | null; more: string | null } {
  const b = t.aurora.mailbox;
  const rest = Math.max(0, total - shown);
  const toggle = shown <= first ? null : open ? b.showLess : rest > 0 ? fmt(b.showSome, { n: shown, total }) : fmt(b.showAll, { n: shown });
  const more = open || shown <= first ? (rest === 0 ? null : rest === 1 ? t.why.moreOne : fmt(t.why.more, { n: rest })) : null;
  return { toggle, more };
}

/** El espacio libre en GB enteros, como la banda del servidor ("12 GB"). */
export function formatGigabytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || bytes < 0) return NO_VALUE;
  return `${Math.floor(bytes / 1024 ** 3)} GB`;
}

// ---------------------------------------------------------------- la lectura automatica

export type AutoReadState = 'encendida' | 'apagada' | 'pausada' | 'fallo' | 'limite_dia' | 'limite_mes';

/** La lectura automatica en una palabra: apagada, encendida o por que no lee ahora. */
export function autoReadState(a: Pick<AutoReadingStatus, 'activa' | 'parada'> | null | undefined): AutoReadState {
  if (!a || !a.activa) return 'apagada';
  switch (a.parada) {
    case 'persona':
    case 'volumen':
      return 'pausada';
    case 'fallo':
      return 'fallo';
    case 'limite_dia':
      return 'limite_dia';
    case 'limite_mes':
      return 'limite_mes';
    default:
      return 'encendida';
  }
}

/** Esa palabra en el idioma de la persona (Aan, Uit, Gepauzeerd...). */
export function autoReadStateText(state: AutoReadState, t: Messages): string {
  const s = t.status.autoRead;
  return { encendida: s.encendida, apagada: s.apagada, pausada: s.pausada, fallo: s.fallo, limite_dia: s.limite_dia, limite_mes: s.limite_mes }[state];
}

/** Por que esta parada, con lo que hace falta (§6.4); null si lee (o si esta apagada). */
export function stopText(a: AutoReadingStatus | null | undefined, t: Messages, now: Date = new Date()): string | null {
  if (!a || !a.activa || !a.parada) return null;
  const r = t.aurora.autoRead;
  switch (a.parada) {
    case 'persona':
      return r.pausedPerson;
    case 'volumen':
      return r.pausedVolume;
    case 'fallo':
      return fmt(r.failed, { reason: reasonOf(a.motivo_codigo, t, 'automatica'), when: whenOf(a.proximo_intento, t, now) });
    case 'limite_dia':
      return fmt(r.limitDay, { max: formatUsdMicro(a.max_por_documento_usd_micro) });
    case 'limite_mes':
      return fmt(r.limitMonth, { max: formatUsdMicro(a.max_por_documento_usd_micro) });
  }
  return null;
}

/** Una pausa que una persona puede quitar con "Weer aanzetten" (reanudar_lectura_automatica). */
export function resumable(a: Pick<AutoReadingStatus, 'activa' | 'parada'> | null | undefined): boolean {
  return !!a && a.activa && (a.parada === 'persona' || a.parada === 'volumen');
}

/** La linea de Procesar, encima de la escena: el estado de la automatica, lo gastado hoy y la
 *  ultima consulta del buzon. Sin correo (la nativa), o sin correo configurado y con la
 *  automatica apagada, nada. `auto`: la de GET /api/v2/lectura, que se consulta cada 2 s (si
 *  no, la de /api/v2/correo). */
export function stripOf(auto: AutoReadingStatus | null | undefined, mailbox: Mailbox | null | undefined, t: Messages): string | null {
  if (!mailbox || !mailboxAvailable(mailbox)) return null;
  const a = auto ?? mailbox.lectura_automatica;
  if (!mailbox.configurado && !a.activa) return null;
  const p = t.aurora.process;
  const state = autoReadStateText(autoReadState(a), t);
  const time = timeOf(mailbox.ultima_consulta);
  if (!a.activa) return fmt(p.stripOff, { state, time });
  return fmt(p.strip, { state, spent: formatUsdMicro(a.gastado_hoy_usd_micro), cap: formatUsdMicro(a.tope_dia_usd_micro), time });
}

// ---------------------------------------------------------------- el formulario (con admin)

/** Lo que la app propone al encenderla por primera vez (§5.1; lectura_automatica.POR_DEFECTO). */
export const AUTO_DEFAULTS = {
  tope_dia_usd_micro: 2_000_000,
  tope_mes_usd_micro: 25_000_000,
  max_documentos: 20,
  max_por_documento_usd_micro: 500_000,
} as const;

/** Los techos de la base (0019; lectura_automatica.TECHO_*). */
export const AUTO_LIMITS = { dayMax: 20_000_000, monthMax: 200_000_000, docsMax: 100 } as const;

const MICRO_PER_CENT = 10_000;

/** Lo que se escribe en un campo de dolares ("2,00", "2.5", "$ 2", "0,50") en millonesimas, o
 *  null si no es un importe (como mucho dos decimales: los centimos). */
export function parseUsd(text: string): number | null {
  const s = text.replace(/[\s $]/g, '');
  const m = /^(\d{1,6})(?:[.,](\d{1,2}))?$/.exec(s);
  if (!m) return null;
  const cents = Number(m[1]) * 100 + Number(((m[2] ?? '') + '00').slice(0, 2));
  return cents * MICRO_PER_CENT;
}

/** Millonesimas de dolar como se escriben en el campo: "2,00" (al centimo). */
export function usdInput(micro: number | null | undefined): string {
  if (micro === null || micro === undefined || micro < 0) return '';
  const cents = Math.round(micro / MICRO_PER_CENT);
  return `${Math.floor(cents / 100)},${String(cents % 100).padStart(2, '0')}`;
}

export interface AutoReadForm {
  activa: string;
  capDay: string;
  capMonth: string;
  maxDocs: string;
  maxPerDoc: string;
}

/** Lo que el formulario ensena al abrirse: lo vigente, o lo que se propone si nunca se fijo. */
export function formValues(a: AutoReadingStatus | null | undefined): AutoReadForm {
  const set = a && a.autorizacion_id !== null;
  return {
    activa: set && !a.activa ? '0' : '1',
    capDay: usdInput(set ? a.tope_dia_usd_micro : AUTO_DEFAULTS.tope_dia_usd_micro),
    capMonth: usdInput(set ? a.tope_mes_usd_micro : AUTO_DEFAULTS.tope_mes_usd_micro),
    maxDocs: String(set ? a.max_documentos : AUTO_DEFAULTS.max_documentos),
    maxPerDoc: usdInput(set ? a.max_por_documento_usd_micro : AUTO_DEFAULTS.max_por_documento_usd_micro),
  };
}

export interface AutoReadValues {
  activa: 0 | 1;
  tope_dia_usd_micro: number;
  tope_mes_usd_micro: number;
  max_documentos: number;
  max_por_documento_usd_micro: number;
}

/** Los cinco valores de fijar_lectura_automatica, con las reglas del servidor
 *  (lectura_automatica.validar), o el texto de lo que no vale. El servidor vuelve a mirarlo. */
export function checkForm(v: AutoReadForm, t: Messages): { values: AutoReadValues } | { problem: string } {
  const r = t.aurora.autoRead;
  const amount = (text: string, label: string): number | { problem: string } => {
    const micro = parseUsd(text);
    return micro === null || micro <= 0 ? { problem: fmt(r.invalidAmount, { field: label }) } : micro;
  };
  const day = amount(v.capDay, r.capDay);
  if (typeof day !== 'number') return day;
  const month = amount(v.capMonth, r.capMonth);
  if (typeof month !== 'number') return month;
  const perDoc = amount(v.maxPerDoc, r.maxPerDoc);
  if (typeof perDoc !== 'number') return perDoc;
  if (day > AUTO_LIMITS.dayMax) return { problem: r.invalidDay };
  if (month < day || month > AUTO_LIMITS.monthMax) return { problem: r.invalidMonth };
  const docs = /^\d{1,3}$/.test(v.maxDocs.trim()) ? Number(v.maxDocs.trim()) : NaN;
  if (!(docs >= 1 && docs <= AUTO_LIMITS.docsMax)) return { problem: r.invalidDocs };
  if (perDoc > day) return { problem: r.invalidPerDoc };
  return {
    values: {
      activa: v.activa === '0' ? 0 : 1,
      tope_dia_usd_micro: day,
      tope_mes_usd_micro: month,
      max_documentos: docs,
      max_por_documento_usd_micro: perDoc,
    },
  };
}
