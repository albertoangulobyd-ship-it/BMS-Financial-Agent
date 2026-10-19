// Buscar en lo que se ve: sin mayusculas ni acentos ("oztürk" encuentra "Öztürk") y sin
// espacios, puntos, guiones ni barras en los numeros ("kt 2026" encuentra "KT-2026-08").

/** Un texto plegado para comparar: minusculas y sin marcas diacriticas. */
export function fold(text: string | null | undefined): string {
  return (text ?? '').normalize('NFD').replace(/\p{M}+/gu, '').toLocaleLowerCase('nl-NL');
}

const SEPARATORS = /[\s.\-/]+/g;

/** Si alguno de los textos contiene lo buscado (vacio: todo vale). */
export function matches(query: string, ...texts: (string | null | undefined)[]): boolean {
  const q = fold(query).trim();
  if (!q) return true;
  const compact = q.replace(SEPARATORS, '');
  return texts.some((t) => {
    const f = fold(t);
    return f.includes(q) || (compact.length > 0 && f.replace(SEPARATORS, '').includes(compact));
  });
}

/** Los dias enteros entre dos fechas AAAA-MM-DD (o el principio de un instante). */
export function daysBetween(from: string | null | undefined, to: string | null | undefined): number | null {
  const a = /^(\d{4})-(\d{2})-(\d{2})/.exec(from ?? '');
  const b = /^(\d{4})-(\d{2})-(\d{2})/.exec(to ?? '');
  if (!a || !b) return null;
  const da = Date.UTC(Number(a[1]), Number(a[2]) - 1, Number(a[3]));
  const db = Date.UTC(Number(b[1]), Number(b[2]) - 1, Number(b[3]));
  return Math.round((db - da) / 86_400_000);
}
