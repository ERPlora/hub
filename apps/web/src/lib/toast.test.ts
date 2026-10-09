// The last link of every tone decided elsewhere (print-on-sale-notice, print-comanda-notice —
// hub#2210, hub#2238): `toast()` must hand the colour and the duration to Ionic as they come, or
// a waiting docket decided amber would still paint in the default grey for the default 2.6 s.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { create, dismiss } = vi.hoisted(() => ({
  create: vi.fn(async (_opts: Record<string, unknown>) => ({ present: vi.fn(async () => undefined) })),
  dismiss: vi.fn(async (_data?: unknown, _role?: string, _id?: string) => true),
}));
vi.mock('@ionic/vue', () => ({ toastController: { create, dismiss } }));

import { dismissToast, toast } from './toast';

describe('toast()', () => {
  beforeEach(() => create.mockClear());

  it('paints with the colour and for the time it is given', async () => {
    await toast('The kitchen order is waiting', 'warning', 6000);
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ color: 'warning', duration: 6000 }));
  });

  it('names the toast when given an id, so it can be withdrawn later', async () => {
    await toast('The PIN settings could not be read', 'warning', 8000, 'some-notice');
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ id: 'some-notice' }));
  });

  // hub#2494 — a receipt whose printer did not answer is retried from the notice itself.
  it('puts an action button before the close button when given one, and taps run its handler', async () => {
    const handler = vi.fn();
    await toast('The receipt did NOT print', 'danger', 0, undefined, { text: 'Retry', handler });
    const buttons = (create.mock.calls[0]![0] as { buttons: { text: string; role?: string; handler?: () => void }[] })
      .buttons;
    expect(buttons.map((b) => b.text)).toEqual(['Retry', 'OK']);
    expect(buttons[1]!.role).toBe('cancel');
    buttons[0]!.handler!();
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('without an action it keeps only the close button', async () => {
    await toast('Saved', 'success');
    const buttons = (create.mock.calls[0]![0] as { buttons: { text: string }[] }).buttons;
    expect(buttons.map((b) => b.text)).toEqual(['OK']);
  });
});

describe('dismissToast()', () => {
  beforeEach(() => dismiss.mockClear());

  it('withdraws the toast with that id', async () => {
    dismiss.mockResolvedValue(true);
    await expect(dismissToast('some-notice')).resolves.toBe(true);
    expect(dismiss).toHaveBeenCalledWith(undefined, undefined, 'some-notice');
  });

  it('a toast that already went away is not an error: it says so with false', async () => {
    // Ionic rejects when no presented overlay has the id (it timed out or was tapped away).
    dismiss.mockImplementationOnce(async () => {
      throw new Error('overlay does not exist');
    });
    expect(await dismissToast('some-notice')).toBe(false);
  });
});
