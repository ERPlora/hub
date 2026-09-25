// hub#2143 — the shell mounts only once the hub has said which business it is.
//
// `main.ts` waits for `GET /api/hub/context` before mounting (hub_id, PIN users, currency, language,
// timezone all come from it). While it waits the served document shows a spinner (hub#2073). When
// the hub does not answer — `bootHubContext` gives up after a bounded wait, or gets an error — the
// boot stops on a notice with ONE action, try again, the way POS apps behave at launch (Square,
// Toast, Lightspeed). Mounting anyway would open a shell with nothing behind it; spinning for ever
// tells the person nothing.
//
// The steps are injected so the sequence is testable without a DOM or a network
// (`boot-unreachable.hub2143.test.ts`); `main.ts` wires the real ones.

export interface BootSteps {
  /** Asks the hub for its context; `null` means it did not answer (timeout or error). */
  loadContext: () => Promise<unknown>;
  /** Paints the «cannot reach your business» notice; `retry` starts another attempt. */
  showUnreachable: (retry: () => void) => void;
  /** Puts the progress indicator back while another attempt runs. */
  showProgress: () => void;
}

/** Resolves once the hub has answered its context — never before, however many retries it takes. */
export function bootUntilReachable(steps: BootSteps): Promise<void> {
  return new Promise<void>((resolve) => {
    const attempt = async (): Promise<void> => {
      const ctx = await steps.loadContext();
      if (ctx) {
        resolve();
        return;
      }
      steps.showUnreachable(() => {
        steps.showProgress();
        void attempt();
      });
    };
    void attempt();
  });
}
