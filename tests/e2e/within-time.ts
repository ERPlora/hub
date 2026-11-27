// A time limit for a step that waits on the browser: Playwright sets none on `page.evaluate` (nor, in this suite, on a
// navigation), and one that never answered held the whole run until its global limit. Here it fails naming the step.

/** What `step` answers, or an error naming `what` when it does not answer within `ms` milliseconds. */
export function withinTime<T>(what: string, step: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<never>((_, refuse) => {
    timer = setTimeout(() => refuse(new Error(`${what} did not answer within ${Math.round(ms / 1000)} s`)), ms);
  });
  return Promise.race([step, late]).finally(() => clearTimeout(timer));
}
