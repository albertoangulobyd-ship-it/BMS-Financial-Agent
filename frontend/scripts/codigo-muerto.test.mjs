// Sin codigo muerto en frontend/src (puerta del paso 16, G2). Lo que mira, en
// scripts/codigo-muerto.mjs. Si una prueba de aqui falla por una pieza que espera a un paso
// posterior, esa pieza no va en src hasta que su paso la monte.
import { describe, expect, it } from 'vitest';
import { en } from '../src/i18n/en';
import { es } from '../src/i18n/es';
import { nl } from '../src/i18n/nl';
import {
  filesImportedByTests,
  unreachedFiles,
  unusedClasses,
  unusedExports,
  unusedTexts,
} from './codigo-muerto.mjs';

// Lo que se queda sin montar a proposito, y por que:
// - components/ui es la biblioteca de piezas (las de shadcn hechas a mano y las del dueno): se
//   usan a la carta. La tira de pestanas tipo Chrome del dueno (paso 15) ya no es la
//   navegacion (paso 16) y se guarda tal cual, con las piezas que solo ella usa (desde el paso
//   17 tambien el desplegable del menu del nombre, que ya no existe, y el tooltip).
// - i18n/glossary.ts e i18n/leftovers.ts son de las pruebas (i18n.test.ts y e2e/fixtures.ts).
const LIBRARY = [
  'src/components/ui/context-menu.tsx',
  'src/components/ui/dropdown-menu.tsx',
  'src/components/ui/hover-card.tsx',
  'src/components/ui/sheet.tsx',
  'src/components/ui/sidebar-with-chrome-like-tabs.tsx',
  'src/components/ui/tooltip.tsx',
];
const FOR_TESTS = ['src/i18n/glossary.ts', 'src/i18n/leftovers.ts'];

describe('sin codigo muerto en frontend/src', () => {
  it('todo fichero se alcanza desde main.tsx, salvo la biblioteca y lo de las pruebas', () => {
    expect(unreachedFiles()).toEqual([...LIBRARY, ...FOR_TESTS].sort());
    // Lo de las pruebas lo importa de verdad una prueba (si no, tambien sobraria).
    const imported = filesImportedByTests();
    for (const path of FOR_TESTS) expect(imported.has(path), path).toBe(true);
  });

  it('cada pieza de Aurora en src la monta la app', () => {
    // Desde el paso 17 la conversacion, el orbe de particulas y el resumen del dinero se montan;
    // el cargador y la tarjeta de Procesar (revision §8.5) vuelven de la copia del prototipo
    // cuando su paso los monte, no antes.
    expect(unreachedFiles().filter((path) => path.startsWith('src/aurora/'))).toEqual([]);
  });

  // El analisis de TypeScript tarda unos segundos (mas con otros procesos en la maquina).
  it('toda declaracion exportada la usa alguien (la app, una prueba o e2e)', () => {
    expect(unusedExports({ skip: ['src/components/ui/'] })).toEqual([]);
  }, 120_000);

  it('cada clase de las hojas la pone alguna pantalla', () => {
    // Las bandas de datos de prueba y de aislamiento las mete el servidor (app_local.py) en la
    // pagina, no la app.
    // Las hojas de Aurora que se copian tal cual (paso 17, especificacion §4.1): llevan reglas de
    // piezas que monta otro paso (los paneles, Procesar) o que la app no pinta (la pagina de
    // busqueda propia, el sello del autor del resumen). No se recortan: son las del dueno.
    const verbatim = [
      'src/aurora/styles.css',
      'src/aurora/workspace-layout.css',
      'src/aurora/chat/ai-actions.css',
      'src/aurora/finance/finance-bento.css',
      'src/aurora/finance/finance-bento-component.css',
      'src/aurora/search/search-workspace.css',
      'src/aurora/documents/document-workspace.css',
      'src/aurora/documents/file-analysis.css',
      'src/aurora/documents/glass-folder-cards.css',
      // El tema claro sale de esas hojas (scripts/aurora-claro.mjs): lleva sus mismas reglas.
      'src/aurora/claro.css',
    ];
    expect(unusedClasses({ external: ['bms-banda-prueba', 'bms-banda-aislamiento'], verbatim })).toEqual([]);
  });

  it('cada texto de Aurora se lee en alguna pantalla, en los tres idiomas', () => {
    expect(unusedTexts(nl, 'aurora')).toEqual([]);
    // Las mismas claves en los tres (lo exige el tipo; aqui, que no se quede ninguna atras).
    expect(unusedTexts(en, 'aurora')).toEqual([]);
    expect(unusedTexts(es, 'aurora')).toEqual([]);
  });
});
