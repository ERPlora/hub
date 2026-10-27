// The screen's own error report (BASE-G95, G13; the old hub's lib/error-report.ts, HUB_SHELL-F149): what nobody
// caught goes to `POST /api/error-report` by itself, without a window nor a confirmation, an identical error once
// every 30 s and at most 50 different ones remembered; a report that cannot leave is lost, never another report.
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createErrorReporter,
  DEDUPE_MS,
  installErrorReport,
  MAX_REMEMBERED,
  REPORT_URL,
  type ReporterDeps,
} from './error-report';

function deps(overrides: Partial<ReporterDeps> = {}) {
  let clock = 1_000;
  const sent: Array<{ url: string; body: Record<string, unknown> }> = [];
  const value: ReporterDeps & { tick(ms: number): void; sent: typeof sent } = {
    send: (url, body) => {
      sent.push({ url, body: JSON.parse(body) as Record<string, unknown> });
      return true;
    },
    now: () => clock,
    address: () => '/sale/cart#pay',
    tick: (ms) => {
      clock += ms;
    },
    sent,
    ...overrides,
  };
  return value;
}

describe('createErrorReporter', () => {
  it('sends what failed, where and in which component to the Hub', () => {
    const d = deps();
    const reporter = createErrorReporter(d);

    expect(reporter.report({ kind: 'vue', message: 'boom', stack: 'at CartPage', component: 'CartPage' })).toBe(true);

    expect(d.sent).toEqual([
      {
        url: REPORT_URL,
        body: { kind: 'vue', message: 'boom', stack: 'at CartPage', component: 'CartPage', url: '/sale/cart#pay' },
      },
    ]);
    expect(REPORT_URL).toBe('/api/error-report');
  });

  it('sends an identical error once every 30 seconds', () => {
    const d = deps();
    const reporter = createErrorReporter(d);
    const error = { kind: 'error' as const, message: 'boom', stack: 's', component: '' };

    reporter.report(error);
    d.tick(DEDUPE_MS - 1);
    expect(reporter.report(error)).toBe(false);
    d.tick(1);
    expect(reporter.report(error)).toBe(true);
    expect(d.sent).toHaveLength(2);
    expect(DEDUPE_MS).toBe(30_000);
  });

  it('tells apart errors with another message, stack or kind', () => {
    const d = deps();
    const reporter = createErrorReporter(d);

    reporter.report({ kind: 'error', message: 'a', stack: 's', component: '' });
    reporter.report({ kind: 'error', message: 'b', stack: 's', component: '' });
    reporter.report({ kind: 'error', message: 'a', stack: 't', component: '' });
    reporter.report({ kind: 'unhandledrejection', message: 'a', stack: 's', component: '' });

    expect(d.sent).toHaveLength(4);
  });

  it('remembers at most 50 different errors: the oldest is forgotten first', () => {
    const d = deps();
    const reporter = createErrorReporter(d);
    const nth = (n: number) => ({ kind: 'error' as const, message: `error ${n}`, stack: '', component: '' });

    for (let n = 0; n <= MAX_REMEMBERED; n += 1) reporter.report(nth(n));

    expect(MAX_REMEMBERED).toBe(50);
    expect(reporter.report(nth(MAX_REMEMBERED))).toBe(false); // still remembered
    expect(reporter.report(nth(0))).toBe(true); // forgotten: the 51st pushed it out
  });

  it('never throws when the report cannot leave, and does not report that', () => {
    const d = deps({
      send: () => {
        throw new Error('beacon refused');
      },
    });
    const reporter = createErrorReporter(d);

    expect(reporter.report({ kind: 'error', message: 'boom', stack: '', component: '' })).toBe(false);
    expect(d.sent).toEqual([]);
  });
});

