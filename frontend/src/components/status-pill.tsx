// Un estado del dominio con el componente Status del dueno (components/ui/status.tsx):
// la pastilla tintada con su punto y SIEMPRE su texto (nunca solo color). Aqui, y solo
// aqui, se decide que variante lleva cada estado y si su punto late: las pantallas dicen
// el grupo y el valor (tal como los manda la API y los nombran los catalogos) y nunca
// eligen una variante.
//
// El punto late SOLO en lo que pide hacer algo ya (bloqueada, urgente, una cuenta por
// verificar, el aislamiento que falla o falta). Todo lo demas lleva el punto quieto: una
// lista de quince facturas no parpadea entera ("minimalista y facil de entender").
// Y ademas, solo en UN sitio por pantalla (PingScope): en las listas, las tarjetas y las
// fichas de relaciones las prioridades van quietas (DataTable y SummaryCard lo ponen);
// late la cabecera de la ficha que se tiene delante (una factura bloqueada o urgente), las
// filas Geblokkeerd de la Werklijst (la lista donde se trabaja), una cuenta por llamar en
// IBAN-controles y el aislamiento.
//
// Las etiquetas salen de los catalogos de Python (src/bms_agent/textos, via
// i18n/domain.ts) y, para lo que no es del dominio (la marca de prueba, el IBAN tecleado,
// el aislamiento, la frescura...), de los textos de la app (i18n/nl.ts y en.ts, status).
import { createContext, useContext, type ReactNode } from 'react';
import type * as React from 'react';
import { Status, StatusIndicator, StatusLabel } from '@/components/ui/status';
import { fmt, useT, type Lang, type Messages } from '@/i18n';
import { priorityLabel, qualityText, severityLabel, severityMeaning, stateLabel, verdictPartText } from '@/i18n/domain';

export type StatusVariant = 'default' | 'success' | 'error' | 'warning' | 'info';

export interface StatusRule {
  variant: StatusVariant;
  /** El punto late: solo lo que pide hacer algo ya. */
  ping: boolean;
}

const quieto = (variant: StatusVariant): StatusRule => ({ variant, ping: false });
const late = (variant: StatusVariant): StatusRule => ({ variant, ping: true });

/**
 * Cada grupo de estados con sus valores. Las claves son las de la API y los catalogos
 * (estados.pago, prioridad, severidades, calidad...); los pocos valores que la API no
 * manda tal cual se derivan en la pantalla y estan dichos al lado.
 */
