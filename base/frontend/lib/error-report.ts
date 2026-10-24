// The screen's own error report (BASE-G95, G13; the old hub's lib/error-report.ts, HUB_SHELL-F149): an error nobody
// caught, a promise rejected without a handler or a component that failed to render goes to the Hub by itself, with no
// window, no screenshot and no confirmation. The Hub writes it as one line of its log (`base/error_report.py`), which
// CloudWatch counts. An identical error is sent once every 30 s and at most 50 different ones are remembered; the
// report is best effort: `navigator.sendBeacon` (it survives the page closing and needs no answer), never retried, and
// a report that cannot leave never makes another. Nothing is kept in the browser. The address goes without its query
// string (a sign-in code may travel there).
import type { App } from 'vue';

export const REPORT_URL = '/api/error-report';
export const DEDUPE_MS = 30_000;
export const MAX_REMEMBERED = 50;

export type ErrorKind = 'error' | 'unhandledrejection' | 'vue';

export interface ScreenError {
  kind: ErrorKind;
  message: string;
  stack: string;
  /** The component that failed to render; empty for the others. */
  component: string;
}

export interface ReporterDeps {
  /** Hands `body` (JSON) to `url`; whether it was queued. */
  send(url: string, body: string): boolean;
  now(): number;
  /** The screen's address: path and hash, no query string. */
  address(): string;
}

export interface ErrorReporter {
  /** Sends `error` unless the same was sent within 30 s; whether it was sent. Never throws. */
  report(error: ScreenError): boolean;
}

export function createErrorReporter(deps: ReporterDeps = browserDeps()): ErrorReporter {
  /** When each different error was last sent, oldest first (a Map keeps the order it was set in). */
  const sentAt = new Map<string, number>();
  return {
    report(error) {
      const key = `${error.kind}\u0000${error.message}\u0000${error.stack}`;
      const now = deps.now();
      const last = sentAt.get(key);
      if (last !== undefined && now - last < DEDUPE_MS) return false;
      sentAt.delete(key);
      sentAt.set(key, now);
      while (sentAt.size > MAX_REMEMBERED) sentAt.delete(sentAt.keys().next().value as string);
      try {
        return deps.send(REPORT_URL, JSON.stringify({ ...error, url: deps.address() }));
      } catch {
        // Best effort: the report is lost, and losing it is no new error.
        return false;
      }
    },
  };
}

function browserDeps(): ReporterDeps {
  return {
    send: (url, body) => navigator.sendBeacon(url, new Blob([body], { type: 'application/json' })),
    now: () => Date.now(),
    address: () => `${window.location.pathname}${window.location.hash}`,
  };
}

function describe(reason: unknown): { message: string; stack: string } {
  if (reason instanceof Error) return { message: reason.message || reason.name, stack: reason.stack ?? '' };
  return { message: String(reason), stack: '' };
}

function componentName(instance: unknown): string {
  const options = (instance as { $options?: { name?: string; __name?: string } } | null)?.$options;
  return options?.name ?? options?.__name ?? '';
}

/**
 * Listens to `target` (the window) and takes over `app`'s error handler, keeping one it already had; Vue logs nothing
 * once a handler is set, so the error still goes to the console. Returns what stops listening.
 */
export function installErrorReport(
  app: App,
  target: Window = window,
  reporter: ErrorReporter = createErrorReporter(),
): () => void {
  const onError = (event: Event) => {
    const { message, error } = event as ErrorEvent;
    const described = describe(error ?? message);
    reporter.report({ kind: 'error', message: message || described.message, stack: described.stack, component: '' });
  };
  const onRejection = (event: Event) => {
    reporter.report({ kind: 'unhandledrejection', ...describe((event as PromiseRejectionEvent).reason), component: '' });
  };
  target.addEventListener('error', onError);
  target.addEventListener('unhandledrejection', onRejection);
  const previous = app.config.errorHandler;
  app.config.errorHandler = (error, instance, info) => {
    reporter.report({ kind: 'vue', ...describe(error), component: componentName(instance) });
    if (previous) previous(error, instance, info);
    else console.error(error);
  };
  return () => {
    target.removeEventListener('error', onError);
    target.removeEventListener('unhandledrejection', onRejection);
    app.config.errorHandler = previous;
  };
}
