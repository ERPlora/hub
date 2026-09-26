// hub#2152 — `main.ts` redeems the panel's pass through `redeemShellCourier`, which reports a
// failure and never throws, instead of `bootCourier` behind an empty `catch` that made the failure
// invisible. The behaviour is tested in `lib/courier.reports-failure.hub2152.test.ts`; this pins
// that the boot goes through it.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const MAIN = readFileSync(fileURLToPath(new URL('./main.ts', import.meta.url)), 'utf8');

describe('main.ts reports a pass it could not redeem (hub#2152)', () => {
  it('redeems the shell courier through the reporting entry point', () => {
    expect(MAIN).toMatch(/await redeemShellCourier\(shellCourierCode\)/);
  });

  it('no longer calls the raw exchange behind a silent catch', () => {
    expect(MAIN).not.toMatch(/bootCourier\(/);
  });

  it('redeems before mounting', () => {
    const redeemAt = MAIN.indexOf('redeemShellCourier(shellCourierCode)');
    const mountAt = MAIN.indexOf("app.mount('#app')");
    expect(redeemAt).toBeGreaterThan(-1);
    expect(mountAt).toBeGreaterThan(redeemAt);
  });
});
