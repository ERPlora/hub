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

    const { document: doc } = await saleTicketDocument('42', { tag, loadViewer: async () => {} });

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

    const { document: doc } = await saleTicketDocument('7', { tag, loadViewer });

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

// hub#1867 — measured on salon-lucia-and18 (v1.1.28, sales 2.16.69): the paper printed on its own
// at checkout said «Ticket: 20260919-0004» and carried no AEAT QR, while the till screen — the same
// viewer — waited behind «Issuing the ticket…» and painted «TICKET-2026-000009» with the QR two
// seconds later. The shell took the FIRST document the viewer answered, before the invoice and its
// VeriFactu record existed. The viewer knows how to wait (`issuing`, sales#308) and says when the
// wait is over (`issued()`); the shell now asks for that before it asks for the paper.
describe('the automatic ticket waits for the fiscal number and QR, like the till screen (hub#1867)', () => {
  interface IssuingSeen extends Seen {
    /** Whether the viewer was already told it was just charged when it was connected. */
    issuingAtConnect?: boolean;
  }

  /** A stand-in for a sales viewer that knows how to wait (sales ≥ `issued()`). */
  function defineIssuingViewer(
    tag: string,
    opts: { issuedAfterMs?: number; complete?: boolean; neverIssues?: boolean; seen?: IssuingSeen } = {},
  ) {
    class Viewer extends HTMLElement {
      saleId?: string;

      issuing = false;

      private loaded = false;

      private fiscal = false;

      private waiters: Array<(complete: boolean) => void> = [];

      connectedCallback() {
        if (opts.seen) opts.seen.issuingAtConnect = this.issuing;
        setTimeout(() => {
          this.loaded = true;
        }, 5);
        if (opts.neverIssues) return;
        setTimeout(() => {
          this.fiscal = opts.complete ?? true;
          for (const resolve of this.waiters) resolve(opts.complete ?? true);
        }, opts.issuedAfterMs ?? 30);
      }

      issued(): Promise<boolean> {
        return new Promise((resolve) => this.waiters.push(resolve));
      }

      printableDocument(): Record<string, unknown> | undefined {
        if (!this.loaded) return undefined;
        return this.fiscal
          ? { receipt_id: 'TICKET-2026-000009', qr_data: 'https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?numserie=TICKET-2026-000009', total: 9.5 }
          : { receipt_id: '20260919-0004', total: 9.5 };
      }
    }
    customElements.define(tag, Viewer);
  }

  it('tells the viewer it was just charged before mounting it, so it waits instead of answering half-built', async () => {
    const tag = nextTag();
    const seen: IssuingSeen = {};
    defineIssuingViewer(tag, { seen });

    await saleTicketDocument('42', { tag, loadViewer: async () => {} });

    expect(seen.issuingAtConnect).toBe(true);
  });

  it('prints only once the viewer says the ticket is issued: the invoice number and the AEAT QR', async () => {
    const tag = nextTag();
    defineIssuingViewer(tag, { issuedAfterMs: 40 });

    const ticket = await saleTicketDocument('42', { tag, loadViewer: async () => {}, pollMs: 5 });

    expect(ticket.document.receipt_id, 'the simplified invoice number, not the sale number').toBe('TICKET-2026-000009');
    expect(ticket.document.qr_data, 'the AEAT QR').toContain('ValidarQR');
    expect(ticket.complete).toBe(true);
  });

  it('when the viewer says its wait ran out incomplete, the paper still goes out and says so', async () => {
    const tag = nextTag();
    defineIssuingViewer(tag, { issuedAfterMs: 20, complete: false });

    const ticket = await saleTicketDocument('42', { tag, loadViewer: async () => {} });

    // A till is never left without paper: it prints what there is, and the caller warns.
    expect(ticket.document.receipt_id).toBe('20260919-0004');
    expect(ticket.complete).toBe(false);
  });

  it('a viewer that never says it is issued does not hold the paper past the deadline', async () => {
    const tag = nextTag();
    defineIssuingViewer(tag, { neverIssues: true });

    const ticket = await saleTicketDocument('42', { tag, loadViewer: async () => {}, timeoutMs: 80, pollMs: 5 });

    expect(ticket.document.receipt_id, 'the best paper there is').toBe('20260919-0004');
    expect(ticket.complete).toBe(false);
    expect(document.querySelector(tag)).toBeNull();
  });

  it('an older sales viewer without issued() prints as before: its first document', async () => {
    const tag = nextTag();
    defineViewer(tag);

    const ticket = await saleTicketDocument('42', { tag, loadViewer: async () => {} });

    expect(ticket.document.receipt_id).toBe('ticket-of-42');
    expect(ticket.complete, 'nothing to say about a wait it cannot report').toBe(true);
  });
});
