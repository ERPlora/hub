// The life of Meta's window (WhatsApp Embedded Signup) from Settings (WHATSAPP_INBOX-F01, F02): `open` runs in the
// click (a window opened after an await is blocked by the browser), then this page follows the window until Meta has
// said which account and number were chosen and erplora.com's return page has brought the one-time code back
// (lib/metaSignup.ts), and hands both, as they came, to `connect` (door 11, `whatsapp_inbox.channel.connect`).
// Closed, cancelled, refused or blocked: `failure` says why and nothing is connected.
import { onScopeDispose, ref, shallowRef } from 'vue';

import { dialogUrl, newState, readReturn, readSession, type Session, type SignupOptions } from '../lib/metaSignup';

/** What door 11 receives: the window's code, how it finished and what it chose. */
export interface SignupWindow {
  code: string;
  event: string;
  waba_id: string;
  phone_number_id: string;
  business_id: string;
}

export type SignupStep = 'idle' | 'waiting' | 'connecting';

/** Why nothing was connected: the browser blocked the window, it was closed or cancelled, Meta refused (with its
 *  words), Meta never said the account, or erplora.com refused the connection (with its words). */
export interface SignupFailure {
  reason: 'blocked' | 'closed' | 'meta' | 'no_account' | 'connect';
  message: string;
}

/** How long a code waits for Meta's word on the account (the code itself lasts 30 s). */
export const SESSION_WAIT_MS = 3000;
/** How long a closed window still may bring its code (erplora.com's page posts it, then closes itself). */
export const CLOSE_GRACE_MS = 1500;
const POLL_MS = 500;
const WINDOW_NAME = 'erplora-whatsapp-signup';
const WINDOW_FEATURES = 'popup,width=640,height=760';

export function useMetaSignup<T>(
  connect: (window: SignupWindow) => Promise<T>,
  env: { hostname: () => string } = { hostname: () => window.location.hostname },
) {
  const step = ref<SignupStep>('idle');
  const failure = ref<SignupFailure | null>(null);
  const result = shallowRef<T | null>(null);

  let options: SignupOptions | null = null;
  let state = '';
  let popup: Window | null = null;
  let session: Session | null = null;
  let code = '';
  let poll: ReturnType<typeof setInterval> | undefined;
  let wait: ReturnType<typeof setTimeout> | undefined;

  function stop(): void {
    window.removeEventListener('message', onMessage);
    clearInterval(poll);
    clearTimeout(wait);
    poll = wait = undefined;
  }

  function fail(reason: SignupFailure['reason'], message = ''): void {
    stop();
    step.value = 'idle';
    failure.value = { reason, message };
  }

  async function finish(): Promise<void> {
    if (!code || !session?.finished) return;
    stop();
    step.value = 'connecting';
    const chosen = session;
    try {
      result.value = await connect({
        code,
        event: chosen.event,
        waba_id: chosen.waba_id,
        phone_number_id: chosen.phone_number_id,
        business_id: chosen.business_id,
      });
      step.value = 'idle';
    } catch (error) {
      fail('connect', error instanceof Error ? error.message : String(error));
    }
  }

  function onMessage(event: MessageEvent): void {
    if (step.value !== 'waiting' || !options) return;
    const said = readSession(event);
    if (said) {
      session = said;
      if (!said.finished) {
        fail(said.error ? 'meta' : 'closed', said.error);
        return;
      }
      void finish();
      return;
    }
    const brought = readReturn(event, options, state);
    if (!brought) return;
    if (brought.error) {
      fail('meta', brought.error);
      return;
    }
    code = brought.code;
    if (session?.finished) {
      void finish();
      return;
    }
    clearTimeout(wait);
    wait = setTimeout(() => fail('no_account'), SESSION_WAIT_MS);
  }

  function open(given: SignupOptions): void {
    stop();
    failure.value = null;
    result.value = null;
    options = given;
    session = null;
    code = '';
    state = newState(env.hostname());
    popup = window.open(dialogUrl(given, state), WINDOW_NAME, WINDOW_FEATURES);
    if (!popup) {
      fail('blocked');
      return;
    }
    step.value = 'waiting';
    window.addEventListener('message', onMessage);
    let closedSince: number | null = null;
    poll = setInterval(() => {
      if (!popup?.closed || code) return;
      closedSince ??= Date.now();
      if (Date.now() - closedSince >= CLOSE_GRACE_MS) fail('closed');
    }, POLL_MS);
  }

  onScopeDispose(stop);

  return { step, failure, result, open };
}
