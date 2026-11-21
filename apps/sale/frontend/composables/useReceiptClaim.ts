// The second QR of a ticket's paper: the address of this hub's public page where the customer asks for the full
// invoice, with the code under it (SALE-F29, INVOICE-F04). The receipt printer gets the same address from the server.
import QRCode from 'qrcode';
import { type MaybeRefOrGetter, shallowRef, toValue, watch } from 'vue';

export interface ReceiptClaim {
  code: string;
  url: string;
  /** The QR as a PNG `data:` URL; empty when it could not be drawn, and the paper prints the address instead. */
  image: string;
}

/** The part of `window.location` the address is built from. */
export interface ClaimPlace {
  origin: string;
  hostname: string;
}

/** `M` correction, as the fiscal QR, and drawn big enough to print sharp at the paper's 35 mm. */
export const RECEIPT_QR_OPTIONS: Readonly<QRCode.ToDataURLOptions> = { errorCorrectionLevel: 'M', margin: 0, width: 320 };

/** The business is the host's first label, as the server reads it (`<slug>.<domain>`). */
export function receiptClaimUrl(place: ClaimPlace, code: string): string {
  const slug = place.hostname.split('.')[0];
  return new URL(`/p/${encodeURIComponent(slug)}/invoice/${encodeURIComponent(code)}`, place.origin).href;
}

async function draw(url: string): Promise<string> {
  try {
    return await QRCode.toDataURL(url, { ...RECEIPT_QR_OPTIONS });
  } catch (error) {
    console.error('sale: the QR to ask for the full invoice could not be drawn', error);
    return '';
  }
}

export function useReceiptClaim(code: MaybeRefOrGetter<string | null | undefined>, place: ClaimPlace = window.location) {
  const claim = shallowRef<ReceiptClaim | null>(null);
  watch(
    () => toValue(code),
    async (wanted) => {
      claim.value = null;
      if (!wanted) return;
      const url = receiptClaimUrl(place, wanted);
      const image = await draw(url);
      // Another code asked for while this one was drawn: that one's drawing answers.
      if (toValue(code) === wanted) claim.value = { code: wanted, url, image };
    },
    { immediate: true },
  );
  return { claim };
}
