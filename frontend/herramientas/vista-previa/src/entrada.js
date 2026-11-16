// La entrada del bundle de la vista previa: primero el shim (fetch, el reloj y la lectura
// grabada), despues la app de verdad por su entrada de verdad (frontend/src/main.tsx del repo
// que se le da a construir.mjs con --repo). El orden de los import es el orden en que corren.
import './shim.js';
import '@vp/app';
