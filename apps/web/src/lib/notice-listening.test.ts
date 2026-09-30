// hub#2307 — **on Android the notices only arrived while somebody kept the app on screen.**
//
// Every notice comes out of this page: the bell polls, the kitchen and the diary listen to the
// event socket. With the screen off, the app in the background or Android reclaiming it, neither the
// poll nor the socket runs, and the business that turned the notices on believed it would be warned.
// The installed app now keeps listening through a foreground service — what order-taking apps for
// merchants do (Uber Eats Orders, Glovo Partners, Deliveroo Restaurant Hub) — and this file is the
// page's half: WHEN to ask for it, and with which words.
//
// What is pinned: it listens only while somebody is signed in, the hub has something that would
// ever send a notice and the notices are not refused; it stops on sign-out; the notification's
// words come from the catalogue in the app's language; and nothing here ever throws.
import { describe, expect, it, vi } from 'vitest';
import { nextTick, ref } from 'vue';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import {
  KEEP_LISTENING_COMMAND,
  NOTICE_LISTENING_COPY_KEYS,
  createNoticeListening,
  registerNoticeListening,
  resyncNoticeListening,
  stopListeningWhenSignedOut,
  type NoticeListeningDeps,
} from './notice-listening';

function deps(over: Partial<NoticeListeningDeps> = {}) {
  const invoke = vi.fn<NoticeListeningDeps['invoke']>(async () => null);
  return {
    invoke,
    deps: {
      hasSomethingToTell: async () => true,
      permission: async () => 'granted' as const,
      t: (key: string) => `«${key}»`,
      invoke,
      ...over,
    } satisfies NoticeListeningDeps,
  };
}

describe('keeping the installed app listening for notices', () => {
  it('signed in, with something to tell and the notices on: it listens, in the words of the app', async () => {
    const { invoke, deps: d } = deps();
    await createNoticeListening(d).sync(true);
    expect(invoke).toHaveBeenCalledOnce();
    expect(invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, {
      on: true,
      title: '«system.notices.listeningTitle»',
      body: '«system.notices.listeningBody»',
      channel: '«system.notices.listeningChannel»',
    });
  });

  it('a device with no runtime permission to ask (desktop, Android below 13) listens too', async () => {
    const { invoke, deps: d } = deps({ permission: async () => 'unsupported' });
    await createNoticeListening(d).sync(true);
    expect(invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, expect.objectContaining({ on: true }));
  });

  it('with the notices refused there is nothing to listen for: it stops', async () => {
    const { invoke, deps: d } = deps({ permission: async () => 'denied' });
    await createNoticeListening(d).sync(true);
    expect(invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, { on: false });
  });

  it('a hub with nothing that would ever send a notice does not keep the app awake', async () => {
    const { invoke, deps: d } = deps({ hasSomethingToTell: async () => false });
    await createNoticeListening(d).sync(true);
    expect(invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, { on: false });
  });

  it('signed out: it stops without asking anything else', async () => {
    const permission = vi.fn(async () => 'granted' as const);
    const hasSomethingToTell = vi.fn(async () => true);
    const { invoke, deps: d } = deps({ permission, hasSomethingToTell });
    await createNoticeListening(d).sync(false);
    expect(invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, { on: false });
    expect(permission).not.toHaveBeenCalled();
    expect(hasSomethingToTell).not.toHaveBeenCalled();
  });

  it('never throws: an app older than the command, a failed read or a refused start', async () => {
    const refused = deps({ invoke: async () => Promise.reject(new Error('command not found')) });
    await expect(createNoticeListening(refused.deps).sync(true)).resolves.toBeUndefined();
    const unreadable = deps({ hasSomethingToTell: async () => Promise.reject(new Error('boom')) });
    await expect(createNoticeListening(unreadable.deps).sync(true)).resolves.toBeUndefined();
    // Not knowing what is installed is not a reason to keep the device awake.
    expect(unreadable.invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, { on: false });
    const noPermission = deps({ permission: async () => Promise.reject(new Error('boom')) });
    await expect(createNoticeListening(noPermission.deps).sync(true)).resolves.toBeUndefined();
    expect(noPermission.invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, { on: false });
  });

  it('a session closed while the decision was on its way stays closed: nothing starts after it', async () => {
    // Deciding asks the hub what it runs, and that can take as long as the network wants. Somebody
    // signing out in the meantime must not find the device listening for nobody a moment later.
    const waiting: Array<(has: boolean) => void> = [];
    const { invoke, deps: d } = deps({
      hasSomethingToTell: () => new Promise<boolean>((resolve) => waiting.push(resolve)),
    });
    const listening = createNoticeListening(d);
    const starting = listening.sync(true);
    const stopping = listening.sync(false);
    waiting.forEach((answer) => answer(true));
    await Promise.all([starting, stopping]);
    expect(invoke).toHaveBeenCalledOnce();
    expect(invoke).toHaveBeenCalledWith(KEEP_LISTENING_COMMAND, { on: false });
  });

  it('and the other way round: the session that opened last is the one that listens', async () => {
    const waiting: Array<(has: boolean) => void> = [];
    const { invoke, deps: d } = deps({
      hasSomethingToTell: () => new Promise<boolean>((resolve) => waiting.push(resolve)),
    });
    const listening = createNoticeListening(d);
    const stopping = listening.sync(false);
    const starting = listening.sync(true);
    waiting.forEach((answer) => answer(true));
    await Promise.all([stopping, starting]);
    // Stopping decides nothing, so it is carried out at once; the start that follows it stands.
    expect(invoke.mock.calls.map(([, args]) => args.on)).toEqual([false, true]);
  });

  it('stops when the session closes, and only then', async () => {
    const signedIn = ref(true);
    const sync = vi.fn(async () => {});
    const stop = stopListeningWhenSignedOut(() => signedIn.value, { sync });
    await nextTick();
    expect(sync).not.toHaveBeenCalled();
    signedIn.value = false;
    await nextTick();
    expect(sync).toHaveBeenCalledOnce();
    expect(sync).toHaveBeenCalledWith(false);
    signedIn.value = true;
    await nextTick();
    expect(sync).toHaveBeenCalledOnce();
    stop();
  });

  it('the notices turned on again from the System screen start listening without a restart', async () => {
    const sync = vi.fn(async () => {});
    await resyncNoticeListening(); // nothing registered (a browser test, the boot not reached): no-op
    registerNoticeListening({ sync });
    await resyncNoticeListening();
    expect(sync).toHaveBeenCalledWith(true);
  });

  it('every word of the notification resolves in English and in Spanish', () => {
    const at = (catalogue: unknown, key: string) =>
      key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalogue);
    for (const key of NOTICE_LISTENING_COPY_KEYS) {
      expect(typeof at(en, key), `${key} in en`).toBe('string');
      expect(typeof at(es, key), `${key} in es`).toBe('string');
      expect(at(es, key)).not.toBe(at(en, key));
    }
  });
});
