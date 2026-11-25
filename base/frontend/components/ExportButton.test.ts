// «ExportButton»: a toolbar button that saves a file the server writes with the rows a list shows. Shared by the
// screens that export: it asks `load` for the file, hands it to the Hub's `saveFile`, says while it works, takes no
// second click, and tells a refusal with its reason.
import { toastError } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browserDownloads, outOfTheApp } from '../__tests__/app-download';
import { flush, mountBase } from '../__tests__/mount-base';
import ExportButton from './ExportButton.vue';

afterEach(() => {
  outOfTheApp();
  vi.restoreAllMocks();
});

const PROPS = {
  testid: 'x-export',
  label: 'Download in Excel',
  pendingLabel: 'Preparing…',
  failed: (reason: string) => `Not exported: ${reason}`,
};
const mount = (load: () => Promise<{ filename: string; blob: Blob }>, over: Record<string, unknown> = {}) =>
  mountBase(ExportButton, { props: { ...PROPS, load, ...over } });
const button = (m: Awaited<ReturnType<typeof mount>>) => m.wrapper.get('[data-testid="x-export"]');

describe('ExportButton', () => {
  it('asks for the file once, saves it under its name and says so while it works', async () => {
    let answer: (file: { filename: string; blob: Blob }) => void = () => {};
    const load = vi.fn(() => new Promise<{ filename: string; blob: Blob }>((resolve) => (answer = resolve)));
    const saved = browserDownloads();
    const m = await mount(load);
    expect(button(m).text()).toBe('Download in Excel');
    await button(m).trigger('click');
    await button(m).trigger('click');
    expect(load).toHaveBeenCalledTimes(1);
    expect(button(m).text()).toBe('Preparing…');
    expect(m.wrapper.getComponent(IonButton).props('disabled')).toBe(true);

    answer({ filename: 'invoices.xlsx', blob: new Blob(['x']) });
    await flush();
    await flush();
    expect(saved.map((file) => file.name)).toEqual(['invoices.xlsx']);
    expect(button(m).text()).toBe('Download in Excel');
  });

  it('a refusal is told with its reason and can be tried again', async () => {
    const load = vi.fn(async () => {
      throw new Error('You do not have permission to do that.');
    });
    const m = await mount(load as never);
    await button(m).trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('Not exported: You do not have permission to do that.');
    await button(m).trigger('click');
    await flush();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('does nothing while disabled', async () => {
    const load = vi.fn();
    const m = await mount(load as never, { disabled: true });
    await button(m).trigger('click');
    expect(load).not.toHaveBeenCalled();
  });
});
