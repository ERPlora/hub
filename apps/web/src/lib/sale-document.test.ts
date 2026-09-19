// @vitest-environment happy-dom
//
// hub#1921 — the ticket printed on payment said «1000000x Acondicionador 300 ml 1190.00» and
// «TOTAL 1190.00» for an 11,90 € sale, and «Pago: Card» in English. The ticket screen's print
// button, on the same sale, printed «1x … 11.90», «TOTAL 11.90», «Pago: Tarjeta».
//
// Two builders of the same paper had drifted apart: the shell composed its own from the raw
// `sales.get` row (minor units, quantity in millionths, payment code), while the button asks the
// sales module's viewer (`erp-sales-document` → `printableDocument()`), which knows the sale's
// units, currency scale and language. The automatic ticket now asks the viewer too, and this file
// pins the door it goes through. The viewer here is a stand-in with the viewer's public surface:
// `saleId` in, `printableDocument()` out, `undefined` until the sale has loaded.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { saleTicketDocument, SALE_DOCUMENT_TIMEOUT, SALE_DOCUMENT_UNAVAILABLE } from './sale-document';

let tagSeq = 0;
/** Every test gets its own tag: the custom element registry cannot forget a definition. */
function nextTag(): string {
  tagSeq += 1;
  return `test-sales-document-${tagSeq}`;
}

/** What the viewer saw while it was composing. */
interface Seen {
  connected?: boolean;
  hidden?: boolean;
}

/** A stand-in for the sales viewer: loads asynchronously once mounted, like the real one. */
function defineViewer(tag: string, opts: { loadMs?: number; neverLoads?: boolean; seen?: Seen } = {}) {
  class Viewer extends HTMLElement {
    saleId?: string;

    private loaded = false;

    connectedCallback() {
      if (opts.neverLoads) return;
      setTimeout(() => {
        this.loaded = true;
      }, opts.loadMs ?? 5);
    }

    printableDocument(): Record<string, unknown> | undefined {
      if (!this.loaded) return undefined;
      if (opts.seen) {
        opts.seen.connected = this.isConnected;
        opts.seen.hidden = this.closest('[hidden]') !== null;
      }
      return {
        business_name: 'Salon Lucia SL',
        receipt_id: `ticket-of-${this.saleId}`,
        items: [{ name: 'Acondicionador 300 ml', quantity: 1, total: 11.9 }],
        total: 11.9,
        payment_method: 'Tarjeta',
      };
    }
  }
  customElements.define(tag, Viewer);
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('the automatic ticket is the paper the sales viewer prints (hub#1921)', () => {
  it('hands back the document the viewer composes for THAT sale', async () => {
    const tag = nextTag();
    defineViewer(tag);

    const doc = await saleTicketDocument('42', { tag, loadViewer: async () => {} });

    expect(doc).toMatchObject({ receipt_id: 'ticket-of-42', total: 11.9, payment_method: 'Tarjeta' });
    expect(doc.items).toEqual([{ name: 'Acondicionador 300 ml', quantity: 1, total: 11.9 }]);
  });

  it('the viewer composes mounted but out of sight, and is gone once the paper is out', async () => {
    const tag = nextTag();
    const seen: Seen = {};
    defineViewer(tag, { seen });

    await saleTicketDocument('42', { tag, loadViewer: async () => {} });

    // Mounted: the real viewer only loads its sale once connected.
    expect(seen.connected).toBe(true);
    // Out of sight: nobody asked to see a second ticket on the till.
    expect(seen.hidden).toBe(true);
    // And gone: a viewer left behind keeps polling the fiscal record for a minute.
    expect(document.querySelector(tag)).toBeNull();
  });

  it('loads the sales bundle on a device that never opened the till', async () => {
    const tag = nextTag();
    const loadViewer = vi.fn(async () => defineViewer(tag));

    const doc = await saleTicketDocument('7', { tag, loadViewer });

    expect(loadViewer).toHaveBeenCalledTimes(1);
    expect(doc.receipt_id).toBe('ticket-of-7');
  });

  it('does not load anything when the viewer is already defined', async () => {
    const tag = nextTag();
    defineViewer(tag);
    const loadViewer = vi.fn(async () => {});

    await saleTicketDocument('42', { tag, loadViewer });

    expect(loadViewer).not.toHaveBeenCalled();
  });

  it('a hub whose sales bundle does not bring the viewer is refused with its code', async () => {
    const tag = nextTag();

    await expect(saleTicketDocument('42', { tag, loadViewer: async () => {} })).rejects.toThrow(
      SALE_DOCUMENT_UNAVAILABLE,
    );
  });

  it('a viewer without the printable document is refused, not printed blank', async () => {
    const tag = nextTag();
    customElements.define(tag, class extends HTMLElement {});

    await expect(saleTicketDocument('42', { tag, loadViewer: async () => {} })).rejects.toThrow(
      SALE_DOCUMENT_UNAVAILABLE,
    );
    expect(document.querySelector(tag)).toBeNull();
  });

  it('a viewer that never gets its sale times out with its code, and is unmounted', async () => {
    const tag = nextTag();
    defineViewer(tag, { neverLoads: true });

    await expect(
      saleTicketDocument('42', { tag, loadViewer: async () => {}, timeoutMs: 60, pollMs: 10 }),
    ).rejects.toThrow(SALE_DOCUMENT_TIMEOUT);
    expect(document.querySelector(tag)).toBeNull();
  });
});
