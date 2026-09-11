// The CSV toast of the shell said `[object Object]`, once per imported row (inventory#90).
//
// `ok-data-table` (OutfitKit) emits the same key with TWO shapes: `csvExport` carries
// `{ rows: <how many> }` and `csvImport` carries `{ headers, rows: [ {…}, {…} ] }` — the parsed
// rows themselves. `bootActionFeedback` read `detail.rows` as a number for both and dropped it
// into a template string, so a shop owner importing 14 products was told
// `CSV importado · [object Object],[object Object],… filas`: fourteen objects and no count.
//
// These tests fire the events the way the table does and assert the message Ionic is asked to
// paint, because that string is the whole defect: anything else (the count, the wording) can move,
// an object stringified into a sentence cannot come back.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

/** Messages handed to Ionic's toast controller, newest last. */
const presented = vi.hoisted(() => [] as string[]);

vi.mock('@ionic/vue', () => ({
  toastController: {
    create: vi.fn(async (opts: { message: string }) => {
      presented.push(opts.message);
      return { present: vi.fn(async () => {}) };
    }),
  },
}));

type Listener = (e: Event) => void;

/** A `window` that only remembers listeners: the suite runs in node, there is no DOM here. */
function stubWindow(): Record<string, Listener[]> {
  const listeners: Record<string, Listener[]> = {};
  vi.stubGlobal('window', {
    addEventListener: (type: string, fn: Listener) => {
      (listeners[type] ??= []).push(fn);
    },
  });
  return listeners;
}

/** Boots the feedback, fires `type` with `detail`, and returns the toast it produced. */
async function toastFor(type: string, detail: unknown): Promise<string> {
  const listeners = stubWindow();
  const { bootActionFeedback } = await import('./toast');
  bootActionFeedback();
  presented.length = 0;
  for (const fn of listeners[type] ?? []) fn({ detail } as unknown as Event);
  await vi.waitFor(() => expect(presented).toHaveLength(1));
  return presented[0];
}

describe('CSV action feedback (inventory#90)', () => {
  beforeEach(() => {
    presented.length = 0;
    // `bootActionFeedback` is idempotent by a module-level flag: each case needs its own copy.
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('announces an import by counting its rows, never by stringifying them', async () => {
    const rows = Array.from({ length: 14 }, (_, i) => ({ name: `Product ${i}`, sku: `SKU-${i}` }));

    const message = await toastFor('csvImport', { headers: ['name', 'sku'], rows });

    expect(message).not.toContain('[object');
    expect(message).toContain('14');
  });

  it('says one row without leaking the object either', async () => {
    const message = await toastFor('csvImport', { headers: ['name'], rows: [{ name: 'Coffee' }] });

    expect(message).not.toContain('[object');
    expect(message).toContain('1');
  });

  it('keeps counting an export, whose payload is already a number', async () => {
    const message = await toastFor('csvExport', { rows: 14 });

    expect(message).not.toContain('[object');
    expect(message).toContain('14');
  });

  it('says nothing it cannot count when the payload carries no rows', async () => {
    const message = await toastFor('csvImport', {});

    expect(message).not.toContain('[object');
    expect(message).not.toContain('undefined');
    expect(message).not.toContain('NaN');
    expect(message.trim()).not.toBe('');
    // The `·` only exists in the sentence that carries a figure. With no figure to say, using it
    // anyway leaves the dangling `read ·  row` the count keys produce when `n` never arrives.
    expect(message).not.toContain('·');
  });
});
