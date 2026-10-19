// Las pruebas de la app en un navegador de verdad (Chromium de Playwright, sin bajar
// nada: PLAYWRIGHT_BROWSERS_PATH apunta al que ya esta instalado). Cada pasada levanta el
// servidor de verdad (bms-agent serve) sobre una base de prueba recien creada en una
// carpeta temporal (e2e/global-setup.ts). Un solo trabajador: todas las pruebas usan la
// misma base y el mismo servidor.
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results/playwright',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: 'nl-NL',
    timezoneId: 'Europe/Amsterdam',
    colorScheme: 'light',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    serviceWorkers: 'block',
  },
});
