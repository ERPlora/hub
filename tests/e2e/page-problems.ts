// What goes wrong in a page while a spec runs: CSP violations, console errors and warnings, and uncaught errors.
import type { Page } from '@playwright/test';

import { onSaas } from './saas';

/** Collects CSP violations (in-page listener), console errors and uncaught page errors. */
export async function collectProblems(
  page: Page,
): Promise<() => Promise<{ csp: unknown[]; console: string[]; warnings: string[]; page: string[] }>> {
  const consoleErrors: string[] = [];
  const warnings: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (msg) => {
    if (onSaas(page)) return;
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') warnings.push(msg.text());
  });
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: unknown[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      w.__csp.push({ directive: e.violatedDirective, blocked: e.blockedURI, sample: e.sample, source: e.sourceFile });
    });
  });
  return async () => ({
    csp: await page.evaluate(() => (window as unknown as { __csp?: unknown[] }).__csp ?? []),
    console: consoleErrors,
    warnings,
    page: pageErrors,
  });
}
