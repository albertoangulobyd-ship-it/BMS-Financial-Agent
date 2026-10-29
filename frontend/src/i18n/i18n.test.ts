import { describe, expect, it } from 'vitest';
import { LANGS, MESSAGES, countText, fmt, isLang, type Lang } from './index';
import { DOMAIN_FALLBACK, catalogFor } from './domain';
import { ES_GLOSSARY, glossaryMisses } from './glossary';
import { leftoversIn, sharedWords } from './leftovers';

type Tree = { [key: string]: Tree | string | string[] };

function leaves(tree: Tree, prefix = ''): Map<string, string | string[]> {
  const out = new Map<string, string | string[]>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string' || Array.isArray(value)) out.set(path, value);
    else for (const [k, v] of leaves(value, path)) out.set(k, v);
  }
  return out;
}

const holes = (text: string) => [...text.matchAll(/\{([a-zA-Z0-9_]+)\}/g)].map((m) => m[1]).sort();
const dictionaries = Object.fromEntries(LANGS.map((lang) => [lang, leaves(MESSAGES[lang] as unknown as Tree)])) as Record<
  Lang,
  Map<string, string | string[]>
>;

describe('los textos de la app', () => {
  it('tienen las mismas claves en los tres idiomas', () => {
    const nl = [...dictionaries.nl.keys()].sort();
    for (const lang of LANGS) expect([...dictionaries[lang].keys()].sort(), lang).toEqual(nl);
  });

  it('tienen los mismos huecos en los tres idiomas', () => {
    for (const [key, value] of dictionaries.nl) {
      for (const lang of LANGS) {
        const other = dictionaries[lang].get(key)!;
        if (typeof value === 'string') expect(holes(other as string), `${lang}:${key}`).toEqual(holes(value));
        else expect((other as string[]).length, `${lang}:${key}`).toBe(value.length);
      }
    }
  });

  it('no dejan ningun texto vacio salvo los que son a proposito', () => {
    const allowedEmpty = /^(groups\.settings|nav\.[a-z-]+\.hint)$/;
    for (const lang of LANGS) {
      for (const [key, value] of dictionaries[lang]) {
        if (typeof value === 'string' && value.trim() === '') {
          expect(allowedEmpty.test(key), `${lang}:${key}`).toBe(true);
        }
      }
    }
  });

  it('no guardan lo que ya no existe (especificacion §6.5): ni el atajo de la paleta ni un texto de carga', () => {
    for (const lang of LANGS) {
      const found = [...dictionaries[lang]].filter(([key, value]) => /searchShortcut|^common\.loading$/.test(key) || /Ctrl ?K|^(Cargando|Laden|Loading)…$/.test(String(value)));
      expect(found.map(([key, value]) => `${key}: ${value}`), lang).toEqual([]);
    }
  });

  it('no llevan restos de otro idioma: cada uno libre de las palabras de los otros dos', () => {
    expect(sharedWords(), 'una palabra en dos listas').toEqual([]);
    const found: string[] = [];
    for (const lang of LANGS) {
      for (const [key, value] of dictionaries[lang]) {
        for (const text of Array.isArray(value) ? value : [value]) {
          const words = leftoversIn(text, lang);
          if (words.length) found.push(`${lang}:${key} ${words.join(',')}: ${text}`);
        }
      }
    }
    expect(found).toEqual([]);
  });

  it('el castellano esta traducido: ninguna frase igual que en ingles o en neerlandes', () => {
    // Iguales a proposito: nombres propios, siglas y codigos (y las palabras del oficio que
    // BMS usa tal cual: Object, IBAN, BTW).
    const same = /^(app\.|language\.(nl|en|es)(Long)?$|units\.|records\.object\.|lines\.object$|planning\.object$|objects\.(object|sectionPos)$|pos\.sectionObjects$|parties\.(iban|no)$|nav\.(objects|vat)\.|help\.object\.term$|vat\.(title|vat)$|overview\.open\.vat$|common\.twin$|parties\.total$|overview\.vat\.caption$|months\.(short|long)\.)/;
    const untranslated: string[] = [];
    for (const [key, value] of dictionaries.es) {
      if (typeof value !== 'string' || same.test(key) || !/\p{L}{3,}.*\s.*\p{L}{3,}/u.test(value)) continue;
      if (value === dictionaries.en.get(key) || value === dictionaries.nl.get(key)) untranslated.push(`${key}: ${value}`);
    }
    expect(untranslated).toEqual([]);
  });
});

