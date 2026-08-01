import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';

// Flujo navegador -> SDK público -> HTTP real -> runtime -> guest WASM -> Postgres.
// El runtime de esta suite arranca con el conjunto POS, `schedules` y `w140` instalados.
const sdkModule = `/@fs/${resolve(
  import.meta.dirname,
  '../../../../packages/module-sdk/src/index.ts',
)}`;
const DEV_AUTH_HEADERS = {
  'x-hub-id': '00000000-0000-0000-0000-000000000001',
  'x-user-id': 'playwright',
  'x-permissions': '*',
} as const;

test.skip(
  process.env.HUB_RUNTIME_CONTRACT_E2E !== '1',
  'requiere un runtime real con los módulos POS, schedules y el fixture w140 instalados',
);

test('sales falla cerrado si el catálogo fiscal está vacío o no tiene regla aplicable', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(async ({ moduleUrl, authHeaders }) => {
    const { ErploraClient, HttpWsTransport, ErploraError } = await import(
      /* @vite-ignore */ moduleUrl
    );
    const client = new ErploraClient(new HttpWsTransport({ headers: () => authHeaders }));
    const attemptSale = async (taxCategoryKey: string) => {
      try {
        await client.command('sales.complete_sale', {
          items: [{
            product_name: 'Producto fiscal Playwright',
            price: 1_000,
            quantity: 1_000_000,
            tax_category_key: taxCategoryKey,
            tax_rate: 99,
          }],
          tax_included: true,
          amount_tendered: 1_000,
          payment_method_name: 'Efectivo',
        });
        return null;
      } catch (error) {
        if (!(error instanceof ErploraError)) throw error;
        return { code: error.code, message: error.message };
      }
    };

    const noApplicableRule = await attemptSale('playwright.sin.regla.aplicable');
    const rules = await client.query<Array<{ id: string }>>('taxes.rules.list');
    for (const rule of rules) {
      await client.command('taxes.rules.deactivate', { rule_id: rule.id });
    }
    const emptyCatalog = await attemptSale('product.generic');
    const sales = await client.query<unknown[]>('sales.list');

    return { noApplicableRule, emptyCatalog, sales };
  }, { moduleUrl: sdkModule, authHeaders: DEV_AUTH_HEADERS });

  expect(result.noApplicableRule).not.toBeNull();
  expect(result.noApplicableRule?.message).toContain('tax_rule_not_applicable');
  expect(result.emptyCatalog).not.toBeNull();
  expect(result.emptyCatalog?.message).toContain('empty_required_read: taxes.rules.list');
  expect(result.sales).toEqual([]);
});

test('commandResult conserva el resultado WASM calculado con reads autoritativas', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(async ({ moduleUrl, authHeaders }) => {
    const { ErploraClient, HttpWsTransport } = await import(/* @vite-ignore */ moduleUrl);
    const transport = new HttpWsTransport({
      headers: () => authHeaders,
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
  }, { moduleUrl: sdkModule, authHeaders: DEV_AUTH_HEADERS });

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

  const failures = await page.evaluate(async ({ moduleUrl, authHeaders }) => {
    const { ErploraClient, HttpWsTransport, ErploraError } = await import(
      /* @vite-ignore */ moduleUrl
    );
    const client = new ErploraClient(new HttpWsTransport({ headers: () => authHeaders }));
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
  }, { moduleUrl: sdkModule, authHeaders: DEV_AUTH_HEADERS });

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

  const rows = await page.evaluate(async ({ moduleUrl, authHeaders }) => {
    const { ErploraClient, HttpWsTransport } = await import(/* @vite-ignore */ moduleUrl);
    const client = new ErploraClient(new HttpWsTransport({ headers: () => authHeaders }));
    return client.query('w140.bridge.inspect', { at: '2026-08-01T09:07:00Z' });
  }, { moduleUrl: sdkModule, authHeaders: DEV_AUTH_HEADERS });

  expect(rows).toEqual([{ date: '2026-08-01', time: '09:07', dow: 5 }]);
});
