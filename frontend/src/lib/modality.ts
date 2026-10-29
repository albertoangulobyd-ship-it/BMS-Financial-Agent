// Como se mueve la persona: con el teclado (Tab) o con el raton o el dedo, en
// <body data-modality="keyboard|pointer">. El CSS lo usa para lo que solo se ve con el teclado: el
// borde de la caja al llegar a ella con Tab (aurora/bms.css). Las letras no cuentan: escribir en
// una caja a la que se llego con el raton no la marca. Sin el script, nada cambia.

export function trackModality(doc: Document = document): () => void {
  const root = doc.body;
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Tab') root.dataset.modality = 'keyboard';
  };
  const onPointer = () => {
    root.dataset.modality = 'pointer';
  };
  doc.addEventListener('keydown', onKey, true);
  doc.addEventListener('pointerdown', onPointer, true);
  return () => {
    doc.removeEventListener('keydown', onKey, true);
    doc.removeEventListener('pointerdown', onPointer, true);
  };
}
