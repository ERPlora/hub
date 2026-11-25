// «Download PDF» of the open invoice (INVOICE-F25): the server's file, under its name, for whoever sees the invoice.
import { toastError } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { INVOICE, setup } from '../__tests__/invoice-detail';
import { ACCOUNTANT, EMPLOYEE, flush } from '../__tests__/mount-invoice';
import { browserDownloads, insideTheAppSaving, outOfTheApp } from '../../../../base/frontend/__tests__/app-download';

const FILE = { filename: 'FACT-2026-000001.pdf', content_type: 'application/pdf', content_base64: btoa('%PDF-1.7 x') };

afterEach(() => {
  outOfTheApp();
  vi.restoreAllMocks();
});

/** The open invoice, the addresses the page asks for and what the server answers the PDF with. */
async function opened(invoice: object = {}, options: Parameters<typeof setup>[0] = {}, answer: () => Response | Promise<Response> = () => Response.json(FILE)) {
  const s = await setup(options);
  await s.show({ ...INVOICE, ...invoice });
  const asked: URL[] = [];
  s.net.onApi(({ url }) => {
    asked.push(new URL(url, 'http://localhost'));
    return answer();
  });
  const button = () => s.find('invoice-detail-pdf');
  const disabled = () => s.wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === 'invoice-detail-pdf')?.props('disabled');
  const press = async () => {
    await button().trigger('click');
    await flush();
    await flush();
  };
  return { ...s, asked, button, disabled, press };
}

describe('InvoiceDetailPage: «Download PDF»', () => {
  it('asks the server for the invoice’s PDF and saves it under its name', async () => {
    const s = await opened();
    const saved = browserDownloads();
    expect(s.button().text()).toBe('Download PDF');
    await s.press();
    const [url] = s.asked;
    expect(s.asked).toHaveLength(1);
    expect(url.pathname).toBe('/api/invoice/invoices/pdf');
    expect(Object.fromEntries(url.searchParams)).toEqual({ invoice_id: 'i1', duplicate: 'false' });
    expect(saved.map((file) => file.name)).toEqual(['FACT-2026-000001.pdf']);
    expect(saved[0].blob.type).toBe('application/pdf');
    expect(await saved[0].blob.text()).toBe('%PDF-1.7 x');
  });

  it.each(['sale', 'refund', 'void'])('a document of a %s is a copy, as its paper', async (source_type) => {
    const s = await opened({ source_type });
    browserDownloads();
    await s.press();
    expect(s.asked[0].searchParams.get('duplicate')).toBe('true');
  });

  it.each([['the accountancy firm', ACCOUNTANT], ['an employee', EMPLOYEE]])('is offered to %s', async (_who, session) => {
    const s = await opened({}, { session });
    expect(s.button().exists()).toBe(true);
  });

  it('says it is being prepared and takes no second press meanwhile', async () => {
    let answer: (response: Response) => void = () => {};
    const s = await opened({}, {}, () => new Promise<Response>((resolve) => (answer = resolve)));
    browserDownloads();
    await s.press();
    expect(s.button().text()).toBe('Preparing…');
    expect(s.disabled()).toBe(true);
    await s.press();
    expect(s.asked).toHaveLength(1);

    answer(Response.json(FILE));
    await flush();
    await flush();
    expect(s.button().text()).toBe('Download PDF');
    expect(s.disabled()).toBe(false);
  });

  it('says why when there is no PDF, and can be pressed again', async () => {
    const refusal = { error: { code: 'invoice.pdf_unavailable', message: 'The PDF cannot be made right now. Try again later.' } };
    const s = await opened({}, {}, () => Response.json(refusal, { status: 503 }));
    const saved = browserDownloads();
    await s.press();
    expect(toastError).toHaveBeenCalledWith('The PDF could not be downloaded: The PDF cannot be made right now. Try again later.');
    expect(saved).toEqual([]);
    await s.press();
    expect(s.asked).toHaveLength(2);
  });

  it('inside the installed app it is saved in Downloads', async () => {
    const s = await opened();
    const invoke = insideTheAppSaving({ path: 'Download/FACT-2026-000001.pdf' });
    await s.press();
    expect(invoke).toHaveBeenCalledWith('save_download', { name: 'FACT-2026-000001.pdf', dataBase64: btoa('%PDF-1.7 x') });
  });

  it('is as tall as «Print / PDF» beside it', async () => {
    const s = await opened();
    const size = (testid: string) => s.wrapper.findAllComponents(IonButton).find((b) => b.attributes('data-testid') === testid)?.props('size');
    expect(size('invoice-detail-pdf')).toBe(size('invoice-detail-print'));
  });

  it('speaks Spanish', async () => {
    const s = await opened({}, { locale: 'es' }, () => Response.json({ error: { code: 'x', message: 'Motivo.' } }, { status: 503 }));
    expect(s.button().text()).toBe('Descargar PDF');
    await s.press();
    expect(toastError).toHaveBeenCalledWith('No se ha podido descargar el PDF: Motivo.');
  });
});
