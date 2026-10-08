// hub#2536 — `main.ts` forgets the e-mails an older version stored for the PIN grid, on every boot
// and before mounting. The behaviour is tested in `lib/trusted-users.hub2536.test.ts`; this pins
// that the boot goes through it.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

describe('main.ts forgets the e-mails of the PIN grid (hub#2536)', () => {
  it('calls forgetTrustedUserEmails before mounting', () => {
    // A statement at the start of a line, not a mention: a commented-out call (`// forget…();`)
    // or the name inside a comment must not satisfy this (rv-hub-2683, hub#2696 review).
    const forgetAt = MAIN.search(/^forgetTrustedUserEmails\(\);$/m);
    const mountAt = MAIN.indexOf("app.mount('#app')");
    expect(forgetAt).toBeGreaterThan(-1);
    expect(mountAt).toBeGreaterThan(forgetAt);
  });
});
