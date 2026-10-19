// Como se ensena y como se edita el valor de un campo de la ficha, segun su tipo (los de
// campos.py): importes, horas, tarifas y porcentajes en notacion neerlandesa desde sus
// enteros, fechas dd-mm-aaaa, si/no en el idioma de la app y los codigos (enum) con su
// nombre del catalogo. El texto de un documento se ensena tal cual.
import type { Lang } from '@/i18n';
import { stateLabel, templateCatalog } from '@/i18n/domain';
import { formatWith } from '@/i18n/templates';
import type { FieldInfo, Json } from './api-types';
import { NO_VALUE, formatDate, formatHours, formatMoney, formatPercentFromBasisPoints } from './format';

/** El grupo de estados del catalogo que nombra los valores de un campo enum. */
const ENUM_GROUP: Record<string, Parameters<typeof stateLabel>[1]> = {
  tipo: 'tipo_factura',
  sentido: 'sentido',
  origen: 'origen_factura',
  tratamiento_iva: 'tratamiento_iva',
  clase: 'clase_referencia',
};

export function enumGroup(field: string): Parameters<typeof stateLabel>[1] | null {
  return ENUM_GROUP[field] ?? null;
}

type Num = number | string | null | undefined;

export function formatFieldValue(field: Pick<FieldInfo, 'campo' | 'tipo'>, value: Json | undefined, lang: Lang): string {
  if (value === null || value === undefined || value === '') return NO_VALUE;
  switch (field.tipo) {
    case 'cent':
      return formatMoney(value as Num);
    case 'mil':
      return formatHours(value as Num);
    case 'pb':
      return formatPercentFromBasisPoints(value as Num);
    case 'e4':
      return formatWith('tarifa', value, templateCatalog(lang));
    case 'fecha':
      return typeof value === 'string' ? formatDate(value) : NO_VALUE;
    case 'bool': {
      const c = templateCatalog(lang).comun;
      return value === true || value === 1 ? c.si : c.no;
    }
    case 'enum': {
      const group = enumGroup(field.campo);
      return (group && stateLabel(lang, group, String(value))) || String(value);
    }
    default:
      // El IBAN del documento, en grupos de cuatro para leerlo (a ese IBAN no se paga).
      if (field.campo === 'iban_doc' && typeof value === 'string') return formatWith('iban', value, templateCatalog(lang));
      return String(value);
  }
}

/** Lo que va en el campo de texto al editar: el valor sin separador de miles y con coma
 *  decimal (2902,79), que es lo que el servidor acepta sin dudas. */
export function editableText(field: Pick<FieldInfo, 'tipo' | 'entrada' | 'valor'>): string {
  if (field.entrada === null || field.entrada === undefined) return '';
  if (['cent', 'mil', 'e4', 'pb'].includes(field.tipo)) return field.entrada.replace('.', ',');
  if (field.tipo === 'bool') return field.valor === true || field.valor === 1 ? 'si' : 'no';
  return field.entrada;
}

/** Los campos de la factura que la ficha ensena: los de la persona, no los de la maquina. */
const HIDDEN = new Set(['sentido', 'origen', 'numero_norm', 'fuente_externa', 'id_externo', 'anulada', 'fusionada_en_id']);

export function visibleFields(fields: FieldInfo[]): FieldInfo[] {
  return fields.filter(
    (f) => f.tipo !== 'ref' && !HIDDEN.has(f.campo) && (f.valor !== null || f.calidad !== null || f.obligatorio)
  );
}

/** Si la app ofrece cambiar o verificar este campo (el IBAN del documento no: los datos
 *  bancarios van por IBAN-controles, y a ese IBAN no se paga nunca). */
export function editableInApp(field: FieldInfo): boolean {
  return field.editable && field.campo !== 'iban_doc';
}
