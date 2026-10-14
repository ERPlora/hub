// «Export CSV» and «Import CSV» in Ioan's Chrome (CUSTOMER-F09, F08): the export downloads
// `customers.csv` with every card matching the search (not just the page shown); the import reads a
// spreadsheet's CSV (Spanish headers, semicolons), creates the good rows and reports the skipped one
// with its line and reason; the live list shows the new cards by themselves.
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { cleanUp, createCard, customersReady, e2eName, rowNamed, searchList, spanishMobile } from './customer-helpers';
import { A, login, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

test('«Export CSV» downloads customers.csv with every card matching the search', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const marker = e2eName('Export');
  const phone = spanishMobile();
  await createCard(context, { name: `${marker} one`, phone });
  await createCard(context, { name: `${marker} two` });
  await page.goto('/customer/customers');
  await customersReady(page);
  await searchList(page, 'customer-list', marker);
  await expect(shown(page).locator('[data-testid=customer-list-row]')).toHaveCount(2);

  const download = page.waitForEvent('download');
  await shown(page).locator('[data-testid=customer-export]').click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('customers.csv');
  const text = readFileSync((await file.path()) as string, 'utf8').replace(/^﻿/, '');
  const [header, ...rows] = text.trim().split('\n');
  expect(header.split(',').slice(0, 3)).toEqual(['name', 'email', 'phone']);
  expect(rows).toHaveLength(2);
  expect(rows.join('\n')).toContain(`${marker} one`);
  // A value starting with «+» is guarded with an apostrophe so a spreadsheet does not run it.
  expect(rows.join('\n')).toContain(`'+34${phone}`);
});

test('«Import CSV» creates the good rows of a spreadsheet\'s file and reports the skipped one', async ({ page }) => {
  await login(page, A, '/customer/customers');
  await customersReady(page);
  const marker = e2eName('Import');
  const csv = join(tmpdir(), `customers-${Date.now()}.csv`);
  writeFileSync(
    csv,
    ['Nombre;Teléfono;Email;País;Etapa', `${marker} Ana;${spanishMobile()};;España;`, `;${spanishMobile()};nobody@example.com;;`, `${marker} Luis;;;Narnia;vip`].join('\n'),
  );
  await shown(page).locator('[data-testid=customer-import] ~ input[type=file]').setInputFiles(csv);
  const report = shown(page).locator('[data-testid=customer-import-report]');
  await expect(report.locator('[data-testid=customer-import-summary]')).toHaveText(/3 rows — 2 created, 1 skipped|3 filas — 2 creadas, 1 omitidas/);
  await expect(report.locator('[data-testid=customer-import-skipped] li')).toHaveText([/^(Row|Fila) 3: /]);
  await expect(report.locator('[data-testid=customer-import-warnings] li')).toHaveText([/^(Row|Fila) 4: /]);
  await page.screenshot({ path: shot('customer-import-report') });

  await searchList(page, 'customer-list', marker);
  await expect(rowNamed(page, 'customer-list', `${marker} Ana`)).toBeVisible();
  await expect(rowNamed(page, 'customer-list', `${marker} Luis`)).toContainText(/VIP/);
  await report.locator('[data-testid=customer-import-close]').click();
  await expect(report).toBeHidden();
});
