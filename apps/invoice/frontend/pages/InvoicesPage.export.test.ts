// «Download in Excel» of Invoices: what the list keeps, as the server's file, for whoever sees everyone's invoices.
import { toastError } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ACCOUNTANT, EMPLOYEE, flush } from '../__tests__/mount-invoice';
import { EMPTY, PAGE, setup } from '../__tests__/invoices-page';
import { browserDownloads, outOfTheApp } from '../../../../base/frontend/__tests__/app-download';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));

afterEach(() => {
  outOfTheApp();
  vi.restoreAllMocks();
});

describe('InvoicesPage: «Download in Excel»', () => {
  const FILE = { filename: 'invoices.xlsx', content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', invoices: 2, content_base64: btoa('PK-xlsx') };
  const button = (s: Awaited<ReturnType<typeof setup>>) => s.wrapper.find('[data-testid="invoice-export"]');

  it('is offered to whoever sees everyone’s invoices, and to nobody else', async () => {
    const owner = await setup();
    expect(button(owner).text()).toBe('Download in Excel');
    const employee = await setup({ session: EMPLOYEE });
    expect(button(employee).exists()).toBe(false);
  });

  it('downloads what the list shows: its filters and its search, with neither its sort nor its page', async () => {
    const s = await setup({ session: ACCOUNTANT });
    await s.show(PAGE);
    await s.filter({ issue_date_from: '2026-10-01', issue_date_to: '2026-10-31' });
    await s.emit('update:search', ' pérez ');
    const asked: string[] = [];
    s.net.onApi(({ url }) => (asked.push(url), Response.json(FILE)));
    const saved = browserDownloads();
    await button(s).trigger('click');
    await flush();
    await flush();
    const [url] = asked.map((u) => new URL(u, 'http://localhost'));
    expect(url.pathname).toBe('/api/invoice/invoices/export');
    expect(Object.fromEntries(url.searchParams)).toEqual({ issue_date_from: '2026-10-01', issue_date_to: '2026-10-31', search: 'pérez' });
    expect(saved.map((file) => file.name)).toEqual(['invoices.xlsx']);
    expect(saved[0].blob.type).toBe(FILE.content_type);
    expect(await saved[0].blob.text()).toBe('PK-xlsx');
  });

  it('says why when the file is refused', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.net.onApi(() => Response.json({ error: { code: 'base.hub_busy', message: 'Your business is busy.' } }, { status: 503 }));
    await button(s).trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('The invoices could not be downloaded: Your business is busy.');
  });

  it('waits for the list: nothing to download while it is loading or empty', async () => {
    const s = await setup();
    const disabled = () => s.wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === 'invoice-export')?.props('disabled');
    expect(disabled()).toBe(true);
    await s.show(PAGE);
    expect(disabled()).toBe(false);
    await s.filter({ status: 'paid' });
    await s.show(EMPTY);
    expect(disabled()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(button(s).text()).toBe('Descargar en Excel');
  });
});
