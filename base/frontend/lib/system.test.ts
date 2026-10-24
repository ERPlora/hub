// System's tabs and the reasons of a failed resend or discard (BASE-G87, G92…G94; the old hub's lib/system-tabs.ts and
// the codes of its dead-letter queue).
import { describe, expect, it } from 'vitest';

import { BACKUPS_TARGET, failureKey, SYSTEM_TABS, TAB_HASH, tabOf, tabsFor } from './system';

describe('System tabs', () => {
  it('keeps the old hub’s five tabs in its order, each in the address', () => {
    expect(SYSTEM_TABS).toEqual(['resources', 'plan', 'updates', 'events', 'logs']);
    expect(TAB_HASH).toEqual({
      resources: '#resources',
      plan: '#plan',
      updates: '#updates',
      events: '#events',
      logs: '#logs',
    });
  });

  it('opens the tab of the address, and Resources for none or an unknown one', () => {
    expect(tabOf('#events', true)).toBe('events');
    expect(tabOf('#plan', false)).toBe('plan');
    expect(tabOf('', true)).toBe('resources');
    expect(tabOf('#nope', true)).toBe('resources');
  });

  it('gives Logs only to who runs the business: anyone else gets Resources for it', () => {
    expect(tabsFor(true)).toEqual(SYSTEM_TABS);
    expect(tabsFor(false)).toEqual(['resources', 'plan', 'updates', 'events']);
    expect(tabOf('#logs', true)).toBe('logs');
    expect(tabOf('#logs', false)).toBe('resources');
  });

  it('sends the retired backups tab to Settings › Data', () => {
    expect(tabOf('#backups', true)).toBe('resources');
    expect(BACKUPS_TARGET).toEqual({ path: '/settings', hash: '#data' });
  });
});

describe('failureKey', () => {
  it('names the reason from the code, never from the text of the Hub', () => {
    expect(failureKey('not_found')).toBe('base.system.failed.reasons.gone');
    expect(failureKey('base.failed_event_app_off')).toBe('base.system.failed.reasons.appOff');
    expect(failureKey('permission_denied')).toBe('base.system.failed.reasons.denied');
    expect(failureKey('network_error')).toBe('base.system.failed.reasons.unknown');
    expect(failureKey(undefined)).toBe('base.system.failed.reasons.unknown');
  });
});