// Una cifra con su palabra (puerta del paso 16: el inicio decia "bij 1 klanten"). Cada texto con
// {n} tiene su singular en <clave>One, salvo estos, con su porque. Que la pantalla lea tambien el
// singular lo mira scripts/singular.test.mjs.
const NO_SINGULAR: Record<string, string> = {
  'common.twin': 'sin palabra: "2 van 3"',
  'action.tooShort': 'n es un minimo de letras, siempre mas de 1',
  'invoice.acceptReasonHelp': 'n es un minimo de letras, siempre mas de 1',
  'why.fieldsToVerify': 'etiqueta y cifra: "Velden te verifiëren: 1"',
  'invoice.notesCount': 'etiqueta y cifra',
  'exceptions.total': 'etiqueta y cifra',
  'parties.exceptionsOpen': 'etiqueta y cifra',
  'overview.nextUp.all': 'solo sale con 2 o mas (hay alguna urgente y mas en la lista)',
  'overview.nextUp.sameNumber': 'solo sale con 2 o mas',
  'documents.showAll': 'solo sale si quedan carpetas por ensenar: 2 o mas',
  'documents.moreWarnings': 'sin palabra: "en nog 1"',
  'importing.moreRejections': 'sin palabra: "en nog 1"',
  'importing.row': 'un numero de regla, no una cuenta',
  'importing.stale': 'n ya viene escrito con su unidad (count)',
  'status.vat.daysLeft': 'el singular es status.vat.dayLeft',
  'vat.daysLeft': 'el singular es vat.dayLeft',
  'parties.unlinkedCreditMany': 'el singular es parties.unlinkedCredit',
  'aurora.panel.more': 'sin palabra: "Y 1 más"',
  'aurora.home.week': 'un numero de semana, no una cuenta',
  'aurora.home.weekOpen': 'un numero de semana, no una cuenta',
  'aurora.settings.permissions': 'etiqueta y cifra',
  'aurora.process.step': 'un numero de paso, no una cuenta',
  'aurora.process.error.some': 'sin palabra: "(1)"',
};

describe('las cifras con su singular', () => {
  it('cada texto con {n} tiene su <clave>One, salvo los de la lista', () => {
    for (const lang of LANGS) {
      const texts = dictionaries[lang];
      const missing = [...texts]
        .filter(([key, value]) => typeof value === 'string' && value.includes('{n}') && !key.endsWith('One'))
        .filter(([key]) => !texts.has(`${key}One`) && !(key in NO_SINGULAR))
        .map(([key, value]) => `${key}: ${value}`);
      expect(missing, lang).toEqual([]);
    }
    // La lista no guarda claves que ya no estan.
    for (const key of Object.keys(NO_SINGULAR)) expect(dictionaries.nl.has(key), key).toBe(true);
  });

  it('cada <clave>One tiene su plural, y el singular es de verdad para el 1', () => {
    for (const lang of LANGS) {
      for (const [key, value] of dictionaries[lang]) {
        if (!key.endsWith('One') || typeof value !== 'string') continue;
        expect(dictionaries[lang].has(key.slice(0, -3)), `${lang}:${key} sin su plural`).toBe(true);
        expect(value.includes('{n}'), `${lang}:${key}`).toBe(false);
      }
    }
  });

  it('countText() pone el singular solo para el 1', () => {
    const [nl, en, es] = [MESSAGES.nl, MESSAGES.en, MESSAGES.es];
    expect([0, 1, 2].map((n) => countText(nl, 'clients', n))).toEqual(['0 klanten', '1 klant', '2 klanten']);
    expect([0, 1, 2].map((n) => countText(en, 'clients', n))).toEqual(['0 clients', '1 client', '2 clients']);
    expect([0, 1, 2].map((n) => countText(es, 'clients', n))).toEqual(['0 clientes', '1 cliente', '2 clientes']);
    expect([countText(nl, 'days', 1), countText(en, 'times', 1), countText(es, 'times', 3)]).toEqual(['1 dag', 'once', '3 veces']);
    expect(countText(es, 'workdays', 1)).toBe('1 día laborable');
  });
});

// El glosario del castellano (revision del paso 16): i18n/glossary.ts.
const GLOSSARY = ES_GLOSSARY;

