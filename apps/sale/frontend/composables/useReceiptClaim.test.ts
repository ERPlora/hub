// `useReceiptClaim`: the second QR of a ticket's paper, the address of this hub's public page where the customer asks
// for the full invoice with the code printed under it. It is drawn once the sale carries its code, drawn again for
// another code, and never leaves a blank square: a QR that cannot be drawn leaves the address to type.
import { mount } from '@vue/test-utils';
import QRCode from 'qrcode';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, type Ref, ref } from 'vue';

import { type ReceiptClaim, RECEIPT_QR_OPTIONS, receiptClaimUrl, useReceiptClaim } from './useReceiptClaim';

const CODE = '20261014-0007-K7Q2M9XD3FPA';
const BAR = { origin: 'https://bar-pepe.erplora.com', hostname: 'bar-pepe.erplora.com' };

function host(code: Ref<string | null | undefined>) {
  let claim!: Ref<ReceiptClaim | null>;
  mount(
    defineComponent({
      setup() {
        claim = useReceiptClaim(code, BAR).claim;
        return () => h('div');
      },
    }),
  );
  return () => claim.value;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('receiptClaimUrl', () => {
  it('opens the business’s public page for the code on the host the till is on', () => {
    expect(receiptClaimUrl(BAR, CODE)).toBe(`https://bar-pepe.erplora.com/p/bar-pepe/invoice/${CODE}`);
    expect(receiptClaimUrl({ origin: 'http://tenant-a.localhost:25000', hostname: 'tenant-a.localhost' }, CODE)).toBe(
      `http://tenant-a.localhost:25000/p/tenant-a/invoice/${CODE}`,
    );
  });
});

describe('useReceiptClaim', () => {
  it('draws the QR of that address once the sale carries its code', async () => {
    const code = ref<string | null | undefined>(undefined);
    const claim = host(code);
    expect(claim()).toBeNull();
    code.value = CODE;
    const url = receiptClaimUrl(BAR, CODE);
    const drawn = await vi.waitFor(() => claim() ?? Promise.reject(new Error('not drawn yet')));
    expect(drawn).toEqual({ code: CODE, url, image: await QRCode.toDataURL(url, { ...RECEIPT_QR_OPTIONS }) });
    expect(drawn.image).toMatch(/^data:image\/png;base64,/);
  });

  it('draws another code again and none for a sale without one', async () => {
    const code = ref<string | null | undefined>(CODE);
    const claim = host(code);
    await vi.waitFor(() => expect(claim()?.code).toBe(CODE));
    code.value = '20261014-0008-AAAABBBBCCCC';
    await vi.waitFor(() => expect(claim()?.url).toBe(receiptClaimUrl(BAR, '20261014-0008-AAAABBBBCCCC')));
    code.value = null;
    await vi.waitFor(() => expect(claim()).toBeNull());
  });

  it('a QR that cannot be drawn leaves the address to type, never a blank square', async () => {
    const failure = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(QRCode, 'toDataURL').mockRejectedValue(new Error('no canvas'));
    const claim = host(ref(CODE));
    await vi.waitFor(() => expect(claim()).toEqual({ code: CODE, url: receiptClaimUrl(BAR, CODE), image: '' }));
    expect(failure).toHaveBeenCalledOnce();
  });
});
