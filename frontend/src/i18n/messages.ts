// La forma de los textos de la app: la de nl.ts. Sin React, para que la puedan usar en.ts y
// es.ts sin traer index.tsx (las pruebas en el navegador importan los diccionarios: e2e/nav.ts).
import type { nl } from './nl';

export type Messages = typeof nl;
