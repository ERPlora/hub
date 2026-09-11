// hub#512 — the PIN approval record has a DOOR, and it is a tab of People.
//
// The panel itself is covered by `ApprovalsPanel.test.ts`; what is fixed here is the wiring, which
// is where a reader can be lost even with a working screen:
//
//   - the tab exists and is reachable by deep link (`/employees#approvals`), so «send me the link»
//     is an answer somebody can act on;
//   - it is offered only to an administrator, matching the runtime gate on `hub.administer`;
//   - the panel is mounted when the tab is OPENED, not with the page. The read is paged
//     server-side since hub#884, but the audit is still not the staff list's business: a visit to
//     People must not query it at all;
//   - a session that stops being an administrator is taken off it, exactly like API keys.
//
// Source-level assertions, like the rest of this page's contract (`employees-core.test.ts`): the
// page needs a router and half the runtime to mount, and what is asserted here is a wiring
// decision that lives literally in the template.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./EmployeesPage.vue', import.meta.url), 'utf8');

describe('People › Approvals · the way in', () => {
  it('offers the tab, and only to an administrator', () => {
    // Two lookaheads, both fenced by `[^>]*` so neither can leave THIS tag: what is asserted is
    // the pairing —the Approvals tab is gated by `isAdmin`— in any attribute order. Order-pinning
    // is what made this assertion fall the day the tab got its `data-testid` (hub#1808) with the
    // gate untouched, and pinning `v-if` to the tag name only moved that trap one attribute to the
    // right: it still went red on an intact gate. A test that fails when nothing broke gets
    // loosened by whoever trips on it, and THEN it stops catching the real thing.
    expect(source).toMatch(
      /<ion-segment-button(?=[^>]*\sv-if="isAdmin")(?=[^>]*\svalue="approvals")[^>]*>/,
    );
  });

  it('is deep-linkable: `approvals` is one of the page tabs', () => {
    expect(source).toMatch(/type EmployeeTab =[^\n]*'approvals'/);
    expect(source).toMatch(/const TABS: readonly EmployeeTab\[\] = \[[^\]]*'approvals'/);
  });

  it('mounts the panel only when the tab is open: People never queries the audit', () => {
    // `v-show` would mount it with the page and fire the query on every visit to People.
    expect(source).toMatch(/<ApprovalsPanel\s+v-if="isAdmin && tab === 'approvals'"\s*\/>/);
  });

  it('drops a session that stops being an administrator off the admin-only tabs', () => {
    expect(source).toMatch(/ADMIN_ONLY_TABS/);
    expect(source).toMatch(/const ADMIN_ONLY_TABS: readonly EmployeeTab\[\] = \[[^\]]*'approvals'/);
  });
});
