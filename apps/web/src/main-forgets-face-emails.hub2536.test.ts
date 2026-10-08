// hub#2536 — `main.ts` forgets the e-mails an older version stored for the PIN grid, on every boot
// and before mounting. The behaviour is tested in `lib/trusted-users.hub2536.test.ts`; this pins
// that the boot goes through it.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

describe('main.ts forgets the e-mails of the PIN grid (hub#2536)', () => {
  it('calls forgetTrustedUserEmails before mounting', () => {
    const forgetAt = MAIN.indexOf('forgetTrustedUserEmails();');
    const mountAt = MAIN.indexOf("app.mount('#app')");
    expect(forgetAt).toBeGreaterThan(-1);
    expect(mountAt).toBeGreaterThan(forgetAt);
  });
});
