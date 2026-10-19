// Dos facturas distintas con el mismo numero y la misma relacion (la misma enviada dos
// veces, o un numero repetido) salen iguales en una lista: nada dice cual es cual antes de
// abrirlas. Aqui cada una recibe su "1 van 2" (por id: la que llego antes, la primera), y
// "Als eerste" junta las de un mismo numero para que sus cinco filas sean cinco cosas.
export interface TwinMark {
  n: number;
  of: number;
}

interface Numbered {
  id: number;
  numero: string | null;
  contraparte: string | null;
}

const keyOf = (r: Numbered) => (r.numero ? `${r.numero.trim().toUpperCase()}\u0000${(r.contraparte ?? '').trim().toUpperCase()}` : null);

/** El "n van m" de cada factura que comparte numero y relacion con otra de la lista. */
export function twinMarks(rows: readonly Numbered[]): Map<number, TwinMark> {
  const groups = new Map<string, number[]>();
  for (const r of rows) {
    const key = keyOf(r);
    if (key === null) continue;
    groups.set(key, [...(groups.get(key) ?? []), r.id]);
  }
  const out = new Map<number, TwinMark>();
  for (const ids of groups.values()) {
    if (ids.length < 2) continue;
    [...ids].sort((a, b) => a - b).forEach((id, i) => out.set(id, { n: i + 1, of: ids.length }));
  }
  return out;
}

/** Una por numero y relacion, en el orden de la lista, con cuantas comparten el numero. */
export function distinctByNumber<R extends Numbered>(rows: readonly R[]): { row: R; count: number }[] {
  const out: { row: R; count: number }[] = [];
  const seen = new Map<string, { row: R; count: number }>();
  for (const r of rows) {
    const key = keyOf(r);
    const known = key === null ? undefined : seen.get(key);
    if (known) {
      known.count += 1;
      continue;
    }
    const entry = { row: r, count: 1 };
    out.push(entry);
    if (key !== null) seen.set(key, entry);
  }
  return out;
}
