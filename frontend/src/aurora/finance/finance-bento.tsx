// El resumen general de Aurora (components/ui/finance-bento.tsx, entrega del 28-10-2026): la
// pregunta que lo pide, el texto que lo acompana y el Finance Bento con su pie. Cambios (§4.1):
// - D: los datos salen de las lecturas de verdad (no de localStorage): la cartera de cobrar y
//   la de pagar (lo pendiente, la misma cifra que sus paneles), los clientes y los proveedores
//   (lo que queda de cada uno y cuantos documentos tiene su carpeta) y la ultima lectura de
//   facturas, si la hay. Son saldos pendientes: nunca historia, rentabilidad ni caja;
// - E: euros desde centimos (lib/format.ts);
// - I: la pregunta se reconoce en castellano, neerlandes e ingles, y los textos son los del
//   diccionario (en castellano, los de Aurora).
import { useMemo } from 'react';
import { countText, fmt, useT, type Messages } from '@/i18n';
import { paths, type ApiClient } from '@/lib/api';
import type { Cartera, PartyRow } from '@/lib/api-types';
import { formatDate, formatMoney } from '@/lib/format';
// La hoja del resumen antes que la del componente: en Aurora, el <style> del componente iba despues.
import './finance-bento.css';
import { FinanceBento as SuppliedFinanceBento, type FinanceBentoData, type FinanceBentoTexts } from './finance-bento-component';

export type { FinanceBentoData };

const fold = (prompt: string) => prompt.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** La pregunta del resumen: la expresion de Aurora y sus formas en neerlandes e ingles. */
export const summaryRequested = (prompt: string) =>
  /\b(resumen|panorama|dashboard)\b|vision general|como (voy|vamos)|situacion financiera|vista general/.test(fold(prompt)) ||
  /\b(overzicht|samenvatting)\b|hoe staan (we|wij) ervoor|financiele situatie/.test(fold(prompt)) ||
  /\b(summary|overview)\b|how are we doing|financial situation/.test(fold(prompt));

/** Lo que dice la ultima lectura de facturas, si la API ya lo cuenta (nuevas y repetidas). */
function lastReading(reading: unknown): FinanceBentoData['analysis'] {
  const pass = (reading as { pasada_en_curso?: { resultado?: { estado: string }[] } } | null)?.pasada_en_curso;
  const rows = pass?.resultado;
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const newCount = rows.filter((r) => r.estado === 'nueva').length;
  const duplicateCount = rows.filter((r) => r.estado === 'ya_leida' || r.estado === 'posible_duplicado').length;
  return { total: rows.length, newCount, duplicateCount };
}

export interface FinanceSummary {
  data: FinanceBentoData;
  /** De cuando son los datos (estado_del de la cartera); null si no lo dice. */
  asOf: string | null;
}

/** El resumen, de las lecturas (captureFinanceSummary en Aurora). */
export async function loadFinanceSummary(api: ApiClient): Promise<FinanceSummary> {
  const [receivable, payable, clients, providers, reading] = await Promise.all([
    api.get<{ cartera: Cartera }>(paths.cartera, { sentido: 'saliente' }).then((r) => r.cartera),
    api.get<{ cartera: Cartera }>(paths.cartera, { sentido: 'entrante' }).then((r) => r.cartera),
    api.get<{ clientes: PartyRow[] }>(paths.clients).then((r) => r.clientes),
    api.get<{ proveedores: PartyRow[] }>(paths.providers).then((r) => r.proveedores),
    api.get<unknown>(paths.reading).catch(() => null),
  ]);
  const rows = [...clients.map((p) => ({ p, type: 'clientes' as const })), ...providers.map((p) => ({ p, type: 'proveedores' as const }))].map(
    ({ p, type }) => ({
      id: p.id,
      name: p.nombre,
      type,
      balance: Math.max(0, p.deuda_cent),
      documents: p.documentos ?? 0,
    })
  );
  return {
    data: {
      capturedAt: new Date().toISOString(),
      receivable: Math.max(0, receivable.totales.pendiente_cent),
      payable: Math.max(0, payable.totales.pendiente_cent),
      documents: rows.reduce((sum, p) => sum + p.documents, 0),
      invoices: [...clients, ...providers].reduce((sum, p) => sum + p.facturas, 0),
      parties: rows,
      analysis: lastReading(reading),
    },
    asOf: receivable.estado_del,
  };
}

