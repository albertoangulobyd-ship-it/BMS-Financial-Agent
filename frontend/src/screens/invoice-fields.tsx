// Los campos de la factura (plegados): cada uno con su valor, de donde sale y sus marcas
// de calidad (Ontbreekt, Onzeker, Afwijking, Afwijkend, Geverifieerd), siempre en texto.
// Donde la persona puede, se cambia (antes de guardar se ve "oud -> nieuw"), se verifica
// o se deshace un cambio manual; cada orden lleva la rev de la fila que se vio.
import { ActionButton } from '@/components/action-dialog';
import { StatusPill } from '@/components/status-pill';
import { fmt, useT } from '@/i18n';
import { catalogFor, fieldLabel, qualityText, sourceText, stateLabel } from '@/i18n/domain';
import { permissionFor } from '@/lib/actions';
import type { FieldInfo, InvoiceDetail } from '@/lib/api-types';
import { editableInApp, editableText, enumGroup, formatFieldValue, visibleFields } from '@/lib/field-format';
import { useCan } from '@/lib/session';
import type { ActionField } from '@/components/action-dialog';
import { revOf } from './invoice-util';

// Verificar tiene sentido donde hay una duda (leido con duda, una discrepancia, algo
// raro); en los demas campos, el boton solo seria ruido.
const NEEDS_CHECK = new Set(['dudoso', 'discrepancia', 'anomalia']);

