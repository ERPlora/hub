// @vitest-environment node
// The files a scenario's owner attaches, made by fixtures and never kept in the repo: a real spreadsheet, and a
// delivery note as a text PDF or as a phone-like photo, both printed by the browser from the same page.
import { readSheet } from 'read-excel-file/node';
import { describe, expect, it } from 'vitest';

import { attachmentFile, noteHtml, type Renderer, renderWith, xlsxOf } from './assistant-fixtures';
import type { DeliveryNote } from './assistant-scenario';

const note: DeliveryNote = {
  supplier: 'Bebidas del Sur & Cía',
  number: 'ALB-0042',
  date: '2026-11-19',
  lines: [
    { product: 'Agua mineral', quantity: '24', unitCost: '0,42' },
    { product: 'Tónica <premium>', quantity: '12', unitCost: '0,55' },
  ],
};

describe('xlsxOf', () => {
  it('makes a spreadsheet a real reader opens, with its texts, numbers and empty cells', async () => {
    const rows = [
      ['Producto', 'Categoría', 'Precio'],
      ['Gildas', null, 3.5],
      ['Tinto de verano', 'Bebidas', '3,00'],
    ];
    const read = await readSheet(Buffer.from(xlsxOf('Carta', rows)));
    expect(read).toEqual([
      ['Producto', 'Categoría', 'Precio'],
      ['Gildas', null, 3.5],
      ['Tinto de verano', 'Bebidas', '3,00'],
    ]);
  });

  it('escapes what XML would read as markup', async () => {
    const read = await readSheet(Buffer.from(xlsxOf('Hoja', [['Pan & <aceite>']])));
    expect(read).toEqual([['Pan & <aceite>']]);
  });
});

describe('noteHtml', () => {
  it('prints every line with its amount and the total, escaped', () => {
    const html = noteHtml(note, 'paper');
    expect(html).toContain('Bebidas del Sur &amp; Cía');
    expect(html).toContain('Tónica &lt;premium&gt;');
    expect(html).toContain('ALB-0042');
    expect(html).toContain('10,08');
    expect(html).toContain('6,60');
    expect(html).toContain('16,68');
    expect(html).not.toContain('rotate(');
  });

  it('looks like a phone photo of a paper on a counter when it is one', () => {
    expect(noteHtml(note, 'photo')).toContain('rotate(');
  });
});

describe('attachmentFile', () => {
  const renderer: Renderer = { pdf: async (html) => Buffer.from(`pdf:${html.length}`), photo: async (html, type) => Buffer.from(`${type}:${html.length}`) };

  it('gives each attachment its bytes and type, as the composer takes it', async () => {
    const sheet = await attachmentFile({ kind: 'xlsx', name: 'carta.xlsx', sheet: 'Carta', rows: [['a']] }, renderer);
    expect(sheet.mimeType).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    expect(sheet.buffer.subarray(0, 2).toString()).toBe('PK');
    const pdf = await attachmentFile({ kind: 'pdf', name: 'albaran.pdf', note }, renderer);
    expect(pdf).toEqual({ name: 'albaran.pdf', mimeType: 'application/pdf', buffer: Buffer.from(`pdf:${noteHtml(note, 'paper').length}`) });
    const photo = await attachmentFile({ kind: 'photo', name: 'albaran.jpg', note }, renderer);
    expect(photo.mimeType).toBe('image/jpeg');
    expect(photo.buffer.toString()).toBe(`jpeg:${noteHtml(note, 'photo').length}`);
    expect((await attachmentFile({ kind: 'photo', name: 'albaran.png', note }, renderer)).mimeType).toBe('image/png');
  });
});

describe('renderWith', () => {
  it('prints the PDF from the page and takes the photo at a phone\'s size by the e2e\'s capture, in the type asked', async () => {
    const calls: string[] = [];
    const page = {
      setContent: async (html: string) => void calls.push(`content:${html.length}`),
      setViewportSize: async (size: { width: number; height: number }) => void calls.push(`viewport:${size.width}x${size.height}`),
      pdf: async () => (calls.push('pdf'), Buffer.from('%PDF')),
    };
    const shoot = async (options: { type: string; quality?: number }) => (calls.push(`shot:${options.type}:${options.quality ?? ''}`), Buffer.from('img'));
    const render = renderWith(page, shoot);
    expect((await render.pdf('<p>x</p>')).toString()).toBe('%PDF');
    expect((await render.photo('<p>y</p>', 'jpeg')).toString()).toBe('img');
    expect(calls).toEqual(['content:8', 'pdf', 'viewport:900x1200', 'content:8', 'shot:jpeg:82']);
  });
});
