// cash_register#98: the drawer's fields drew a border style the app ignored. Ionic paints `fill="outline"`
// only in its `md` mode (in `ios` it draws nothing), so every outlined input, select and textarea of Cash
// register carries `mode="md"` (working rules §2, «UI completa»).
import { describe, expect, it } from 'vitest';

const sources = import.meta.glob('./**/*.vue', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
/** An opening tag of an Ionic field, its attributes across lines (an arrow `=>` never sits in one). */
const FIELD = /<ion-(input|select|textarea)(?=[\s>])([^>]*)>/g;

describe('outlined fields', () => {
  it('every outlined input, select or textarea is in md mode', () => {
    const wrong: string[] = [];
    let outlined = 0;
    for (const [file, source] of Object.entries(sources)) {
      for (const [, kind, attributes] of source.matchAll(FIELD)) {
        if (!/\sfill="outline"/.test(attributes)) continue;
        outlined += 1;
        if (!/\smode="md"/.test(attributes)) wrong.push(`${file}: <ion-${kind}>`);
      }
    }
    expect(outlined).toBeGreaterThanOrEqual(8);
    expect(wrong).toEqual([]);
  });
});
