// QrSheet: the paper the tables' QR codes are printed on (ONLINE_ORDER-F02): one card per table to cut out and leave on
// it, in the floor plan's order, with «Scan to order», the table's QR, its number and its zone. A table without a code,
// or whose QR could not be drawn, is not on the paper: it never prints a blank square.
import { describe, expect, it } from 'vitest';

import { codeRow, mountOnlineOrder } from '../__tests__/mount-online-order';
import type { TableCodeOut } from '../operations';
import QrSheet from './QrSheet.vue';

const FOUR = codeRow({ number: '4' });
const TEN = codeRow({ number: '10', zone_name: null, table: '10' });
const BARE = codeRow({ number: '12', code: null });

async function sheet(rows: TableCodeOut[], images: Record<string, string>, locale: 'en' | 'es' = 'en') {
  const m = await mountOnlineOrder(QrSheet, { props: { rows, images }, locale });
  const cards = () => m.wrapper.findAll('[data-testid="online-order-qr-sheet-card"]');
  const card = (i: number) => ({
    words: cards()[i].findAll('p').map((p) => p.text()),
    image: cards()[i].find('img').attributes(),
  });
  return { ...m, cards, card };
}

const drawn = (...rows: TableCodeOut[]) => Object.fromEntries(rows.map((row) => [row.url!, `data:image/png;base64,${row.number}`]));

describe('QrSheet', () => {
  it('one card per table, in order, with «Scan to order», its QR, its number and its zone', async () => {
    const s = await sheet([FOUR, TEN], drawn(FOUR, TEN));
    expect(s.find('online-order-qr-sheet').exists()).toBe(true);
    expect(s.cards()).toHaveLength(2);
    expect(s.card(0).words).toEqual(['Scan to order', 'Table 4', 'Terrace']);
    expect(s.card(0).image).toMatchObject({ src: 'data:image/png;base64,4', alt: 'QR code of table 4 (Terrace)' });
    // A table with no zone says only its number.
    expect(s.card(1).words).toEqual(['Scan to order', 'Table 10']);
  });

  it('leaves out a table without a code and one whose QR could not be drawn', async () => {
    const s = await sheet([FOUR, BARE, TEN], drawn(FOUR));
    expect(s.cards().map((c) => c.find('img').attributes('src'))).toEqual(['data:image/png;base64,4']);
  });

  it('is written in the language of the hub', async () => {
    const s = await sheet([FOUR], drawn(FOUR), 'es');
    expect(s.card(0).words).toEqual(['Escanea para pedir', 'Mesa 4', 'Terrace']);
    expect(s.card(0).image.alt).toBe('Código QR de la mesa 4 (Terrace)');
  });
});
