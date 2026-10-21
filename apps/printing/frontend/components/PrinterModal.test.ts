// «New printer» / «Edit printer» (PRINTING-F03, F04): its name, connection, address (IP and port, MAC or
// queue; none for the system printer), paper, role and whether it is active. «Save» adds it or saves it and
// says so; a refusal is said at its field, in the server's words.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, ionToggle, ionValue, mountPrinting } from '../__tests__/mount-printing';
import type { PrinterDraft } from '../lib/discovery';
import type { PrinterOut } from '../operations';
import PrinterModal from './PrinterModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const TILL = {
  id: 'p1',
  name: 'Till',
  kind: 'network',
  address: '192.168.1.50',
  port: 9100,
  paper_width: 80,
  usage: 'receipt',
  is_active: true,
} as PrinterOut;

async function setup(printer: PrinterOut | null = null, draft: PrinterDraft | null = null) {
  const m = await mountPrinting(PrinterModal, { props: { open: true, printer, draft } });
  const field = (name: string) => m.inDoc(`printing-printer-${name}`);
  const submit = () => click(m.inDoc('printing-printer-submit'));
  return { ...m, field, submit };
}

describe('PrinterModal', () => {
  it('adds a network printer: port 9100 and 80 mm unless told', async () => {
    const s = await setup();
    expect(s.inDoc('printing-printer')?.getAttribute('aria-label')).toBe('New printer');
    expect(prop(s.field('port'), 'value')).toBe('9100');
    // The app prints 32 characters a line today, whatever the paper: the window does not promise otherwise.
    expect(s.find('printing-printer-paper-hint').text()).toBe('Kept with the printer: the ERPlora app prints 32 characters a line for now, whatever the paper.');
    await ionValue(s.field('name'), ' Till ', 'ionInput');
    await ionValue(s.field('address'), '192.168.1.50', 'ionInput');
    s.answer(201, { ...TILL });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/printing/printers',
        query: {},
        body: { name: 'Till', kind: 'network', address: '192.168.1.50', port: 9100, paper_width: 80, usage: 'receipt', is_active: true },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Printer added');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('a printer the search found starts filled in, and is added as it came (PRINTING-F02)', async () => {
    const s = await setup(null, { name: 'MTP-II', kind: 'bluetooth', address: 'AA:BB:CC:DD:EE:FF', port: null, paper_width: 58 });
    expect(s.inDoc('printing-printer')?.getAttribute('aria-label')).toBe('New printer');
    expect([prop(s.field('name'), 'value'), prop(s.field('kind'), 'value'), prop(s.field('address'), 'value'), prop(s.field('paper'), 'value')]).toEqual([
      'MTP-II',
      'bluetooth',
      'AA:BB:CC:DD:EE:FF',
      58,
    ]);
    s.answer(201, { ...TILL, name: 'MTP-II' });
    await s.submit();
    expect(s.sent()[0].body).toEqual({ name: 'MTP-II', kind: 'bluetooth', address: 'AA:BB:CC:DD:EE:FF', port: null, paper_width: 58, usage: 'receipt', is_active: true });
  });

  it('a Bluetooth printer asks for its MAC and has no port', async () => {
    const s = await setup();
    await ionValue(s.field('kind'), 'bluetooth');
    expect(s.field('port')).toBeNull();
    expect(prop(s.field('address'), 'label')).toBe('Bluetooth MAC');
    await ionValue(s.field('name'), 'Kitchen', 'ionInput');
    await ionValue(s.field('address'), 'AA:BB:CC:DD:EE:FF', 'ionInput');
    await ionValue(s.field('usage'), 'kitchen');
    await ionValue(s.field('paper'), 58);
    s.answer(201, { ...TILL, kind: 'bluetooth' });
    await s.submit();
    expect(s.sent()[0].body).toEqual({
      name: 'Kitchen',
      kind: 'bluetooth',
      address: 'AA:BB:CC:DD:EE:FF',
      port: null,
      paper_width: 58,
      usage: 'kitchen',
      is_active: true,
    });
  });

  it('the system printer has no address and prints receipts and A4 documents', async () => {
    const s = await setup();
    await ionValue(s.field('kind'), 'system');
    expect(s.field('address')).toBeNull();
    expect(s.field('paper')).toBeNull();
    expect(prop(s.field('usage'), 'disabled')).toBe(true);
    expect(s.find('printing-printer-system-hint').exists()).toBe(true);
    await ionValue(s.field('name'), 'Office', 'ionInput');
    s.answer(201, { ...TILL, kind: 'system' });
    await s.submit();
    expect(s.sent()[0].body).toMatchObject({ kind: 'system', address: '', port: null, usage: 'receipt' });
  });

  it('edits a printer from its values and saves it by its id', async () => {
    const s = await setup(TILL);
    expect(s.inDoc('printing-printer')?.getAttribute('aria-label')).toBe('Edit printer');
    expect(prop(s.field('name'), 'value')).toBe('Till');
    expect(prop(s.field('address'), 'value')).toBe('192.168.1.50');
    await ionValue(s.field('name'), 'Front till', 'ionInput');
    await ionToggle(s.field('active'), false);
    s.answer(200, { ...TILL, name: 'Front till', is_active: false });
    await s.submit();
    expect(s.sent()[0]).toMatchObject({
      path: '/api/printing/printers/update',
      body: { printer_id: 'p1', name: 'Front till', is_active: false, kind: 'network', address: '192.168.1.50', port: 9100 },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Printer saved');
  });

  it('a name is required and the server’s refusal is said at its field', async () => {
    const s = await setup();
    await s.submit();
    expect(prop(s.field('name'), 'errorText')).toBe('Give the printer a name.');
    expect(s.sent()).toEqual([]);
    await ionValue(s.field('name'), 'Till', 'ionInput');
    await ionValue(s.field('address'), 'nope nope', 'ionInput');
    const message = 'Type a valid IP or network name (for example 192.168.1.100).';
    s.answer(422, { error: { code: 'invalid_payload', message, fields: { address: message } } });
    await s.submit();
    expect(prop(s.field('address'), 'errorText')).toBe(message);
  });
});
