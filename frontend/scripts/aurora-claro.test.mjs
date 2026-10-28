// El tema claro de Aurora (scripts/aurora-claro.mjs): src/aurora/claro.css es el que escribe el
// script (nadie lo edita a mano ni se queda viejo al cambiar una hoja), la inversion conserva
// el matiz y el alfa, y las superficies claras con su texto oscuro (el boton .primary, la hoja de
// papel) se quedan como en el oscuro.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { TEXT_MAX_L, build, invert, invertValue } from './aurora-claro.mjs';

describe('aurora-claro', () => {
  it('claro.css es el que escribe el script', () => {
    const current = readFileSync(fileURLToPath(new URL('../src/aurora/claro.css', import.meta.url)), 'utf8');
    expect(current).toBe(build());
  });

  it('el negro pasa a casi blanco, el blanco a casi negro y el alfa se queda', () => {
    const [r, g, b] = invert([0, 0, 0, 1]);
    expect(Math.min(r, g, b)).toBeGreaterThan(240);
    const white = invert([255, 255, 255, 1]);
    expect(Math.max(...white.slice(0, 3))).toBeLessThan(20);
    expect(invertValue('rgba(255, 255, 255, .08)')).toMatch(/^#[0-9a-f]{6}14$/);
    expect(invertValue('12px')).toBeNull();
  });

  it('el texto en claro se lee: el gris apagado de la rueda queda a 4,5:1 sobre el fondo del panel', () => {
    const lum = ([r, g, b]) => {
      const f = (v) => {
        const c = v / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    // El fondo del panel en claro, medido en el navegador (su color sobre la pagina).
    const panel = [0xd8, 0xd8, 0xe0];
    for (const grey of [[0x54, 0x4e, 0x60], [0x6e, 0x65, 0x7a], [0x77, 0x71, 0x7f], [0x82, 0x77, 0x8d]]) {
      const text = invert([...grey, 1], TEXT_MAX_L);
      expect((lum(panel) + 0.05) / (lum(text) + 0.05), grey.join(',')).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('las superficies claras (texto oscuro sobre fondo claro) y lo de dentro no se invierten', () => {
    const css = build();
    for (const selector of ['.primary', '.ws-paper', '.ws-paper dt', '.ws-paper hr', '.ws-download', '.search-submit', '.search-submit:hover', '.skip-link']) {
      expect(css, selector).not.toContain(`\nhtml:not(.dark) ${selector}{`);
    }
    // Lo demas, si: el panel y su texto.
    expect(css).toContain('html:not(.dark) .panel{');
    expect(css).toMatch(/html:not\(\.dark\) \.outline,html:not\(\.dark\) \.primary\{/);
  });

  it('Procesar es negro con la suricata blanca en los dos temas: no se invierte, y la marca sigue blanca', () => {
    const css = build();
    for (const selector of ['.processing-', '.flow-button', '.zur-', '.pc-', '.analysis-entry{', '.analysis-counts']) {
      expect(css, selector).not.toContain(`html:not(.dark) ${selector}`);
    }
    // Sin esto, «finance» salia casi negro sobre el negro de Procesar (axe, en claro).
    expect(css).toContain('html:not(.dark) .process-mode .bms-brand{color:#fff}');
    expect(css).toContain('html:not(.dark) .process-mode .bms-brand svg{filter:none}');
    expect(css).toContain('html:not(.dark) .process-mode .bms-brand>span{border-left:1px solid #ffffff26}');
  });
});
