// A file a read hands the person in the assistant's chat (the CSV of an export) leaves the Hub the one way every download
// does (`saveFile`): a browser's downloads, or, inside the installed app, its Downloads folder and a toast of where.
// Without it the panel offers no file, and inside the Android app a plain link saves nothing.
import { describe, expect, it } from 'vitest';

import { browserDownloads, insideTheAppSaving, keyText, outOfTheAppAfterEach } from '../__tests__/app-download';
import { HUB_ASSISTANT } from './assistant-hub';

outOfTheAppAfterEach();

const CSV = '﻿Nombre;SKU\nCaña;BEB-01\n';

const handed = () => new Blob([CSV], { type: 'text/csv' });

describe('a file the assistant hands, saved by the Hub', () => {
  it('in a browser, it goes to its downloads under its own name, whole', async () => {
    const saved = browserDownloads();

    await HUB_ASSISTANT.saveFile?.('inventario-productos.csv', handed(), keyText);

    expect(saved.map((file) => file.name)).toEqual(['inventario-productos.csv']);
    expect(await saved[0].blob.text()).toBe(CSV);
  });

  it('inside the installed app, the app writes it to Downloads', async () => {
    const invoke = insideTheAppSaving({ path: 'Download/inventario-productos.csv' });

    await expect(HUB_ASSISTANT.saveFile?.('inventario-productos.csv', handed(), keyText)).resolves.toBe(true);

    expect(invoke).toHaveBeenCalledWith('save_download', expect.objectContaining({ name: 'inventario-productos.csv' }));
  });
});