function catalogTexts(tree: unknown, path = ''): [string, string][] {
  if (typeof tree === 'string') return [[path, tree]];
  if (Array.isArray(tree)) return tree.flatMap((v, i) => catalogTexts(v, `${path}[${i}]`));
  if (tree && typeof tree === 'object') return Object.entries(tree).flatMap(([k, v]) => catalogTexts(v, path ? `${path}.${k}` : k));
  return [];
}

describe('el glosario del castellano', () => {
  // BTW solo como nombre neerlandes entre parentesis ("Número de IVA (BTW)"), en "BTW
  // verlegd" y como pista de la entrada IVA (nav.vat.hint): quien busca "BTW" la encuentra.
  const allowed = new Set(['nav.vat.hint']);
  it('es.ts no usa las palabras que se dejaron', () => {
    const found: string[] = [];
    for (const [key, value] of dictionaries.es) {
      if (allowed.has(key)) continue;
      for (const text of Array.isArray(value) ? value : [value]) {
        for (const [word, rejected] of Object.entries(GLOSSARY)) if (rejected.test(text)) found.push(`${word} <- ${key}: ${text}`);
      }
    }
    expect(found).toEqual([]);
  });

  it('es.json tampoco: la app y el catalogo dicen lo mismo', () => {
    const found: string[] = [];
    for (const [key, text] of catalogTexts(catalogFor('es'))) {
      for (const [word, rejected] of Object.entries(GLOSSARY)) if (rejected.test(text)) found.push(`${word} <- ${key}: ${text}`);
    }
    expect(found).toEqual([]);
  });

  it('las expresiones ven lo que tienen que ver', () => {
    expect(GLOSSARY.IVA!.test('Importe sin BTW')).toBe(true);
    expect(GLOSSARY.IVA!.test('Número de IVA (BTW)')).toBe(false);
    expect(GLOSSARY.IVA!.test('Autoliquidación (BTW verlegd)')).toBe(false);
    expect(GLOSSARY['nota de crédito']!.test('1 abono aún sin enlazar')).toBe(true);
    expect(GLOSSARY.archivo!.test('Elegir fichero')).toBe(true);
    expect(GLOSSARY.empresa!.test('facturas de la misma parte')).toBe(true);
    expect(GLOSSARY.empresa!.test('Importada en parte')).toBe(false);
    expect(GLOSSARY.anotar!.test('Apuntar un pago ya hecho')).toBe(true);
    expect(glossaryMisses('Esperando a el proveedor')).toEqual(['al (a + el) <- a el']);
    expect(glossaryMisses('Esperando al proveedor')).toEqual([]);
  });
});

describe('el castellano de Aurora, tal cual (especificacion §4.2 I)', () => {
  // Las cadenas del prototipo del dueno (outputs/aurora/src, entrega del 28-10-2026) que la app
  // usa en castellano: la misma frase, letra a letra. En neerlandes e ingles, su traduccion.
  const AURORA_ES: Record<string, string> = {
    'aurora.home.navigate': 'Presiona para navegar', // main.tsx
    'aurora.home.intro': '¿Cómo te puedo ayudar hoy?', // main.tsx
    'aurora.home.open': 'Abrir navegación', // main.tsx
    'aurora.home.close': 'Cerrar navegación', // main.tsx
    'aurora.home.searchTitle': '¿Qué estabas buscando?', // main.tsx
    'aurora.home.searchIntro': 'Encuentra claridad entre tus documentos.', // main.tsx
    'aurora.home.searchThinking': 'Pensando… Buscando entre tus documentos.', // main.tsx
    'aurora.chat.back': 'Volver al espacio', // ai-actions.tsx
    'aurora.process.back': 'Volver al inicio', // processing-workspace.tsx
    'aurora.process.eyebrow': 'UN POCO DE ORDEN. MUCHA CLARIDAD.', // processing-workspace.tsx
    'aurora.process.complete.title': 'He finalizado con el análisis.', // processing-workspace.tsx
    'aurora.archive.upToDate': 'Al corriente', // document-workspace.tsx
    'aurora.archive.openProfile': 'Abrir ficha', // document-workspace.tsx
    'aurora.archive.viewProfile': 'Ver ficha', // document-workspace.tsx
    'aurora.tree.hint':
      'Usa las flechas para moverte. Derecha expande una carpeta; izquierda la cierra o sube al padre. Inicio y Fin saltan a los extremos. Escribe una letra para encontrar el siguiente nombre.', // tree-view.tsx
    'aurora.folder.open': 'Abrir carpeta', // glass-folder-cards.tsx
    'aurora.folder.close': 'Cerrar carpeta', // glass-folder-cards.tsx
    'aurora.folder.filesOf': 'Archivos de {name}', // glass-folder-cards.tsx ('Archivos de '+label)
  };
  it('las frases de Aurora en es.ts son las del prototipo', () => {
    const differ = Object.entries(AURORA_ES).filter(([key, text]) => dictionaries.es.get(key) !== text);
    expect(differ.map(([key, text]) => `${key}: «${dictionaries.es.get(key)}» y no «${text}»`)).toEqual([]);
  });
  it('y en neerlandes e ingles van traducidas, no copiadas', () => {
    for (const lang of ['nl', 'en'] as const) for (const key of Object.keys(AURORA_ES)) expect(dictionaries[lang].get(key), `${lang} ${key}`).not.toBe(AURORA_ES[key]);
  });
});

