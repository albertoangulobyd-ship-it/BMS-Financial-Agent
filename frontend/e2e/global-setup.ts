// Antes de las pruebas: una base de prueba nueva en una carpeta temporal, el servidor de
// verdad (bms-agent serve) en un puerto libre de 127.0.0.1 sobre esa base, y los tokens
// de las dos personas de prueba. Al terminar, se para el servidor y se borra la carpeta.
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = fileURLToPath(new URL('../..', import.meta.url));

function python(): string {
  if (process.env.BMS_PYTHON) return process.env.BMS_PYTHON;
  for (const candidate of [join(repo, '.venv', 'bin', 'python'), join(repo, '.venv', 'Scripts', 'python.exe')]) {
    if (existsSync(candidate)) return candidate;
  }
  return 'python';
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

async function waitFor(url: string, child: ChildProcess, log: () => string): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`bms-agent serve se ha parado:\n${log()}`);
    try {
      const response = await fetch(url);
      if (response.status === 200) return;
    } catch {
      // Aun no escucha.
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`bms-agent serve no contesta en ${url}:\n${log()}`);
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  const work = mkdtempSync(join(tmpdir(), 'bms-e2e-'));
  const env: NodeJS.ProcessEnv = { ...process.env, PYTHONPATH: join(repo, 'src'), PYTHONUTF8: '1' };
  delete env.BMS_DB;
  const created = spawnSync(python(), [join(repo, 'scripts', 'crear_demo_e2e.py'), '--carpeta', join(work, 'datos')], {
    cwd: work,
    env,
    encoding: 'utf8',
  });
  if (created.status !== 0) {
    throw new Error(`No se ha podido crear la base de prueba:\n${created.stdout}\n${created.stderr}`);
  }
  const lines = created.stdout.trim().split('\n');
  const demo = JSON.parse(lines[lines.length - 1]!) as { db: string; tokens: Record<string, string> };

  // Las ordenes del servidor van a esta base y a ninguna otra.
  env.BMS_DB = demo.db;
  const port = await freePort();
  let output = '';
  const server = spawn(
    python(),
    ['-m', 'bms_agent.cli', 'serve', '--db', demo.db, '--puerto', String(port),
      '--facturas', join(work, 'facturas'), '--out', join(work, 'out')],
    { cwd: work, env, stdio: ['ignore', 'pipe', 'pipe'] }
  );
  server.stdout?.on('data', (chunk: Buffer) => (output += chunk.toString()));
  server.stderr?.on('data', (chunk: Buffer) => (output += chunk.toString()));
  const base = `http://127.0.0.1:${port}`;
  await waitFor(`${base}/app`, server, () => output);

  process.env.BMS_E2E_URL = base;
  process.env.BMS_E2E_TOKEN_ANA = demo.tokens['Ana Demo'];
  process.env.BMS_E2E_TOKEN_BRAM = demo.tokens['Bram Demo'];

  return async () => {
    server.kill();
    await new Promise((r) => setTimeout(r, 300));
    rmSync(work, { recursive: true, force: true });
  };
}
