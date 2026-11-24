// What a spec that prints a business's papers with no printer to take them sets up and puts back: Invoicing's issuer
// and series, the cash drawer off, a coffee to sell and the business's printers off; after it, the cash sessions,
// invoices, sales and products it made are gone and the printers and the drawer are back as they were.
import type { Browser } from '@playwright/test';

import { forgetSessions } from './cash-session-helpers';
import { A, login } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanInvoices, ensureIssuer, snapshotSeries } from './invoice-helpers';
import { printersBackOn, printersOff } from './printing-helpers';
import { cleanSales, drawerOff, restoreDrawer } from './sale-helpers';

export interface PrintRun {
  coffee: Product;
  /** The printers that were on before the run (switched off for it: nothing is queued). */
  printersOn: string[];
  /** The cash sessions the run opened. */
  sessions: Set<string>;
}

/** The business ready to print with no printer, and a coffee named `name` with the code `sku` to sell. */
export async function startPrintRun(browser: Browser, name: string, sku: string): Promise<PrintRun> {
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/sale/pos');
  snapshotSeries();
  await ensureIssuer(context);
  await drawerOff(context);
  const coffee = await createProduct(context, { name, sku, price: 150 });
  const printersOn = printersOff();
  await context.close();
  return { coffee, printersOn, sessions: new Set() };
}

/** What `run` made, gone, and the printers and the drawer as the run found them. */
export function endPrintRun(run: PrintRun | undefined): void {
  try {
    forgetSessions(run?.sessions ?? []);
    cleanInvoices();
  } finally {
    printersBackOn(run?.printersOn ?? []);
    cleanSales();
    cleanInventory();
    restoreDrawer();
  }
}
