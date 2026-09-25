// hub#2143 — `main.ts` mounts the shell only after the hub answered its boot context, through
// `bootUntilReachable` (which shows the «cannot connect» notice and its retry). Before, it mounted
// in a `.finally` — whatever the answer was, and never if there was none. The sequence itself is
// tested in `lib/boot-unreachable.hub2143.test.ts`; this pins that `main.ts` goes through it.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

describe('main.ts waits for the hub before mounting (hub#2143)', () => {
  it('asks for the context through bootUntilReachable, with the boot screen', () => {
    expect(MAIN).toMatch(/bootUntilReachable\(\{\s*loadContext:\s*bootHubContext,/);
    expect(MAIN).toMatch(/showUnreachable:\s*\(retry\)\s*=>\s*bootScreen\?\.showUnreachable\(retry\)/);
    expect(MAIN).toMatch(/showProgress:\s*\(\)\s*=>\s*bootScreen\?\.showProgress\(\)/);
  });

  it('no longer mounts whatever the context answered', () => {
    expect(MAIN).not.toMatch(/bootHubContext\(\)\s*\.finally/);
  });

  it('mounts inside the continuation that runs once the hub answered', () => {
    const start = MAIN.indexOf('bootUntilReachable({');
    const mountAt = MAIN.indexOf("app.mount('#app')");
    expect(start).toBeGreaterThan(-1);
    expect(mountAt).toBeGreaterThan(start);
    // Only one mount in the file: the one behind the wait.
    expect(MAIN.split("app.mount('#app')")).toHaveLength(2);
  });
});
