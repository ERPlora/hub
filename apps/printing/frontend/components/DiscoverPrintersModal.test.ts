// «Search printers» (PRINTING-F02): inside the app it asks the device what printers it reaches and lists
// them, each with «Add» (the draft of «New printer») or «Already added»; it says why it found nothing —
// a browser cannot look, the device denied the permission, the app is not linked to this business, the
// scan failed, or nothing answered — and always offers «Add by its address» (hub#1924).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { click, flush, mountPrinting } from '../__tests__/mount-printing';
import { draftOf, type FoundPrinter } from '../lib/discovery';
import DiscoverPrintersModal from './DiscoverPrintersModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Win = { __TAURI__?: unknown };

const EPSON: FoundPrinter = { id: 'network:192.168.1.50:9100', name: 'EPSON TM-T20III', type: 'network', category: 'unknown', status: 'ready', paper_width: 80 };
const MTP: FoundPrinter = { id: 'bluetooth:aa:bb:cc:dd:ee:ff', name: 'MTP-II', type: 'bluetooth', category: 'unknown', status: 'ready', paper_width: 58 };

function inApp(invoke: (command: string) => Promise<unknown>): void {
  (window as Win).__TAURI__ = { core: { invoke: vi.fn(invoke) } };
}

async function setup(locale: 'en' | 'es' = 'en', known: string[] = []) {
  const m = await mountPrinting(DiscoverPrintersModal, { locale, props: { open: true, known } });
  await flush();
  return m;
}

afterEach(() => delete (window as Win).__TAURI__);

describe('DiscoverPrintersModal', () => {
  it('a browser is told it cannot search, in the person’s language, and offered the address', async () => {
    const s = await setup('es');
    expect(s.inDoc('printing-discover')?.getAttribute('aria-label')).toBe('Buscar impresoras');
    expect(s.find('printing-discover-browser').text()).toBe('Desde el navegador no se puede buscar impresoras: añádela por su dirección.');
    expect(s.find('printing-discover-again').exists()).toBe(false);
    await click(s.inDoc('printing-discover-submit'));
    expect(s.wrapper.emitted('manual')).toHaveLength(1);
  });

  it('inside the app it lists what the device found: «Add» opens the draft, one already added says so', async () => {
    inApp(async () => ({ status: 'scanned', printers: [EPSON, MTP] }));
    const s = await setup('en', ['bluetooth:AA:BB:CC:DD:EE:FF']);
    const rows = [...s.inDoc('printing-discover')!.querySelectorAll('[data-testid="printing-discover-row"]')];
    const read = (row: Element) => [row.querySelector('h3'), row.querySelector('p'), row.querySelector('ion-button, ion-note')].map((el) => el?.textContent?.trim());
    expect(rows.map(read)).toEqual([
      ['EPSON TM-T20III', 'Network · 192.168.1.50:9100', 'Add'],
      ['MTP-II', 'Bluetooth · AA:BB:CC:DD:EE:FF', 'Already added'],
    ]);
    expect(s.find('printing-discover-row-1-add').exists()).toBe(false);
    await click(s.inDoc('printing-discover-row-0-add'));
    expect(s.wrapper.emitted('add')).toEqual([[draftOf(EPSON)]]);
  });

  it('searches while it waits for the device, and again on «Search again»', async () => {
    let answer: (value: unknown) => void = () => {};
    inApp(() => new Promise((resolve) => (answer = resolve)));
    const s = await setup();
    expect(s.find('printing-discover-searching').text()).toBe('Searching for printers…');
    answer({ status: 'scanned', printers: [] });
    await flush();
    expect(s.find('printing-discover-empty').text()).toContain('No printer found.');
    const invoke = ((window as Win).__TAURI__ as { core: { invoke: ReturnType<typeof vi.fn> } }).core.invoke;
    await click(s.inDoc('printing-discover-again'));
    expect(invoke).toHaveBeenCalledTimes(2);
    expect(invoke).toHaveBeenCalledWith('erplora_discover_printers');
  });

  it('«Search again» reads as a button, never as loose text: outlined, with its icon', async () => {
    inApp(async () => ({ status: 'scanned', printers: [] }));
    const s = await setup();
    const again = s.wrapper.findAllComponents(IonButton).find((button) => button.attributes('data-testid') === 'printing-discover-again')!;
    expect(again.props('fill')).toBe('outline');
    expect(again.findComponent(HubIcon).props('name')).toBe('ion:refresh-outline');
  });

  it('says the device denied the permission, never «no printers» (hub#1773)', async () => {
    inApp(async () => ({ status: 'local_network_permission_denied', permission: 'NEARBY_WIFI_DEVICES' }));
    const s = await setup();
    expect(s.find('printing-discover-denied').text()).toBe(
      'The app is not allowed to search the local network: allow it in the device’s settings and search again.',
    );
    expect(s.find('printing-discover-empty').exists()).toBe(false);
    expect(s.find('printing-discover-again').exists()).toBe(true);
  });

  it('an app not linked to this business, and a failed scan, are said in words, never the device’s code', async () => {
    inApp(() => Promise.reject('not_the_linked_hub'));
    const unlinked = await setup();
    expect(unlinked.find('printing-discover-unlinked').text()).toBe(
      'This app is not linked to this business: open the business from the app to search for its printers.',
    );
    expect(unlinked.inDoc('printing-discover')?.textContent).not.toContain('not_the_linked_hub');
    inApp(() => Promise.reject('mDNS socket closed'));
    const failed = await setup();
    expect(failed.find('printing-discover-failed').text()).toBe('Could not search for printers.');
    expect(failed.inDoc('printing-discover')?.textContent).not.toContain('mDNS');
  });
});