// BASE-F47: the browser's own «ResizeObserver loop» notice is no error of the screen: the browser says it held some size
// notifications for the next frame, nothing broke and no app can fix it. Every error reporter drops it on the client
// (Sentry's `ignoreErrors`, TrackJS's ignore rules…), by its whole message; anything else that names ResizeObserver,
// or the same words thrown by the app itself, is a real error and still goes.
describe('createErrorReporter: the browser notices that are no error', () => {
  const notice = (message: string) => ({ kind: 'error' as const, message, stack: '', component: '' });

  it('drops the browser\'s «ResizeObserver loop» notice, in its current and its old words', () => {
    const d = deps();
    const reporter = createErrorReporter(d);

    expect(reporter.report(notice('ResizeObserver loop completed with undelivered notifications.'))).toBe(false);
    expect(reporter.report(notice('ResizeObserver loop limit exceeded'))).toBe(false);

    expect(d.sent).toEqual([]);
  });

  it('still sends an error that only mentions ResizeObserver, or carries the notice inside other words', () => {
    const d = deps();
    const reporter = createErrorReporter(d);

    reporter.report(notice('Uncaught ReferenceError: ResizeObserver is not defined'));
    reporter.report(notice('ResizeObserver loop completed with undelivered notifications. Chart failed to draw'));
    reporter.report(notice('resizeobserver loop limit exceeded'));

    expect(d.sent.map((sent) => sent.body.message)).toEqual([
      'Uncaught ReferenceError: ResizeObserver is not defined',
      'ResizeObserver loop completed with undelivered notifications. Chart failed to draw',
      'resizeobserver loop limit exceeded',
    ]);
  });

  it('still sends the same words when the app threw them (an Error with its stack) or a promise rejected with them', () => {
    const d = deps();
    const reporter = createErrorReporter(d);
    const message = 'ResizeObserver loop limit exceeded';

    reporter.report({ kind: 'error', message, stack: 'Error: ResizeObserver loop limit exceeded\n    at Chart', component: '' });
    reporter.report({ kind: 'unhandledrejection', message, stack: '', component: '' });
    reporter.report({ kind: 'vue', message, stack: '', component: 'Agenda' });

    expect(d.sent.map((sent) => sent.body.kind)).toEqual(['error', 'unhandledrejection', 'vue']);
  });
});

describe('installErrorReport', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function setup() {
    const d = deps();
    const reporter = createErrorReporter(d);
    const app = { config: {} as { errorHandler?: (err: unknown, instance: unknown, info: string) => void } };
    const target = new EventTarget();
    const uninstall = installErrorReport(app as never, target as never, reporter);
    return { d, app, target, uninstall };
  }

  it('reports an error nobody caught', () => {
    const { d, target } = setup();
    const error = new TypeError('x is undefined');

    target.dispatchEvent(Object.assign(new Event('error'), { message: 'Uncaught TypeError: x is undefined', error }));

    expect(d.sent.map((s) => [s.body.kind, s.body.message, s.body.stack])).toEqual([
      ['error', 'Uncaught TypeError: x is undefined', error.stack],
    ]);
  });

  it('does not report the browser\'s «ResizeObserver loop» notice (a window error with no Error behind it)', () => {
    const { d, target } = setup();

    target.dispatchEvent(
      Object.assign(new Event('error'), { message: 'ResizeObserver loop completed with undelivered notifications.', error: null }),
    );

    expect(d.sent).toEqual([]);
  });

  it('reports a promise rejected without a handler, an Error or anything else', () => {
    const { d, target } = setup();

    target.dispatchEvent(Object.assign(new Event('unhandledrejection'), { reason: new Error('network down') }));
    target.dispatchEvent(Object.assign(new Event('unhandledrejection'), { reason: 'plain text' }));

    expect(d.sent.map((s) => [s.body.kind, s.body.message])).toEqual([
      ['unhandledrejection', 'network down'],
      ['unhandledrejection', 'plain text'],
    ]);
  });

  it('reports a component that failed to render with its name, and still shows it in the console', () => {
    const { d, app } = setup();
    const console_ = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const error = new Error('render failed');

    app.config.errorHandler!(error, { $options: { __name: 'CartPage' } }, 'render function');

    expect(d.sent.map((s) => [s.body.kind, s.body.message, s.body.component])).toEqual([
      ['vue', 'render failed', 'CartPage'],
    ]);
    expect(console_).toHaveBeenCalledWith(error);
  });

  it('keeps a handler the app already had', () => {
    const d = deps();
    const previous = vi.fn();
    const app = { config: { errorHandler: previous } };
    installErrorReport(app as never, new EventTarget() as never, createErrorReporter(d));

    app.config.errorHandler(new Error('x'), null, 'setup');

    expect(previous).toHaveBeenCalledOnce();
    expect(d.sent).toHaveLength(1);
  });

  it('stops listening when uninstalled', () => {
    const { d, target, uninstall } = setup();
    uninstall();

    target.dispatchEvent(Object.assign(new Event('error'), { message: 'late', error: new Error('late') }));

    expect(d.sent).toEqual([]);
  });
});
