// flow: task-e2e-wait — FIX of the Tasks specs' wait (FIX-HUB-TASK-E2E-WAIT-COUNTS-ONLY-OVERLAYS)
// Before a capture, the Tasks specs (task-*.spec.ts) and their helpers wait with the harness's one wait,
// `untilStill(page)` (helpers.ts), which asks the document and every open shadow root for what moves. Their own wait
// counted Ionic's modals and popovers between their «will» and «did» events and nothing else, so a toast entering
// (`task-settled.spec.ts` shows it with «Task started») passed for still and the capture caught it half in. This keeps
// such a wait — counting what moves itself, or sleeping a fixed time — from coming back in the Tasks files, and keeps
// `snap()` on untilStill. The same rule for every spec of the e2e is FIX-HUB-E2E-OWN-ANIMATION-WAIT-UNGUARDED's (hub:base).
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The Tasks specs and their helpers (`task-*.ts`), not Vitest's own tests. */
const taskFiles = (): string[] => readdirSync(E2E_DIR).filter((name) => /^task-.*\.ts$/.test(name) && !name.endsWith('.test.ts'));

const read = (name: string): string => readFileSync(join(E2E_DIR, name), 'utf8');

/**
 * The lines of `source` that count what moves themselves instead of waiting with `untilStill`: asking for animations
 * (`getAnimations(`), or keeping a tally of Ionic's overlays by their present and dismiss events.
 */
function ownMotionCounts(source: string): string[] {
  return source.split('\n').filter((line) => /\bgetAnimations\(|__overlaysMoving|(?:Will|Did)(?:Present|Dismiss)\b/.test(line));
}

/** The lines of `source` that sleep a fixed time (`waitForTimeout(`). */
function sleeps(source: string): string[] {
  return source.split('\n').filter((line) => /\.waitForTimeout\(/.test(line));
}

/** The body of `snap()` in `source`, the capture of every flow of Tasks; empty when there is none. */
function snapBody(source: string): string {
  return /export async function snap\([^)]*\)[^{]*\{([\s\S]*?)\n\}/.exec(source)?.[1] ?? '';
}

/** Each offending line of the Tasks files by `find`, as `<file>: <line>`. */
const offending = (find: (source: string) => string[]): string[] =>
  taskFiles().flatMap((name) => find(read(name)).map((line) => `${name}: ${line.trim()}`));

describe('the Tasks specs wait with untilStill() of helpers.ts', () => {
  it('there are Tasks specs and helpers to look at', () => {
    expect(taskFiles()).toEqual(
      expect.arrayContaining(['task-helpers.ts', 'task-flows.spec.ts', 'task-tasks.spec.ts', 'task-employee.spec.ts', 'task-settled.spec.ts']),
    );
  });

  it('no Tasks spec or helper counts what moves itself: the wait is untilStill(page)', () => {
    expect(offending(ownMotionCounts)).toEqual([]);
  });

  it('no Tasks spec or helper sleeps a fixed time', () => {
    expect(offending(sleeps)).toEqual([]);
  });

  it('snap() waits with untilStill(page) before it captures', () => {
    const body = snapBody(read('task-helpers.ts'));
    expect(body).toContain('await untilStill(page);');
    expect(body.indexOf('await untilStill(page);')).toBeLessThan(body.indexOf('await capture('));
  });

  it('the checks read the waits the Tasks specs had, and untilStill() as none', () => {
    const counted = "  await page.waitForFunction(() => ((window as unknown as { __overlaysMoving?: number }).__overlaysMoving ?? 0) === 0);";
    const events = "    for (const [start, end] of [['WillPresent', 'DidPresent'], ['WillDismiss', 'DidDismiss']]) {";
    const blind = "  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));";
    expect(ownMotionCounts([counted, events, blind].join('\n'))).toEqual([counted, events, blind]);
    expect(ownMotionCounts("  document.addEventListener('ionToastWillPresent', count);")).toHaveLength(1);
    expect(sleeps('    await page.waitForTimeout(400);')).toEqual(['    await page.waitForTimeout(400);']);
    expect(ownMotionCounts('    await untilStill(page);')).toEqual([]);
    expect(sleeps('    await untilStill(page);')).toEqual([]);
    expect(snapBody('export async function snap(page: Page): Promise<void> {\n  await untilStill(page);\n  await capture(page, x);\n}')).toContain(
      'await untilStill(page);',
    );
  });
});
