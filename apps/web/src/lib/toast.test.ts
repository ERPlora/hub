// The last link of every tone decided elsewhere (print-on-sale-notice, print-comanda-notice —
// hub#2210, hub#2238): `toast()` must hand the colour and the duration to Ionic as they come, or
// a waiting docket decided amber would still paint in the default grey for the default 2.6 s.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { create } = vi.hoisted(() => ({
  create: vi.fn(async (_opts: Record<string, unknown>) => ({ present: vi.fn(async () => undefined) })),
}));
vi.mock('@ionic/vue', () => ({ toastController: { create } }));

import { toast } from './toast';

describe('toast()', () => {
  beforeEach(() => create.mockClear());

  it('paints with the colour and for the time it is given', async () => {
    await toast('The kitchen order is waiting', 'warning', 6000);
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ color: 'warning', duration: 6000 }));
  });
});