export const STATUS_RULES = {
  /** La prioridad de una factura, una excepcion o una PO (catalogo: prioridad). */
  prioridad: {
    bloqueada: late('error'),
    urgente: late('warning'),
    atencion: quieto('info'),
    normal: quieto('default'),
  },
  /** Lo que dice el sistema de una factura (catalogo: veredicto). "limpia" nunca es "aprobada". */
  veredicto: {
    limpia: quieto('success'),
    limpia_sin_datos: quieto('success'),
    objeciones: quieto('warning'),
    campos: quieto('warning'),
    aceptadas: quieto('default'),
  },
  /** Lo que hace un hallazgo (catalogo: severidades). */
  severidad: {
    bloqueo: quieto('error'),
    retencion: quieto('warning'),
    aviso: quieto('info'),
  },
  /** El estado de un hallazgo (catalogo: estados.hallazgo). */
  hallazgo: {
    abierto: quieto('warning'),
    desaparecido: quieto('info'),
    aceptado: quieto('default'),
    cerrado: quieto('success'),
    resuelto: quieto('success'),
  },
  /** El pago (catalogo: estados.pago). */
  pago: {
    vencida: quieto('error'),
    pendiente: quieto('default'),
    pagada: quieto('success'),
    anulada: quieto('default'),
    acreditada: quieto('default'),
  },
  /** Un pago de una factura (catalogo: estados.aplicacion, paso 16): lo que el banco propuso
   *  espera a una persona; lo confirmado cuenta; lo retirado se guarda y no cuenta. */
  aplicacion: {
    propuesta: quieto('warning'),
    confirmada: quieto('success'),
    retirada: quieto('default'),
  },
  /** El control de una persona (catalogo: estados.revision). */
  revision: {
    necesita_revision: quieto('warning'),
    sin_revisar: quieto('default'),
    revisada: quieto('success'),
  },
  /** Una excepcion (catalogo: estados.excepcion). */
  excepcion: {
    abierta: quieto('warning'),
    asignada: quieto('info'),
    esperando_externo: quieto('info'),
    resuelta: quieto('success'),
  },
  /** La calidad de un campo (catalogo: calidad). */
  calidad: {
    faltante: quieto('error'),
    dudoso: quieto('warning'),
    discrepancia: quieto('warning'),
    anomalia: quieto('info'),
    verificado: quieto('success'),
  },
  /** Una cuenta bancaria del registro (catalogo: estados.cuenta). */
  cuenta: {
    registrada: late('warning'),
    heredada: quieto('warning'),
    verificada: quieto('success'),
    atestada: quieto('success'),
    rechazada: quieto('error'),
  },
  /** Un control de IBAN sin cuenta en el registro (un aviso F de una factura), y el
   *  telefono de los datos maestros. Derivados en IBAN-controles. */
  iban_control: {
    por_verificar: late('warning'),
    sin_telefono: quieto('error'),
  },
  /** El IBAN que se teclea al verificar, contra el encontrado (derivado en el dialogo). */
  iban_tecleado: {
    coincide: quieto('success'),
    difiere: quieto('error'),
  },
  /** Una relacion entre facturas (catalogo: estados.relacion). */
  relacion: {
    propuesta: quieto('warning'),
    confirmada: quieto('success'),
    rechazada: quieto('default'),
  },
  /** Un turno de la planning (catalogo: estados.turno). */
  turno: {
    planificado: quieto('default'),
    realizado: quieto('info'),
    validado: quieto('success'),
    cancelado: quieto('default'),
  },
  /** La comprobacion del aislamiento de un papel (/api/v2/aislamiento, papeles[].estado:
   *  correcto, falla, sin_comprobar o caducada, de aislamiento.problemas_de). */
  aislamiento: {
    correcto: quieto('success'),
    falla: late('error'),
    sin_comprobar: late('error'),
    caducada: late('error'),
  },
  /** Lo fresco de una fuente (/api/v2/fuentes: caducada false, true o null). */
  fuente: {
    al_dia: quieto('success'),
    caducada: quieto('warning'),
    sin_limite: quieto('default'),
  },
  /** Un trimestre del BTW (catalogo: estados.btw) y su plazo (derivado de
   *  dias_para_limite: cerca, 14 dias o menos; vencido, pasado y sin presentar). */
  btw: {
    abierto: quieto('default'),
    listo_revision: quieto('info'),
    presentado: quieto('success'),
    plazo_cerca: quieto('warning'),
    plazo_vencido: quieto('error'),
  },
  /** Si la configuracion del btw se confirmo con el asesor (btw.configuracion.confirmada). */
  btw_config: {
    confirmada: quieto('success'),
    sin_confirmar: quieto('warning'),
  },
  /** Los datos de BM Support BV que usan las reglas (/api/v2/empresa: completa). */
  empresa: {
    completa: quieto('success'),
    incompleta: quieto('warning'),
  },
  /** Una PO (catalogo: estados.po). */
  po: {
    activa: quieto('default'),
    cerrada: quieto('default'),
    caducada: quieto('default'),
  },
  /** Lo que avisa de una PO junto a sus cifras: el codigo de su regla (catalogo: reglas).
   *  Lleva el color de la gravedad de ese aviso (severidad), el mismo que tiene justo debajo
   *  en "Wat aandacht nodig heeft" y en cualquier otra pantalla: un aviso, un color. Avisan
   *  (aviso: info) bijna op P5, verloopt P7, gepland P8 y eerder op P9; retienen
   *  (retencion: warning) la factura por encima de lo que queda P4, la PO gastada P6 y lo
   *  esperado por encima P10 (reglas/catalogo.py). */
  po_senal: {
    P5: quieto('info'),
    P7: quieto('info'),
    P8: quieto('info'),
    P9: quieto('info'),
    P10: quieto('warning'),
    P4: quieto('warning'),
    P6: quieto('warning'),
  },
  /** Una importacion (catalogo: estados.importacion). */
  importacion: {
    en_curso: quieto('info'),
    aceptada: quieto('success'),
    parcial: quieto('warning'),
    rechazada: quieto('error'),
  },
  /** La prueba de una importacion y su resultado (derivado: sin avisos, con avisos, con
   *  errores). */
  importar_prueba: {
    ok: quieto('success'),
    avisos: quieto('warning'),
    errores: quieto('error'),
  },
  /** Una pasada del lector de PDF (derivado: en curso, terminada, con errores). */
  lectura: {
    en_curso: quieto('info'),
    terminada: quieto('success'),
    con_errores: quieto('error'),
  },
  /** La marca TESTGEGEVENS de la cabecera (X-BMS-Entorno: demo). */
  datos_prueba: {
    demo: quieto('warning'),
  },
} as const satisfies Record<string, Record<string, StatusRule>>;

export type StatusGroup = keyof typeof STATUS_RULES;
export const STATUS_GROUPS = Object.keys(STATUS_RULES) as StatusGroup[];

const UNKNOWN: StatusRule = quieto('default');

function own<T extends object>(o: T, k: string): boolean {
  return Object.prototype.hasOwnProperty.call(o, k);
}

/** La regla de un estado; uno que no se conoce va en gris y quieto (con su texto). */
export function statusRule(group: StatusGroup, state: string | null | undefined): StatusRule {
  const rules = STATUS_RULES[group] as Record<string, StatusRule>;
  return typeof state === 'string' && own(rules, state) ? rules[state]! : UNKNOWN;
}

