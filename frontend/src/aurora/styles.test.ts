// styles.css de Aurora es el del dueno tal cual (especificacion §4.2): sin el @import de Tailwind
// (cambio C), con la regla de §1.1 al final (cambio B) y nada mas; tampoco una capa alrededor de
// su base (lo que la puerta del paso 17 encontro: `@layer base`). La huella es la del fichero de la
// entrega del 28-10-2026 sin su primera linea (`@import 'tailwindcss';`).
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8');
const OWNER_SHA256 = '9a5a3460700298160bcce42959030dc6dccd71e4bf4b1a2499ee4f3c9917fd83';
const RULE_1_1 = '\n\n/* BMS (§1.1): o el menu o una pantalla. Lo que Aurora ya hace a 1150 px o menos, en todos los anchos. */\n.has-panel .navigation{display:none}';

describe('styles.css de Aurora', () => {
  const body = css.slice(css.indexOf('*/') + 2).trim();

  it('acaba con la regla de §1.1 y nada mas', () => {
    expect(body.endsWith(RULE_1_1)).toBe(true);
  });

  it('lo de antes es el fichero del dueno, letra a letra, sin capa', () => {
    const owner = body.slice(0, -RULE_1_1.length);
    expect(owner).not.toContain('@layer');
    expect(owner).not.toContain('@import');
    expect(owner.startsWith(':root{font-family:Inter')).toBe(true);
    expect(createHash('sha256').update(owner).digest('hex')).toBe(OWNER_SHA256);
  });
});
