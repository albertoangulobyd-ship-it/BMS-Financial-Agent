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
  unusedPaletteTokens,
  unusedTexts,
} from './codigo-muerto.mjs';

// Lo que se queda sin montar a proposito, y por que:
// - components/ui es la biblioteca de piezas (las de shadcn hechas a mano y las del dueno): se
//   usan a la carta. La tira de pestanas tipo Chrome del dueno (paso 15) ya no es la
//   navegacion (paso 16) y se guarda tal cual, con las dos piezas que solo ella usa.
// - i18n/glossary.ts e i18n/leftovers.ts son de las pruebas (i18n.test.ts y e2e/fixtures.ts).
const LIBRARY = [
  'src/components/ui/context-menu.tsx',
  'src/components/ui/hover-card.tsx',
  'src/components/ui/sheet.tsx',
  'src/components/ui/sidebar-with-chrome-like-tabs.tsx',
];
const FOR_TESTS = ['src/i18n/glossary.ts', 'src/i18n/leftovers.ts'];

describe('sin codigo muerto en frontend/src', () => {
  it('todo fichero se alcanza desde main.tsx, salvo la biblioteca y lo de las pruebas', () => {
    expect(unreachedFiles()).toEqual([...LIBRARY, ...FOR_TESTS].sort());
    // Lo de las pruebas lo importa de verdad una prueba (si no, tambien sobraria).
    const imported = filesImportedByTests();
    for (const path of FOR_TESTS) expect(imported.has(path), path).toBe(true);
  });

  it('las piezas de Aurora que esperan a otro paso no estan en src', () => {
    // La conversacion y el orbe de particulas (el asistente, revision §6), el cargador y la
    // tarjeta de Procesar (revision §8.5) y el resumen del dinero (FinanceBento): vuelven
    // desde la copia del prototipo cuando su paso los monte.
    const files = unreachedFiles().concat([...filesImportedByTests()]);
    expect(files.filter((path) => /^src\/aurora\/(conversation|processing|finance|thinking-orb)\//.test(path))).toEqual([]);
    expect(unreachedFiles().filter((path) => path.startsWith('src/aurora/'))).toEqual([]);
  });

  // El analisis de TypeScript tarda unos segundos (mas con otros procesos en la maquina).
  it('toda declaracion exportada la usa alguien (la app, una prueba o e2e)', () => {
    expect(unusedExports({ skip: ['src/components/ui/'] })).toEqual([]);
  }, 120_000);

  it('cada variable de la paleta de Aurora se usa', () => {
    expect(unusedPaletteTokens()).toEqual([]);
  });

  it('cada clase de las hojas la pone alguna pantalla', () => {
    // Las bandas de datos de prueba y de aislamiento las mete el servidor (app_local.py) en la
    // pagina, no la app.
    expect(unusedClasses({ external: ['bms-banda-prueba', 'bms-banda-aislamiento'] })).toEqual([]);
  });

  it('cada texto de Aurora se lee en alguna pantalla, en los tres idiomas', () => {
    expect(unusedTexts(nl, 'aurora')).toEqual([]);
    // Las mismas claves en los tres (lo exige el tipo; aqui, que no se quede ninguna atras).
    expect(unusedTexts(en, 'aurora')).toEqual([]);
    expect(unusedTexts(es, 'aurora')).toEqual([]);
  });
});
