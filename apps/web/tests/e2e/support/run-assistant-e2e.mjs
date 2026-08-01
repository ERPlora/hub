import { createServer } from 'node:net';
import { spawnSync } from 'node:child_process';

async function reservePort() {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('no se pudo reservar un puerto');
  return { server, port: address.port };
}

// Mantiene las cuatro reservas abiertas a la vez para que el SO no entregue el mismo puerto dos
// veces. Se liberan justo antes de arrancar Playwright; cada invocación paralela obtiene su juego.
const reservations = await Promise.all(Array.from({ length: 4 }, reservePort));
await Promise.all(reservations.map(({ server }) => new Promise((resolve) => server.close(resolve))));
const [webPort, runtimePort, cloudPort, pgPort] = reservations.map(({ port }) => String(port));

const result = spawnSync(
  'pnpm',
  ['exec', 'playwright', 'test', '--config', 'tests/playwright.assistant.config.ts'],
  {
    stdio: 'inherit',
    env: {
      ...process.env,
      ASSISTANT_E2E_WEB_PORT: webPort,
      ASSISTANT_E2E_RUNTIME_PORT: runtimePort,
      ASSISTANT_E2E_CLOUD_PORT: cloudPort,
      ASSISTANT_E2E_PG_PORT: pgPort,
    },
  },
);
process.exit(result.status ?? 1);
