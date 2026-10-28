// El asistente de la conversacion (especificacion §2.5): local y determinista. No llama a ningun
// modelo ni sale del ordenador: contesta con lo que dicen las lecturas de /api/v2 y nunca
// inventa una cifra. Sabe hacer cinco cosas, en este orden:
// 1. el resumen general ("Dame un resumen general" y sus formas en nl y en): texto y Finance Bento;
// 2. "¿Que es...?" / "Wat is...?" / "What is...?": la frase del glosario (t.help);
// 3. el nombre de una pantalla ("IVA", "cola de trabajo"): una fila que la abre;
// 4. un numero de factura, un nombre, un Object o una PO: "Encontre N para «…»." y sus filas;
// 5. lo demas: lo dice, y dice lo que si sabe hacer.
// El asistente de 25 preguntas del servidor (/api/v2/preguntar) entra despues por el mismo hueco.
import { LANGS, MESSAGES, fmt, type Messages } from '@/i18n';
import type { ApiClient } from '@/lib/api';
import { invoiceResults, loadSources, recordResults, screenResults, type PlaceTarget } from '@/lib/quick-search';
import { fold } from '@/lib/text';
import { loadFinanceSummary, summaryRequested, summaryText, type FinanceSummary } from './finance/finance-bento';

/** Lo que abre una fila de la respuesta (lib/quick-search.ts): el panel de una entrada con la
 *  vista de un grupo (E4 -> E2 en un solo cambio, F9), la busqueda con sus filtros, Documentos
 *  (con el vuelo) o Procesar. */
export type AnswerTarget = PlaceTarget;

export interface AnswerRow {
  key: string;
  label: string;
  detail?: string;
  /** Una pantalla (no lleva importe ni datos de nadie). */
  screen: boolean;
  target: AnswerTarget;
}

export interface Answer {
  text: string;
  rows?: AnswerRow[];
  /** Lo buscado, para "Buscar con filtros" (E5). */
  search?: string;
  summary?: FinanceSummary;
}

const QUESTION: readonly RegExp[] = [
  /^\s*¿?\s*que\s+(?:es|son|significa|quiere decir)\s+(?:(?:un|una|el|la|los|las|lo)\s+)?(.+?)\s*\??\s*$/,
  /^\s*wat\s+(?:is|zijn|betekent)\s+(?:(?:een|de|het)\s+)?(.+?)\s*\??\s*$/,
  /^\s*what\s+(?:is|are|does)\s+(?:(?:a|an|the)\s+)?(.+?)(?:\s+mean)?\s*\??\s*$/,
];

/** "¿Que es un Object?" -> la frase del glosario, en el idioma de la persona. */
export function glossaryAnswer(prompt: string, t: Messages): string | null {
  const q = fold(prompt);
  const asked = QUESTION.map((re) => re.exec(q)?.[1]).find(Boolean);
  if (!asked) return null;
  const keys = Object.keys(t.help) as (keyof Messages['help'])[];
  const hit = keys.find((k) => LANGS.some((lang) => fold(MESSAGES[lang].help[k].term) === asked || asked.startsWith(fold(MESSAGES[lang].help[k].term))));
  return hit ? t.help[hit].text : null;
}

export async function answerQuestion(
  prompt: string,
  ctx: { api: ApiClient; t: Messages; can: (permission?: string) => boolean }
): Promise<Answer> {
  const { api, t, can } = ctx;
  const q = prompt.trim();
  if (summaryRequested(q)) {
    const summary = await loadFinanceSummary(api);
    return { text: summaryText(t, summary), summary };
  }
  const glossary = glossaryAnswer(q, t);
  if (glossary) return { text: glossary };
  const [sources, invoices] = await Promise.all([loadSources(api), invoiceResults(api, q, t)]);
  const found = [...screenResults(q, t, can), ...recordResults(q, sources, t), ...invoices.results];
  if (found.length === 0) return { text: t.aurora.chat.unknown };
  const rows = found.map<AnswerRow>((r) => ({
    key: r.key,
    label: r.label,
    detail: r.detail,
    screen: r.kind === 'screens',
    target: r.target,
  }));
  const total = found.length + Math.max(0, invoices.total - invoices.results.length);
  return { text: fmt(total === 1 ? t.aurora.chat.foundOne : t.aurora.chat.found, { n: total, q }), rows, search: q };
}
