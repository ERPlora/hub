// hub#2307 — the WIRING guard for keeping the installed app listening for notices.
//
// The decision lives in `lib/notice-listening.ts` (with its test); `main.ts` and the System screen
// cannot be mounted in a unit test, so this reads their SOURCE to pin what only lives there: the
// decision runs after the sign-in ask (so a refusal in that very dialog is already known), the
// listening stops with the session, and turning the notices back on from the System screen starts
// it without a restart. Without these three lines the app behaves exactly as before, every unit
// test still green.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');
const SYSTEM_PAGE = readFileSync(fileURLToPath(new URL('./views/SystemPage.vue', import.meta.url)), 'utf8');

/** The source of ONE call: from `opening` (which ends in its `(`) to the parenthesis that closes it. */
function callOf(source: string, opening: string): string {
  const start = source.indexOf(opening);
  expect(start).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = start + opening.length - 1; i < source.length; i++) {
    if (source[i] === '(') depth++;
    else if (source[i] === ')' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`unbalanced call: ${opening}`);
}

describe('the installed app keeps listening while somebody is signed in', () => {
  it('decides after the sign-in ask, so the answer to that dialog counts', () => {
    const call = callOf(MAIN, 'askWhenSomeoneSignsIn(');
    expect(call).toMatch(/warnIfThereIsSomethingToTell\([\s\S]*\)\.then\(\(\) => noticeListening\.sync\(true\)\)/);
  });

  it('is registered for the System screen', () => {
    expect(MAIN).toContain('registerNoticeListening(noticeListening);');
  });

  it('stops with the session', () => {
    expect(callOf(MAIN, 'stopListeningWhenSignedOut(')).toMatch(
      /stopListeningWhenSignedOut\(\s*\(\) => isAuthed\.value,\s*noticeListening\s*\)/,
    );
  });

  it('decides with what the ask decides with: the bell modules and the named sources', () => {
    const call = callOf(MAIN, 'createNoticeListening(');
    expect(call).toContain('hasNoticeSource(');
    expect(call).toContain('loadBellCounterModuleIds()');
    expect(call).toContain('notificationPermissionState()');
    expect(call).toContain('invokeTauri(');
  });

  it('turning the notices on from the System screen starts listening', () => {
    const turnOn = SYSTEM_PAGE.split('async function turnOnNotices(): Promise<void> {')[1]?.split('\n}')[0] ?? '';
    expect(turnOn).toContain('await resyncNoticeListening();');
  });
});
