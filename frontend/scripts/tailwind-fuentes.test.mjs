// Tailwind lee solo lo que cubre la huella de lo construido: ninguna prueba (src/**/*.test.ts),
// nada de e2e/ ni de scripts/, ni la configuracion de Playwright. Si leyera algo de eso, una
// clase escrita alli cambiaria el CSS construido y la huella (fuente.json) no lo veria.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { outsideInputs, scannedFiles } from './tailwind-fuentes.mjs';

const config = JSON.parse(readFileSync(new URL('../build-inputs.json', import.meta.url), 'utf8'));

describe('lo que lee Tailwind', () => {
  it('es src (sin pruebas) e index.html', async () => {
    const files = await scannedFiles();
    expect(files).toContain('frontend/index.html');
    expect(files).toContain('frontend/src/components/ui/status.tsx');
    expect(files.filter((f) => !f.startsWith('frontend/src/') && f !== 'frontend/index.html')).toEqual([]);
    expect(files.filter((f) => /\.test\.tsx?$/.test(f))).toEqual([]);
  });

  it('esta todo en la huella (build-inputs.json)', async () => {
    const files = await scannedFiles();
    const covered = files.filter(
      (f) => config.include.some((entry) => f === entry || f.startsWith(`${entry}/`)) &&
        !config.exclude.some((suffix) => f.endsWith(suffix))
    );
    expect(covered).toEqual(files);
    expect(await outsideInputs(covered)).toEqual([]);
  });
});
