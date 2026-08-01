import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';

// Flujo navegador -> SDK público -> HTTP real -> runtime -> guest WASM -> Postgres.
// El runtime de esta suite debe arrancar con los módulos `schedules` y `w140` instalados.
const sdkModule = `/@fs/${resolve(
  import.meta.dirname,
  '../../../../packages/module-sdk/src/index.ts',
)}`;

test.skip(
  process.env.HUB_RUNTIME_CONTRACT_E2E !== '1',
  'requiere un runtime real con schedules y el fixture w140 instalados',
);

test('commandResult conserva el resultado WASM calculado con reads autoritativas', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(async ({ moduleUrl }) => {
    const { ErploraClient, HttpWsTransport } = await import(/* @vite-ignore */ moduleUrl);
    const transport = new HttpWsTransport({
      headers: () => ({
        'x-hub-id': 'h1',
        'x-user-id': 'playwright',
        'x-permissions': '*',
      }),
    });
    const client = new ErploraClient(transport);

    // Una fecha suficientemente variable permite repetir el E2E contra la misma BD de desarrollo.
    const stamp = Date.now();
    const year = 2050 + (Math.floor(stamp / 86_400_000) % 40);
    const day = 1 + (stamp % 27);
    const date = `${year}-12-${String(day).padStart(2, '0')}`;
    await client.command('schedules.special_days.create', {
      date,
      name: 'Cierre Playwright',
      is_closed: true,
    });

    // No se envían filas internas: el host las consulta con hub_id del contexto y el guest las
    // recibe en context.reads. commandResult devuelve solo el canal público de negocio.
    return client.commandResult<{ is_open: boolean; reason: string; today: string }>(
      'schedules.is_open',
      { when: `${date}T12:00:00Z` },
    );
  }, { moduleUrl: sdkModule });

  expect(result).toEqual({
    is_open: false,
    reason: 'Cierre Playwright',
    today: result.today,
    current_time: '12:00',
  });
  expect(result.today).toMatch(/^20\d{2}-12-\d{2}$/);
});

test('el SDK conserva el code de dominio namespaced del runtime', async ({ page }) => {
  await page.goto('/');

  const failures = await page.evaluate(async ({ moduleUrl }) => {
    const { ErploraClient, HttpWsTransport, ErploraError } = await import(
      /* @vite-ignore */ moduleUrl
    );
    const client = new ErploraClient(new HttpWsTransport({
      headers: () => ({
        'x-hub-id': 'h1',
        'x-user-id': 'playwright',
        'x-permissions': '*',
      }),
    }));
    const capture = async (name: string, payload: Record<string, unknown>) => {
      try {
        await client.command(name, payload);
        return null;
      } catch (error) {
        if (!(error instanceof ErploraError)) throw error;
        return { code: error.code, message: error.message };
      }
    };
    return {
      wasm: await capture('schedules.is_open', { when: 'fecha-invalida' }),
      expectRows: await capture('w140.items.consume', { item_id: 'missing' }),
    };
  }, { moduleUrl: sdkModule });

  expect(failures.wasm).toEqual({
    code: 'schedules.invalid_date',
    message: "'when' inválido ('fecha-invalida', se espera YYYY-MM-DDTHH:MM)",
  });
  expect(failures.expectRows).toEqual({
    code: 'w140.insufficient_stock',
    message: 'No hay stock suficiente',
  });
});

test('una query del navegador ejecuta las funciones-puente SQL del contrato', async ({ page }) => {
  await page.goto('/');

  const rows = await page.evaluate(async ({ moduleUrl }) => {
    const { ErploraClient, HttpWsTransport } = await import(/* @vite-ignore */ moduleUrl);
    const client = new ErploraClient(new HttpWsTransport({
      headers: () => ({
        'x-hub-id': 'h1',
        'x-user-id': 'playwright',
        'x-permissions': '*',
      }),
    }));
    return client.query('w140.bridge.inspect', { at: '2026-08-01T09:07:00Z' });
  }, { moduleUrl: sdkModule });

  expect(rows).toEqual([{ date: '2026-08-01', time: '09:07', dow: 5 }]);
});