export type StatusValues = Record<string, string | number>;

/** El texto de un estado, en el idioma pedido; null si no hay. */
export function statusLabel(
  lang: Lang,
  t: Messages,
  group: StatusGroup,
  state: string | null | undefined,
  values: StatusValues = {}
): string | null {
  if (typeof state !== 'string') return null;
  const app = (section: Record<string, string>) => (own(section, state) ? section[state]! : null);
  switch (group) {
    case 'prioridad':
      return priorityLabel(lang, state);
    case 'severidad':
      return severityLabel(lang, state);
    case 'calidad':
      return qualityText(lang, state)?.label ?? null;
    case 'veredicto':
      return verdictPartText(lang, state, values);
    case 'po_senal':
      // Corto (va entre las cifras de la ficha); el nombre entero de la regla esta en la
      // lista de lo que necesita atencion, justo debajo.
      return own(STATUS_RULES.po_senal, state) ? app(t.status.poSignal) : null;
    case 'excepcion': {
      const who = values.esperando_a;
      if (state === 'esperando_externo' && typeof who === 'string' && who) {
        return fmt(t.exceptions.waitingOn, { who: stateLabel(lang, 'esperando_a', who) ?? who });
      }
      return stateLabel(lang, 'excepcion', state);
    }
    case 'btw': {
      // Con los dias que quedan ({n}), el plazo cercano dice cuantos: "Nog 5 dagen".
      if (state === 'plazo_cerca' && typeof values.n === 'number') {
        return fmt(values.n === 1 ? t.status.vat.dayLeft : t.status.vat.daysLeft, { n: values.n });
      }
      return state === 'plazo_cerca' || state === 'plazo_vencido' ? app(t.status.vat) : stateLabel(lang, 'btw', state);
    }
    case 'btw_config':
      return app(t.status.vatConfig);
    case 'empresa':
      return app(t.status.company);
    case 'iban_control':
      return app(t.status.ibanControl);
    case 'iban_tecleado':
      return app(t.status.ibanTyped);
    case 'aislamiento':
      return app(t.status.isolation);
    case 'fuente':
      // Con su limite ({n}: "5 werkdagen"), lo caducado dice de cuanto: "Te oud (meer dan ...)".
      if (state === 'caducada' && values.n !== undefined) return fmt(t.importing.stale, { n: values.n });
      return app(t.status.freshness);
    case 'importar_prueba':
      return app(t.status.importCheck);
    case 'lectura':
      return app(t.status.reading);
    case 'datos_prueba':
      return state === 'demo' ? t.testData.chip : null;
    case 'pago':
    case 'aplicacion':
    case 'revision':
    case 'hallazgo':
    case 'cuenta':
    case 'relacion':
    case 'turno':
    case 'po':
    case 'importacion':
      return stateLabel(lang, group, state);
  }
}

/**
 * Donde puede latir un punto, de fuera a dentro: 'all' (lo de siempre: la cabecera de una
 * ficha, IBAN-controles, el aislamiento), 'blocked' (solo una prioridad bloqueada: las filas
 * de la Werklijst) o 'none' (todo quieto: listas, tarjetas, fichas de relaciones).
 */
export type PingScopeValue = 'all' | 'blocked' | 'none';

const PingContext = createContext<PingScopeValue>('all');

export function PingScope({ scope, children }: { scope: PingScopeValue; children: ReactNode }) {
  return <PingContext.Provider value={scope}>{children}</PingContext.Provider>;
}

/** Si el punto late: la regla del estado y, encima, donde esta la pastilla. */
export function pings(rule: StatusRule, scope: PingScopeValue, group: StatusGroup, state: string | null | undefined): boolean {
  if (!rule.ping || scope === 'none') return false;
  if (scope === 'blocked') return group === 'prioridad' && state === 'bloqueada';
  return true;
}

export interface StatusPillProps extends Omit<React.ComponentProps<'div'>, 'children'> {
  group: StatusGroup;
  state: string | null | undefined;
  /** Las cifras o nombres que lleva el texto (el veredicto, "Wacht op de leverancier"). */
  values?: StatusValues;
}

/** Un estado del dominio, como lo quiere el dueno: pastilla, punto y texto. */
export function StatusPill({ group, state, values, ...props }: StatusPillProps) {
  const { lang, t } = useT();
  const scope = useContext(PingContext);
  const rule = statusRule(group, state);
  const label = statusLabel(lang, t, group, state, values) ?? t.common.unknown;
  // La gravedad de un aviso dice ademas, al pasar el raton, que hace con la factura.
  const hint = group === 'severidad' ? severityMeaning(lang, state) : null;
  return (
    <Status variant={rule.variant} title={hint ?? undefined} {...props}>
      <StatusIndicator className={pings(rule, scope, group, state) ? undefined : 'before:animate-none'} />
      <StatusLabel>{label}</StatusLabel>
    </Status>
  );
}
