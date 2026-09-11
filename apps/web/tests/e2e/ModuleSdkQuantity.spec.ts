import { expect, test } from '../bench-boot';
import { resolve } from 'node:path';

const quantityModule = `/@fs/${resolve(
  import.meta.dirname,
  '../../../../packages/module-sdk/src/quantity.ts',
)}`;

test('el navegador carga el contrato público de cantidades del SDK', async ({ page }) => {
  await page.goto('/');

  const result = await page.evaluate(async (moduleUrl) => {
    const units = await import(/* @vite-ignore */ moduleUrl);
    return {
      halfKg: units.parseQuantity('0,5'),
      rendered: units.formatQuantity(1_250_000),
      exactGrid: units.onGrid(500_000, 1_000),
      rejectedPrecision: units.parseQuantity('0.1234567'),
    };
  }, quantityModule);

  expect(result).toEqual({
    halfKg: 500_000,
    rendered: '1.25',
    exactGrid: true,
    rejectedPrecision: null,
  });
});