/** El texto que acompana al resumen (para copiar y exportar). */
export function summaryText(t: Messages, s: FinanceSummary): string {
  const d = s.data;
  const b = t.aurora.bento;
  const lines = [
    b.textIntro,
    '',
    fmt(b.textReceivable, { amount: formatMoney(d.receivable) }),
    fmt(b.textPayable, { amount: formatMoney(d.payable) }),
    fmt(b.textDifference, { amount: formatMoney(d.receivable - d.payable) }),
    fmt(b.textDocuments, {
      documents: d.documents,
      folders: d.parties.length,
      invoices: d.invoices,
    }),
  ];
  if (d.analysis)
    lines.push(
      fmt(b.textAnalysis, {
        fresh: d.analysis.newCount,
        repeated: d.analysis.duplicateCount,
      })
    );
  lines.push('', s.asOf ? fmt(b.textAsOf, { date: formatDate(s.asOf) }) : b.textNoDate);
  return lines.join('\n');
}

/** Los textos de las tarjetas, del diccionario. */
export function bentoTexts(t: Messages): FinanceBentoTexts {
  const b = t.aurora.bento;
  return {
    period: b.period,
    currency: b.currency,
    currencyBadge: b.currencyBadge,
    pending: b.pending,
    pendingNote: b.pendingNote,
    receivable: b.receivable,
    payable: b.payable,
    allocation: b.allocation,
    allocationLabel: b.allocationLabel,
    allocationCaption: b.allocationCaption,
    collect: b.collect,
    pay: b.pay,
    clientsWithBalance: (n) => fmt(b.withBalance, { what: countText(t, 'clients', n) }),
    providersWithBalance: (n) => fmt(b.withBalance, { what: countText(t, 'providers', n) }),
    documents: b.documents,
    invoicesInArchive: (n) => fmt(b.invoicesInArchive, { what: countText(t, 'invoices', n) }),
    folders: b.folders,
    foldersNote: b.foldersNote,
    where: b.where,
    companyType: b.companyType,
    clients: b.clients,
    providers: b.providers,
    noFolders: b.noFolders,
    lastReview: b.lastReview,
    newCount: b.newCount,
    duplicateCount: b.duplicateCount,
    reviewed: (n) => fmt(n === 1 ? b.reviewedOne : b.reviewed, { n }),
    noCopies: b.noCopies,
    explore: b.explore,
    noReview: b.noReview,
    noReviewNote: b.noReviewNote,
    composition: b.composition,
    compositionLabel: (invoices, others) => fmt(b.compositionLabel, { invoices, others }),
    invoicesLabel: b.invoicesLabel,
    othersLabel: b.othersLabel,
  };
}

function useBentoTexts(): FinanceBentoTexts {
  const { t } = useT();
  return useMemo(() => bentoTexts(t), [t]);
}

/** The supplied Finance Bento shell and SVG gauge, adapted to the document snapshot. */
export function FinanceBento({
  summary,
  onOpenParty,
}: {
  summary: FinanceSummary;
  onOpenParty?: (party: { id: number; type: 'clientes' | 'proveedores' } | null) => void;
}) {
  const { t, lang } = useT();
  const texts = useBentoTexts();
  const time = new Date(summary.data.capturedAt).toLocaleTimeString(lang === 'en' ? 'en-GB' : lang === 'nl' ? 'nl-NL' : 'es-ES', {
    hour: '2-digit',
    minute: '2-digit',
  });
  const source = summary.asOf ? fmt(t.aurora.bento.footerAsOf, { date: formatDate(summary.asOf) }) : t.aurora.bento.footerNoDate;
  return (
    <section className='finance-bento' aria-label={t.aurora.bento.label}>
      <SuppliedFinanceBento data={summary.data} texts={texts} title={t.aurora.bento.title} subtitle={t.aurora.bento.subtitle} onOpenParty={onOpenParty} />
      <footer>{`${source} · ${time}`}</footer>
    </section>
  );
}
