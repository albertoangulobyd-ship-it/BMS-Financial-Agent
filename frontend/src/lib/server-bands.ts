// Las bandas que pone el servidor encima de la app (datos de prueba, aislamiento roto: pasos
// 13 y 14) se quedan a la vista al desplazar la pagina. Cada una es sticky (index.css); aqui
// se apilan (cada una debajo de las de antes) y se deja su alto en --bms-bandas, que usa la
// cabecera de la app para ir debajo. Se rehace si cambia su alto (una banda larga se parte en
// dos lineas en el movil). Sin el script, las bandas siguen arriba de la pagina.

/** Donde va cada banda (su `top`, en px) y lo que ocupan todas, de sus altos en orden. */
export function stackBands(heights: readonly number[]): { tops: number[]; total: number } {
  const tops: number[] = [];
  let total = 0;
  for (const h of heights) {
    tops.push(total);
    total += h;
  }
  return { tops, total };
}

export function stickServerBands(doc: Document = document): () => void {
  const bands = Array.from(doc.querySelectorAll<HTMLElement>('body > .bms-banda'));
  const root = doc.documentElement;
  const layout = () => {
    const { tops, total } = stackBands(bands.map((b) => b.getBoundingClientRect().height));
    bands.forEach((b, i) => (b.style.top = `${tops[i]}px`));
    root.style.setProperty('--bms-bandas', `${total}px`);
  };
  layout();
  if (bands.length === 0 || typeof ResizeObserver === 'undefined') return () => undefined;
  const observer = new ResizeObserver(layout);
  bands.forEach((b) => observer.observe(b));
  return () => observer.disconnect();
}
