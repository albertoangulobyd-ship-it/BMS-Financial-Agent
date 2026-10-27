// El renderizador de plantillas contra la referencia de Python: cada caso de
// src/bms_agent/textos/casos.json (los bordes del lenguaje y un hallazgo de cada variante
// de cada regla) tiene que dar exactamente el mismo texto en cada idioma que traiga el caso
// (neerlandes, ingles y castellano: los tres idiomas de la app), y lo mismo en `faltan`.
import { describe, expect, it } from 'vitest';
import casos from '../../../src/bms_agent/textos/casos.json';
import { catalogFor, errorText, findingDetail, templateCatalog, verdict } from './domain';
import { chooseVariant, holds, integerOf, renderDetail, renderTemplate, type RuleTexts } from './templates';
import { LANGS as APP_LANGS, type Lang } from './index';

type Texts = Partial<Record<Lang, string>>;

interface TemplateCase extends Texts {
  plantilla: string;
  valores: unknown;
  faltan: string[];
}

interface DetailCase extends Texts {
  origen: string;
  regla: string;
  resultado: string;
  valores: unknown;
  variante: number;
  faltan: string[];
}

const plantillas = casos.plantillas as unknown as TemplateCase[];
const detalles = casos.detalles as unknown as DetailCase[];
// Los idiomas que trae la referencia de Python (nl, en y, desde el paso 16, es).
const LANGS: Lang[] = APP_LANGS.filter((lang) => typeof plantillas[0]?.[lang] === 'string');

describe('las plantillas, como bms_agent.textos.pintar', () => {
  it('hay casos, en cada idioma de la app', () => {
    expect(plantillas.length).toBeGreaterThan(50);
    expect(LANGS).toEqual([...APP_LANGS]);
  });
  for (const [i, caso] of plantillas.entries()) {
    for (const lang of LANGS) {
      it(`${i} ${lang}: ${caso.plantilla}`, () => {
        const out = renderTemplate(caso.plantilla, caso.valores, templateCatalog(lang));
        expect(out.text).toBe(caso[lang]);
        expect(out.missing).toEqual(caso.faltan);
      });
    }
  }
});

describe('el detalle de cada regla, como bms_agent.textos.detalle', () => {
  it('cubre cada variante de cada regla', () => {
    expect(detalles.length).toBeGreaterThan(250);
    const seen = new Set(detalles.map((d) => `${d.regla}:${d.resultado}:${d.variante}`));
    for (const [rule, texts] of Object.entries(catalogFor('nl').reglas as Record<string, RuleTexts>)) {
      for (const [result, variants] of Object.entries(texts.detalle)) {
        for (let v = 0; v < (variants ?? []).length; v += 1) {
          expect(seen.has(`${rule}:${result}:${v}`), `${rule} ${result} ${v}`).toBe(true);
        }
      }
    }
  });
  for (const [i, caso] of detalles.entries()) {
    for (const lang of LANGS) {
      it(`${i} ${lang}: ${caso.regla} ${caso.resultado} (${caso.origen})`, () => {
        const rule = (catalogFor(lang).reglas as Record<string, RuleTexts>)[caso.regla]!;
        const out = renderDetail(rule, caso.resultado, caso.valores, templateCatalog(lang));
        expect(out.variant).toBe(caso.variante);
        expect(out.text).toBe(caso[lang]);
        expect(out.missing).toEqual(caso.faltan);
        expect(findingDetail(lang, caso.regla, caso.resultado, caso.valores)).toBe(caso[lang]);
      });
    }
  }
});

describe('las piezas', () => {
  it('lee enteros, textos de cifras y fracciones sin floats', () => {
    expect(integerOf(12)).toBe(12n);
    expect(integerOf('181351/2')).toBe(90676n);
    expect(integerOf('-25/4')).toBe(-6n);
    expect(integerOf('1/0')).toBeNull();
    expect(integerOf(1.5)).toBeNull();
    expect(integerOf(true)).toBeNull();
    expect(integerOf('12,5')).toBeNull();
  });

  it('las condiciones: esta, no esta, igual', () => {
    const v = { a: 1, b: [], c: null, d: true, e: { f: 'x' } };
    expect(holds('a', v)).toBe(true);
    expect(holds('b', v)).toBe(false);
    expect(holds('c', v)).toBe(false);
    expect(holds('!c', v)).toBe(true);
    expect(holds('d=true', v)).toBe(true);
    expect(holds('a=1', v)).toBe(true);
    expect(holds('e.f=x', v)).toBe(true);
    expect(holds('z', v)).toBe(false);
  });

  it('una variante con partes escribe las que valen; sin ninguna, sigue', () => {
    const variants = [
      { cuando: [], partes: [{ cuando: ['x'], texto: 'X' }, { cuando: ['y'], texto: 'Y' }] },
      { cuando: [], texto: 'nada' },
    ];
    expect(chooseVariant(variants, { x: 1, y: 2 })).toEqual({ index: 0, templates: ['X', 'Y'] });
    expect(chooseVariant(variants, {})).toEqual({ index: 1, templates: ['nada'] });
  });

  it('lo que sale es texto: el HTML de un documento se queda tal cual', () => {
    const out = renderTemplate('{x}', { x: '<img src=x onerror=alert(1)>' }, templateCatalog('nl'));
    expect(out.text).toBe('<img src=x onerror=alert(1)>');
  });

  it('el veredicto no aprueba nada', () => {
    const clean = verdict('en', { pendientes: 0, aceptados: 0, sin_datos: 0, campos: 0 });
    expect(clean).toMatchObject({ text: 'No system objections', clean: true, main: { state: 'limpia' } });
    const mixed = verdict('nl', { pendientes: 3, aceptados: 1, sin_datos: 0, campos: 2 });
    expect(mixed.text).toBe('Bezwaren van het systeem: 2; Door een medewerker geaccepteerd: 1; Velden te verifiëren: 2');
    // La parte mas seria es la de la pastilla (components/status-pill).
    expect(mixed.main).toEqual({ state: 'objeciones', values: { n: 2 }, text: 'Bezwaren van het systeem: 2' });
    expect(mixed.parts.map((p) => p.state)).toEqual(['objeciones', 'aceptadas', 'campos']);
    expect(verdict('en', { pendientes: 1, aceptados: 1, sin_datos: 0, campos: 1 }).main.state).toBe('campos');
    expect(verdict('en', { pendientes: 0, aceptados: 0, sin_datos: 2, campos: 0 }).main).toMatchObject({
      state: 'limpia_sin_datos',
      text: 'No objections in what was checked; checks without data: 2',
    });
    for (const lang of APP_LANGS) {
      for (const text of Object.values(catalogFor(lang).veredicto)) {
        expect(text).not.toMatch(/goedgekeurd|approved|aprobad/i);
      }
    }
  });

  it('cada codigo de error tiene su texto en cada idioma', () => {
    for (const code of Object.keys(catalogFor('nl').errores)) {
      for (const lang of APP_LANGS) expect(errorText(lang, code), `${lang} ${code}`).toBeTruthy();
    }
    expect(errorText('en', 'no_such_code')).toBeNull();
  });
});
