// The files a read hands the person in the chat (`HUB_ASSISTANT.saveFile`): saved as a screen's button saves them.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { browserDownloads, outOfTheApp } from '../__tests__/app-download';
import { HUB_ASSISTANT } from './assistant-hub';

afterEach(() => {
  outOfTheApp();
  vi.restoreAllMocks();
});

describe('HUB_ASSISTANT: the files a read hands in the chat', () => {
  const xlsx = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

  it('a CSV is saved as it comes', async () => {
    const saved = browserDownloads();
    await HUB_ASSISTANT.saveFile?.('products.csv', new Blob(['name\nCaña\n'], { type: 'text/csv' }), (key) => key);
    expect(saved.map((file) => file.name)).toEqual(['products.csv']);
    expect(await saved[0].blob.text()).toBe('name\nCaña\n');
  });

  it('an Excel, which comes in base64, is saved as the file it is', async () => {
    const saved = browserDownloads();
    const bytes = Uint8Array.from([0x50, 0x4b, 0x03, 0x04, 0xff, 0x00]);
    const base64 = btoa(String.fromCharCode(...bytes));
    await HUB_ASSISTANT.saveFile?.('invoices.xlsx', new Blob([base64], { type: xlsx }), (key) => key);
    expect(saved.map((file) => [file.name, file.blob.type])).toEqual([['invoices.xlsx', xlsx]]);
    expect(new Uint8Array(await saved[0].blob.arrayBuffer())).toEqual(bytes);
  });
});
