// hub#447 — the way OUT to another business, from inside the till.
//
// The installed app remembers ONE hub (`hub.url`, ADR-0159) and until now the only thing that
// forgot it was a Cloud 410: an owner with two businesses and one tablet had no door — the only
// exit was uninstalling the app (which on Android also destroys `device.id`, the stable anchor of
// ADR-0154's single-device session). The mechanism was always whole — `/shell/?choose=1` lists
// the hubs and the capture overwrites the previous one — what was missing is literally the button.
import { describe, it, expect, vi, beforeEach } from 'vitest';

const { invokeTauri, tauriMode, present, create, dialog } = vi.hoisted(() => {
  const dialog: { role?: string } = {};
  const present = vi.fn();
  return {
    invokeTauri: vi.fn(),
    tauriMode: { value: true },
    present,
    dialog,
    create: vi.fn(async (opts: unknown) => ({
      present,
      onDidDismiss: async () => ({ role: dialog.role }),
      __opts: opts,
    })),
  };
});

vi.mock('./device', () => ({
  invokeTauri: (cmd: string, args?: Record<string, unknown>) => invokeTauri(cmd, args),
  isTauri: () => tauriMode.value,
}));
vi.mock('@ionic/vue', () => ({ alertController: { create } }));

import { canChangeHub, requestChangeHub, type ChangeHubLabels } from './change-hub';

const labels: ChangeHubLabels = {
  header: 'Switch business?',
  message: 'This device will sign out and show your list of businesses.',
  cancel: 'Cancel',
  confirm: 'Switch',
};

beforeEach(() => {
  invokeTauri.mockReset().mockResolvedValue(null);
  create.mockClear();
  present.mockClear();
  tauriMode.value = true;
  dialog.role = undefined;
});

describe('canChangeHub', () => {
  it('exists only inside the installed app — in a browser there is no capture to forget', () => {
    expect(canChangeHub()).toBe(true);
    tauriMode.value = false;
    expect(canChangeHub()).toBe(false);
  });
});

describe('requestChangeHub', () => {
  it('confirms FIRST: the local session is lost, so nothing happens until the user says switch', async () => {
    dialog.role = 'destructive';

    const switched = await requestChangeHub(labels);

    expect(switched).toBe(true);
    expect(present).toHaveBeenCalledTimes(1);
    // The order is the contract: the invoke may only happen after the dismissal said "confirm".
    expect(create).toHaveBeenCalledTimes(1);
    expect(invokeTauri).toHaveBeenCalledWith('forget_hub', { choose: true });
  });

  it('sends choose:true — plain forget_hub would bounce a single-hub user straight back in', async () => {
    dialog.role = 'destructive';

    await requestChangeHub(labels);

    expect(invokeTauri.mock.calls[0]).toEqual(['forget_hub', { choose: true }]);
  });

  it('cancelling keeps the hub: no invoke, no navigation', async () => {
    dialog.role = 'cancel';

    const switched = await requestChangeHub(labels);

    expect(switched).toBe(false);
    expect(invokeTauri).not.toHaveBeenCalled();
  });

  it('dismissing by tapping outside is a cancel too', async () => {
    dialog.role = 'backdrop';

    expect(await requestChangeHub(labels)).toBe(false);
    expect(invokeTauri).not.toHaveBeenCalled();
  });

  it('puts the words the caller chose in front of the user', async () => {
    dialog.role = 'cancel';

    await requestChangeHub(labels);

    const opts = create.mock.calls[0][0] as {
      header: string;
      message: string;
      buttons: Array<{ text: string; role: string }>;
    };
    expect(opts.header).toBe(labels.header);
    expect(opts.message).toBe(labels.message);
    expect(opts.buttons.map((b) => b.text)).toEqual([labels.cancel, labels.confirm]);
  });
});
