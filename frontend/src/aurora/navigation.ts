// Ir a Documentos desde cualquier sitio (especificacion §1.5, F3): una factura (su hoja, en la
// carpeta de su empresa), la carpeta de una empresa, un Object o una orden de compra. Desde el
// inicio de Aurora (un panel, la conversacion, la busqueda) va con el vuelo del orbe a la
// esquina; dentro de Documentos, sin vuelo.
import { useCallback } from 'react';
import { invoicePlace, type DocsPlace, type InvoiceRef } from './estado';
import { useAurora } from './root';

/** Ir a un sitio de Documentos: con vuelo desde el inicio, sin vuelo dentro. */
export function useGoToDocuments(): (place: DocsPlace) => void {
  const { state, dispatch, go } = useAurora();
  const inside = state.screen === 'work' && state.work.kind === 'documents';
  return useCallback((place: DocsPlace) => (inside ? dispatch({ type: 'docs', place }) : go({ type: 'enterDocuments', place })), [inside, dispatch, go]);
}

/** Abrir la hoja de una factura (F3). */
export function useOpenInvoice(): (ref: InvoiceRef) => void {
  const goTo = useGoToDocuments();
  return useCallback((ref: InvoiceRef) => goTo(invoicePlace(ref)), [goTo]);
}
