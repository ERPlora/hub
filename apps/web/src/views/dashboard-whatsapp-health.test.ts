// hub#1629 — WhatsApp that stopped on its own is said on the home panel, next to the printer.
//
// `whatsappLine` (system-health) decides the sentence; these tests pin that the panel actually
// asks for the numbers, feeds them to that rule, and paints EVERY health line with its way out —
// not only the printer's, which is all the strip could hold before.
//
// Hub pattern (dashboard-import-refresh.test.ts): read the SFC source and assert the contract.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const dashboard = readFileSync(new URL('./DashboardPage.vue', import.meta.url), 'utf8');

function functionBody(source: string, signature: string): string {
  const start = source.indexOf(signature);
  expect(start, `${signature} not found`).toBeGreaterThan(-1);
  return source.slice(start, source.indexOf('\n}\n', start) + 2);
}

describe('the panel says when WhatsApp stopped on its own (hub#1629)', () => {
  it('reads the connected numbers while loading the hub health', () => {
    const body = functionBody(dashboard, 'async function loadSystemHealth');
    expect(body).toContain('fetchWhatsAppNumbers()');
  });

  it('a failed read is «we do not know», never an empty list of numbers', () => {
    const body = functionBody(dashboard, 'async function loadSystemHealth');
    expect(body).toMatch(/whatsappNumbers\.value = null/);
    expect(body).not.toMatch(/whatsappNumbers\.value = \[\]/);
  });

  it('only asks when the WhatsApp module is running — no call for a hub without it', () => {
    const body = functionBody(dashboard, 'async function loadSystemHealth');
    const ask = body.indexOf('fetchWhatsAppNumbers()');
    const guard = body.lastIndexOf('isWhatsAppInstalled(', ask);
    expect(guard, 'fetchWhatsAppNumbers must sit behind isWhatsAppInstalled').toBeGreaterThan(-1);
  });

  it('feeds the numbers and the installed modules to whatsappLine', () => {
    expect(dashboard).toMatch(/whatsappLine\(whatsappNumbers\.value, installedModules\.value\)/);
  });

  it('puts the WhatsApp line among the ones the strip paints', () => {
    const start = dashboard.indexOf('const healthLines');
    expect(start, 'healthLines not found').toBeGreaterThan(-1);
    const computedBody = dashboard.slice(start, dashboard.indexOf(');\n', start));
    expect(computedBody).toContain('printerHealth.value');
    expect(computedBody).toContain('whatsappHealth.value');
  });

  it('paints every health line with its own action, not only the printer', () => {
    expect(dashboard).toMatch(/v-for="line in healthLines"/);
    expect(dashboard).toMatch(/:router-link="line\.action\.route"/);
    expect(dashboard).not.toMatch(/printerHealth\?\.action/);
  });
});
