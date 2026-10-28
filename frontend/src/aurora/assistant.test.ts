// El asistente de la conversacion (especificacion §2.5): el resumen general con las cifras de la
// cartera (saldos pendientes), el glosario en los tres idiomas, una pantalla que es la entrada de
// un panel (abre el panel, F9), una empresa (su carpeta en Documentos) y lo que no sabe.
import { describe, expect, it } from 'vitest';
import { MESSAGES } from '@/i18n';
import type { ApiClient } from '@/lib/api';
import { formatMoney } from '@/lib/format';
import { answerQuestion, glossaryAnswer } from './assistant';
import { entryIndex } from './estado';

const party = (id: number, nombre: string, deuda: number) => ({
  id,
  nombre,
  exact_id: null,
  activo: true,
  facturas: 2,
  pendiente_cent: deuda,
  vencido_cent: 0,
  ano_facturado_cent: 0,
  nivel: 'ok',
  documentos: 3,
  deuda_cent: deuda,
  abonos_sin_enlazar_cent: 0,
  abonos_sin_enlazar_facturas: 0,
});

const cartera = (sentido: string, pendiente: number) => ({
  cartera: { sentido, hoy: '2026-10-28', estado_del: '2026-10-27', al_dia: true, totales: { pendiente_cent: pendiente } },
});

function fakeApi(calls: string[] = []): ApiClient {
  const get = async (path: string, params?: Record<string, unknown>) => {
    calls.push(path + (params?.sentido ? `?${params.sentido}` : ''));
    if (path === '/api/v2/cartera') return params?.sentido === 'saliente' ? cartera('saliente', 250000) : cartera('entrante', 120000);
    if (path === '/api/v2/clientes') return { clientes: [party(7, 'Hotel Zeezicht', 250000)] };
    if (path === '/api/v2/proveedores') return { proveedores: [party(9, 'Schoonmaak BV', -500)] };
    if (path === '/api/v2/objetos') return { objetos: [] };
    if (path === '/api/v2/ordenes') return { ordenes: [] };
    if (path === '/api/v2/buscar') return { busqueda: { total: 0, facturas: [] } };
    if (path === '/api/v2/lectura') throw new Error('sin lectura');
    throw new Error('ruta inesperada ' + path);
  };
  return { get } as unknown as ApiClient;
}

const ctx = (lang: 'es' | 'nl' | 'en' = 'es', calls?: string[]) => ({ api: fakeApi(calls), t: MESSAGES[lang], can: () => true });

describe('asistente', () => {
  it('el glosario contesta en el idioma de la persona, se pregunte en el idioma que se pregunte', () => {
    expect(glossaryAnswer('¿Qué es un Object?', MESSAGES.es)).toBe(MESSAGES.es.help.object.text);
    expect(glossaryAnswer('Wat is een Object?', MESSAGES.nl)).toBe(MESSAGES.nl.help.object.text);
    expect(glossaryAnswer('What is an Object?', MESSAGES.en)).toBe(MESSAGES.en.help.object.text);
    expect(glossaryAnswer('What is an Object?', MESSAGES.es)).toBe(MESSAGES.es.help.object.text);
    expect(glossaryAnswer('Hotel Zeezicht', MESSAGES.es)).toBeNull();
  });

  it('"Dame un resumen general": las cifras de la cartera, sin saldos negativos, con el Bento', async () => {
    const calls: string[] = [];
    const a = await answerQuestion('Dame un resumen general', ctx('es', calls));
    expect(a.summary).toBeDefined();
    expect(a.summary!.data.receivable).toBe(250000);
    expect(a.summary!.data.payable).toBe(120000);
    // Un proveedor con saldo a favor no suma (max(0, deuda)).
    expect(a.summary!.data.parties.find((p) => p.id === 9)!.balance).toBe(0);
    expect(a.summary!.data.analysis).toBeNull();
    expect(a.text).toContain(formatMoney(250000));
    expect(a.text).toContain(MESSAGES.es.aurora.bento.textIntro);
    expect(calls).toContain('/api/v2/cartera?saliente');
    expect(calls).toContain('/api/v2/cartera?entrante');
    expect(a.rows).toBeUndefined();
  });

  it('"Geef me een overzicht" y "Give me an overview" piden lo mismo', async () => {
    for (const [q, lang] of [
      ['Geef me een overzicht', 'nl'],
      ['Give me an overview', 'en'],
    ] as const) {
      const a = await answerQuestion(q, ctx(lang));
      expect(a.summary, q).toBeDefined();
      expect(a.text).toContain(MESSAGES[lang].aurora.bento.textIntro);
    }
  });

  it('el nombre de una pantalla que es la entrada de un panel abre el panel (F9)', async () => {
    const a = await answerQuestion('IVA', ctx());
    const row = a.rows!.find((r) => r.screen && r.key === 'screen:vat')!;
    expect(row.target).toEqual({ kind: 'panel', entry: entryIndex('vat') });
    expect(a.search).toBe('IVA');
  });

  it('una empresa abre su carpeta en Documentos', async () => {
    const a = await answerQuestion('Zeezicht', ctx());
    const row = a.rows!.find((r) => r.key === 'client:7')!;
    expect(row.target).toEqual({ kind: 'work', trail: [{ screen: 'documents' }, { screen: 'client-documents', id: 7 }] });
    expect(a.text).toBe(MESSAGES.es.aurora.chat.foundOne.replace('{q}', 'Zeezicht'));
  });

  it('lo que no sabe, lo dice', async () => {
    const a = await answerQuestion('xyzzy', ctx());
    expect(a.text).toBe(MESSAGES.es.aurora.chat.unknown);
    expect(a.rows).toBeUndefined();
  });
});
