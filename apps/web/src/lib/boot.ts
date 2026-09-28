// hub#2143 — the shell mounts only once the hub has said which business it is.
//
// `main.ts` waits for `GET /api/hub/context` before mounting (hub_id, PIN users, currency, language,
// timezone all come from it). While it waits the served document shows a spinner (hub#2073). When
// the hub does not answer — `bootHubContext` gives up after a bounded wait, or gets an error — the
// boot stops on a notice with ONE action, try again, the way POS apps behave at launch (Square,
// Toast, Lightspeed). Mounting anyway would open a shell with nothing behind it; spinning for ever
// tells the person nothing.
//
// hub#2255 split the failure in two. `unreachable`: no answer came back (the request failed or
// timed out), so the device's connection is worth checking. `refused`: something answered, but
// not with the context (a 403 from an edge ban, a 5xx) — the device is fine, telling the person to
// check their wifi sends them the wrong way, and since there is nothing for them to do the boot
// asks again by itself every [`BOOT_REFUSED_RETRY_MS`].
//
// The steps are injected so the sequence is testable without a DOM or a network
// (`boot-unreachable.hub2143.test.ts`, `boot-refused.hub2255.test.ts`); `main.ts` wires the real
// ones.

/** Why the boot could not go on. */
export type BootFailure = 'unreachable' | 'refused';

/** What one attempt found: the hub answered its context, or why it did not. */
export type BootOutcome = 'answered' | BootFailure;

/**
 * How long a refusal waits before the boot asks again on its own (hub#2255). An edge ban or a
 * restarting hub lasts minutes, not seconds: often enough to notice it is back, rarely enough not
 * to add load to a hub that is already refusing.
 */
export const BOOT_REFUSED_RETRY_MS = 30_000;

export interface BootSteps {
  /** Asks the hub for its context. */
  loadContext: () => Promise<BootOutcome>;
  /** Paints the notice for `failure`; `retry` starts another attempt. */
  showUnreachable: (retry: () => void, failure: BootFailure) => void;
  /** Puts the progress indicator back while another attempt runs. */
  showProgress: () => void;
}

/** Resolves once the hub has answered its context — never before, however many retries it takes. */
export function bootUntilReachable(steps: BootSteps): Promise<void> {
  return new Promise<void>((resolve) => {
    const attempt = async (): Promise<void> => {
      const outcome = await steps.loadContext();
      if (outcome === 'answered') {
        resolve();
        return;
      }
      // One way out of each notice: the button or the timer, whichever comes first — the other one
      // (and a second press) then does nothing.
      let left = false;
      const retry = (): void => {
        if (left) return;
        left = true;
        steps.showProgress();
        void attempt();
      };
      steps.showUnreachable(retry, outcome);
      if (outcome === 'refused') setTimeout(retry, BOOT_REFUSED_RETRY_MS);
    };
    void attempt();
  });
}
