// `useQrImages(urls)`: the QR of each address, drawn in the browser as a PNG `data:` URL (the way the paper of a ticket
// draws its own), ready for the sheet that is printed. Each address is drawn once, a new one as soon as it appears,
// and one that cannot be drawn is left out and said in the console, never painted as a blank square.
import { mount } from '@vue/test-utils';
import QRCode from 'qrcode';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, type Ref, ref } from 'vue';

import { QR_OPTIONS, useQrImages } from './useQrImages';

const FOUR = 'https://bar-pepe.erplora.com/p/bar-pepe/order/abc';
const SEVEN = 'https://bar-pepe.erplora.com/p/bar-pepe/order/xyz';

function host(urls: Ref<string[]>) {
  let images!: ReturnType<typeof useQrImages>;
  mount(
    defineComponent({
      setup() {
        images = useQrImages(() => urls.value);
        return () => h('div');
      },
    }),
  );
  return images;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useQrImages', () => {
  it('draws the QR of every address, and says when all of them are drawn', async () => {
    const urls = ref([FOUR, SEVEN]);
    const { images, ready } = host(urls);
    await vi.waitFor(() => expect(ready.value).toBe(true));
    expect(images.value).toEqual({
      [FOUR]: await QRCode.toDataURL(FOUR, { ...QR_OPTIONS }),
      [SEVEN]: await QRCode.toDataURL(SEVEN, { ...QR_OPTIONS }),
    });
    expect(images.value[FOUR]).toMatch(/^data:image\/png;base64,/);
  });

  it('M correction, a quiet zone and a size that prints sharp at five centimetres', () => {
    expect(QR_OPTIONS).toEqual({ errorCorrectionLevel: 'M', margin: 2, width: 600 });
  });

  it('draws a new address once, and is not ready until it is drawn', async () => {
    const draw = vi.spyOn(QRCode, 'toDataURL');
    const urls = ref([FOUR]);
    const { images, ready } = host(urls);
    await vi.waitFor(() => expect(ready.value).toBe(true));
    urls.value = [FOUR, SEVEN];
    await nextTick();
    expect(ready.value).toBe(false);
    await vi.waitFor(() => expect(ready.value).toBe(true));
    expect(Object.keys(images.value)).toEqual([FOUR, SEVEN]);
    expect(draw.mock.calls.map((call) => call[0])).toEqual([FOUR, SEVEN]);
  });

  it('with no address it is ready with nothing to draw', () => {
    const { images, ready } = host(ref([]));
    expect([images.value, ready.value]).toEqual([{}, true]);
  });

  it('leaves out an address that cannot be drawn, says it in the console and is still ready', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(QRCode, 'toDataURL').mockImplementation(async (url: string) => {
      if (url === SEVEN) throw new Error('too long');
      return 'data:image/png;base64,FOUR';
    });
    const { images, ready } = host(ref([FOUR, SEVEN]));
    await vi.waitFor(() => expect(ready.value).toBe(true));
    expect(images.value).toEqual({ [FOUR]: 'data:image/png;base64,FOUR' });
    expect(error).toHaveBeenCalledOnce();
  });
});