export function FieldsTable({ invoice, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const { t, lang } = useT();
  const can = useCan();
  const fields = visibleFields(invoice.campos);
  return (
    <div className='overflow-x-auto rounded-md border border-border bg-card'>
      <table className='w-full border-collapse text-left text-[13px]'>
        <caption className='sr-only'>{t.sections.fields}</caption>
        <thead>
          <tr className='border-b border-border bg-[#f2efe8] text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground'>
            <th scope='col' className='px-3 py-2'>{t.fields.field}</th>
            <th scope='col' className='px-3 py-2'>{t.fields.value}</th>
            <th scope='col' className='px-3 py-2'>{t.fields.source}</th>
            <th scope='col' className='px-3 py-2'>{t.fields.quality}</th>
            <th scope='col' className='px-3 py-2'><span className='sr-only'>{t.fields.actions}</span></th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => {
            const quality = qualityText(lang, f.calidad);
            const source = sourceText(lang, f.fuente);
            const rev = revOf(invoice, f);
            const canEdit = editableInApp(f) && can(permissionFor('fijar_campo', f.valor !== null));
            return (
              <tr key={f.campo} className='border-b border-[#ebe7df] align-top last:border-b-0'>
                <th scope='row' className='px-3 py-2 font-normal text-[#45423c]'>
                  {fieldLabel(lang, f.tabla, f.campo) ?? f.campo}
                </th>
                <td className='px-3 py-2'>
                  <span className={f.tipo === 'cent' ? 'num' : undefined}>{formatFieldValue(f, f.valor, lang)}</span>
                  {f.editado && f.cambiado_por && (
                    <span className='mt-0.5 block text-xs text-muted-foreground'>
                      {fmt(t.fields.changedBy, { name: f.cambiado_por })}
                      {f.motivo ? `: ${f.motivo}` : ''}
                    </span>
                  )}
                </td>
                <td className='px-3 py-2 text-[#45423c]' title={source?.meaning}>
                  {source?.label ?? '—'}
                </td>
                <td className='px-3 py-2'>
                  {quality ? (
                    <StatusPill group='calidad' state={f.calidad} title={quality.meaning} />
                  ) : (
                    <span className='text-muted-foreground'>—</span>
                  )}
                </td>
                <td className='px-3 py-1.5'>
                  <div className='flex flex-wrap justify-end gap-x-3'>
                    {canEdit && <FieldEditButton field={f} rev={rev} onDone={onDone} />}
                    {canEdit && f.valor !== null && !f.verificado && NEEDS_CHECK.has(f.calidad ?? '') && (
                      <ActionButton
                        action='verificar_campo'
                        label={t.fields.verify}
                        size='xs'
                        variant='link'
                        intro={fmt(t.fields.verifyIntro, { field: fieldLabel(lang, f.tabla, f.campo) ?? f.campo })}
                        data={() => ({ tabla: f.tabla, fila_id: f.fila_id, campo: f.campo, rev })}
                        onDone={onDone}
                      />
                    )}
                    {canEdit && f.revertible && (
                      <ActionButton
                        action='revertir_campo'
                        label={t.fields.revert}
                        size='xs'
                        variant='link'
                        intro={fmt(t.fields.revertIntro, { value: formatFieldValue(f, f.original, lang) })}
                        fields={[{ name: 'motivo', label: t.action.reason, kind: 'textarea', required: true }]}
                        data={(v) => ({ tabla: f.tabla, fila_id: f.fila_id, campo: f.campo, rev, motivo: v.motivo })}
                        onDone={onDone}
                      />
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Cambiar un campo: el dialogo ensena el valor de ahora y el nuevo antes de guardar. */
export function FieldEditButton({
  field,
  rev,
  onDone,
  labelPrefix = false,
}: {
  field: FieldInfo;
  rev: number;
  onDone: () => void;
  /** "Wijzigen: Totaal" (en un hallazgo) en vez de "Wijzigen" (en la tabla). */
  labelPrefix?: boolean;
}) {
  const { t, lang } = useT();
  const can = useCan();
  if (!editableInApp(field) || !can(permissionFor('fijar_campo', field.valor !== null))) return null;
  const name = fieldLabel(lang, field.tabla, field.campo) ?? field.campo;
  const hasValue = field.valor !== null;
  const input = inputFor(field, lang, t.fields.newValue);
  return (
    <ActionButton
      action='fijar_campo'
      label={labelPrefix ? fmt(hasValue ? t.fields.editThis : t.fields.fillThis, { field: name }) : hasValue ? t.fields.edit : t.fields.fill}
      size={labelPrefix ? 'sm' : 'xs'}
      variant={labelPrefix ? 'outline' : 'link'}
      title={fmt(hasValue ? t.fields.editThis : t.fields.fillThis, { field: name })}
      intro={hasValue ? t.fields.editIntro : t.fields.fillIntro}
      fields={[
        input,
        { name: 'motivo', label: t.action.reason, kind: 'textarea', required: hasValue, help: hasValue ? t.fields.reasonHelp : undefined },
      ]}
      preview={(v) => (
        <dl className='grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-md border border-border bg-card px-3 py-2 text-[13px]'>
          <dt className='text-muted-foreground'>{t.fields.oldValue}</dt>
          <dd className='m-0'>{formatFieldValue(field, field.valor, lang)}</dd>
          <dt className='text-muted-foreground'>{t.fields.newValue}</dt>
          <dd className='m-0 font-medium'>{previewValue(field, v.valor ?? '', lang)}</dd>
        </dl>
      )}
      data={(v) => ({
        tabla: field.tabla,
        fila_id: field.fila_id,
        campo: field.campo,
        valor: v.valor === '' ? null : v.valor,
        rev,
        motivo: v.motivo || undefined,
      })}
      onDone={onDone}
    />
  );
}

function inputFor(field: FieldInfo, lang: 'nl' | 'en', label: string): ActionField {
  const initial = editableText(field);
  if (field.tipo === 'fecha') return { name: 'valor', label, kind: 'date', initial, hideOptional: true };
  if (field.tipo === 'bool') {
    const c = catalogFor(lang).comun;
    return {
      name: 'valor',
      label,
      kind: 'select',
      initial: initial || 'no',
      options: [
        { value: 'si', label: c.si },
        { value: 'no', label: c.no },
      ],
    };
  }
  const group = field.tipo === 'enum' ? enumGroup(field.campo) : null;
  if (group) {
    const options = Object.keys(catalogFor(lang).estados[group]).map((k) => ({
      value: k,
      label: stateLabel(lang, group, k) ?? k,
    }));
    return { name: 'valor', label, kind: 'select', initial: initial || options[0]?.value, options };
  }
  return { name: 'valor', label, kind: 'text', initial, hideOptional: true };
}

/** El valor nuevo como se vera (un importe escrito 2902,79 se ve € 2.902,79). */
function previewValue(field: FieldInfo, text: string, lang: 'nl' | 'en'): string {
  const value = text.trim();
  if (!value) return '—';
  if (['cent', 'mil', 'e4', 'pb'].includes(field.tipo)) {
    const scale = { cent: 2, mil: 3, e4: 4, pb: 2 }[field.tipo as 'cent' | 'mil' | 'e4' | 'pb'];
    const integer = toScaled(value, scale);
    return integer === null ? value : formatFieldValue(field, integer, lang);
  }
  if (field.tipo === 'bool') return formatFieldValue(field, value === 'si', lang);
  return formatFieldValue(field, value, lang);
}

/** "2902,79" -> 290279 con la escala del campo, sin floats; null si no se entiende. */
export function toScaled(text: string, scale: number): string | null {
  let s = text.replace(/\s/g, '');
  if (/^[+-]?[1-9]\d{0,2}(\.\d{3})+,\d+$/.test(s)) s = s.replace(/\./g, '');
  const m = /^([+-]?)(\d+)(?:[.,](\d+))?$/.exec(s);
  if (!m) return null;
  const decimals = (m[3] ?? '').padEnd(scale, '0');
  if (decimals.length > scale) return null;
  const digits = `${m[2]}${decimals}`.replace(/^0+(?=\d)/, '');
  return `${m[1] === '-' ? '-' : ''}${digits}`;
}
