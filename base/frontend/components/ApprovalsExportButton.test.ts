// «Export CSV» of Employees › Approvals (BASE-F85; the old hub exported its record): the server writes `approvals.csv`
// with every approval the list's search and filters keep (not only the newest it shows), in the person's language;
// this hands the file to the browser, with a byte-order mark first so a spreadsheet reads the accents.
import { toastError } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import ApprovalsExportButton from './ApprovalsExportButton.vue';

const mocks = vi.hoisted(() => ({ saveFile: vi.fn() }));
vi.mock('../lib/data', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/data')>()),
  saveFile: mocks.saveFile,
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastError: vi.fn(() => Promise.resolve()),
}));

beforeEach(() => {
  mocks.saveFile.mockClear();
  vi.mocked(toastError).mockClear();
});

const FILE = { filename: 'approvals.csv', content_type: 'text/csv', rows: 1, csv: 'Cuándo,Acción\r\n2026-10-24 11:30,Anular\r\n' };

describe('ApprovalsExportButton', () => {
  it('asks the server for the file with the search and the filters on screen, and downloads it', async () => {
    const urls: string[] = [];
    const query = { search: 'eva', at_from: '2026-10-01', operation: 'sale.sale.void', way: 'pin', used: 'false' };
    const m = await mountBase(ApprovalsExportButton, {
      props: { query },
      onApi: ({ url }) => (urls.push(url), Response.json(FILE)),
    });
    const button = m.wrapper.get('[data-testid="approvals-export"]');
    expect(button.text()).toBe('Export CSV');
    await button.trigger('click');
    await flush();
    const url = new URL(urls[0], 'http://a.localhost');
    expect([url.pathname, Object.fromEntries(url.searchParams)]).toEqual(['/api/approvals/export', query]);
    expect(mocks.saveFile).toHaveBeenCalledOnce();
    const [name, blob] = mocks.saveFile.mock.calls[0] as [string, Blob];
    expect([name, blob.type]).toEqual(['approvals.csv', 'text/csv']);
    expect(await blob.text()).toBe(`﻿${FILE.csv}`);
  });

  it('says it is exporting and takes no second click meanwhile', async () => {
    let answer: (response: Response) => void = () => {};
    const m = await mountBase(ApprovalsExportButton, {
      props: { query: {} },
      locale: 'es',
      onApi: () => new Promise<Response>((resolve) => (answer = resolve)),
    });
    const button = m.wrapper.get('[data-testid="approvals-export"]');
    expect(button.text()).toBe('Exportar CSV');
    await button.trigger('click');
    await flush();
    expect(button.text()).toBe('Exportando…');
    expect(button.attributes('disabled')).toBeDefined();
    answer(Response.json(FILE));
    await flush();
    expect(button.text()).toBe('Exportar CSV');
    expect(button.attributes('disabled')).toBeUndefined();
  });

  it('a refusal is told in a toast with its reason, and nothing is downloaded', async () => {
    const m = await mountBase(ApprovalsExportButton, {
      props: { query: {} },
      onApi: () =>
        Response.json({ error: { code: 'permission_denied', message: 'You do not have permission to do that.' } }, { status: 403 }),
    });
    await m.wrapper.get('[data-testid="approvals-export"]').trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('The approvals could not be exported: You do not have permission to do that.');
    expect(mocks.saveFile).not.toHaveBeenCalled();
  });
});
