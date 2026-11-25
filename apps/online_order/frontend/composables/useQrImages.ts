// `useQrImages(urls)`: the QR of each address as a PNG `data:` URL, drawn in the browser as the paper of a ticket draws
// its own, so the printed sheet needs nothing from the network. Each address is drawn once; one that cannot be drawn
// is left out and said in the console, so the sheet never prints a blank square.
import QRCode from 'qrcode';
import { computed, type MaybeRefOrGetter, shallowRef, toValue, watch } from 'vue';

/** `M` correction, as the website's QR, a quiet zone of two modules, and drawn big enough to print sharp at 5 cm. */
export const QR_OPTIONS: Readonly<QRCode.ToDataURLOptions> = { errorCorrectionLevel: 'M', margin: 2, width: 600 };

async function draw(url: string): Promise<string | null> {
  try {
    // `qrcode` fills its defaults into the options it is handed: each call takes a copy.
    return await QRCode.toDataURL(url, { ...QR_OPTIONS });
  } catch (error) {
    console.error('online_order: the QR of a table could not be drawn', error);
    return null;
  }
}

export function useQrImages(urls: MaybeRefOrGetter<readonly string[]>) {
  const images = shallowRef<Record<string, string>>({});
  const tried = new Set<string>();
  const pending = shallowRef(0);

  watch(
    () => toValue(urls),
    (now) => {
      for (const url of now) {
        if (tried.has(url)) continue;
        tried.add(url);
        pending.value += 1;
        void draw(url).then((image) => {
          if (image) images.value = { ...images.value, [url]: image };
          pending.value -= 1;
        });
      }
    },
    { immediate: true },
  );

  return { images, ready: computed(() => pending.value === 0) };
}