describe('el glosario del neerlandes y del ingles', () => {
  // Las palabras de la app (revision del paso 17): la werkruimte / the workspace, de postbus /
  // the mailbox, het plafond / the cap, providers (no suppliers); las comillas tipograficas (“…”)
  // y no las del castellano («…»). Y las marcas de nueva y repetida de Aurora (en Documentos, en
  // Procesar y en el resumen) son "herhaald": "dubbel" es el de los avisos de duplicados (B2-B5,
  // V7, K4) y el de un posible duplicado.
  const REJECTED: Record<'nl' | 'en', Record<string, RegExp | [RegExp, RegExp]>> = {
    nl: {
      werkruimte: /\bde ruimte\b/i,
      postbus: /\binbox\b/i,
      plafond: /maximum aan kosten/i,
      herhaald: [/\bdubbel(e)?\b/i, /^aurora\.(bento|folder|archive|process\.complete)\./],
      '“…”': /[«»]/,
    },
    en: {
      workspace: /\bthe space\b/i,
      mailbox: /\binbox\b/i,
      providers: /\bsuppliers?\b/i,
      '“…”': /[«»]/,
    },
  };
  for (const lang of ['nl', 'en'] as const) {
    it(`${lang}.ts y textos/${lang}.json usan las palabras de la app`, () => {
      const found: string[] = [];
      const texts = [...dictionaries[lang]].flatMap(([key, value]) => (Array.isArray(value) ? value : [value]).map((text) => [key, text] as const));
      for (const [key, text] of [...texts, ...catalogTexts(catalogFor(lang))])
        for (const [word, rule] of Object.entries(REJECTED[lang])) {
          const [rejected, keys] = Array.isArray(rule) ? rule : [rule, /./];
          if (keys.test(key) && rejected.test(text)) found.push(`${word} <- ${key}: ${text}`);
        }
      expect(found).toEqual([]);
    });
  }
});

describe('fmt', () => {
  it('rellena los huecos y deja a la vista los que faltan', () => {
    expect(fmt('Factuur {id}', { id: 12 })).toBe('Factuur 12');
    expect(fmt('{a} en {b}', { a: 'x' })).toBe('x en {b}');
    expect(fmt('{a}', { a: '{b}', b: 'no' })).toBe('{b}');
  });
});

describe('idiomas', () => {
  it('neerlandes, ingles y castellano; nada mas', () => {
    expect(LANGS).toEqual(['nl', 'en', 'es']);
    expect(isLang('nl') && isLang('en') && isLang('es')).toBe(true);
    expect(isLang('fr')).toBe(false);
    expect(isLang('ES')).toBe(false);
    expect(isLang(null)).toBe(false);
  });

  it('los textos de dominio tienen las mismas claves en cada idioma', () => {
    const nl = leaves(catalogFor('nl') as unknown as Tree);
    for (const lang of LANGS) {
      expect([...leaves(catalogFor(lang) as unknown as Tree).keys()].sort(), lang).toEqual([...nl.keys()].sort());
    }
  });

  it('cada idioma tiene su propio catalogo de dominio (es.json desde el paso 16)', () => {
    expect(DOMAIN_FALLBACK).toEqual({});
    expect(catalogFor('es')).not.toBe(catalogFor('en'));
    expect(catalogFor('es').idioma).toBe('es');
    expect(catalogFor('en').idioma).toBe('en');
    expect(catalogFor('nl').idioma).toBe('nl');
    expect(DOMAIN_FALLBACK.nl).toBeUndefined();
    expect(DOMAIN_FALLBACK.en).toBeUndefined();
  });
});
