import { describe, expect, it } from 'vitest';

import { BACKUPS_TARGET, failureKey, SYSTEM_TABS, TAB_HASH, tabOf } from './system';

describe('System tabs', () => {
  it('has its four tabs in order, each in the address', () => {
    expect(SYSTEM_TABS).toEqual(['usage', 'updates', 'events', 'logs']);
    expect(TAB_HASH).toEqual({ usage: '#usage', updates: '#updates', events: '#events', logs: '#logs' });
  });

  it('opens the tab of the address, and «Usage and plan» for none or an unknown one', () => {
    expect(tabOf('#events')).toBe('events');
    expect(tabOf('#logs')).toBe('logs');
    expect(tabOf('#usage')).toBe('usage');
    expect(tabOf('')).toBe('usage');
    expect(tabOf('#nope')).toBe('usage');
  });

  it('opens «Usage and plan» from the addresses of the two tabs it took over', () => {
    expect(tabOf('#resources')).toBe('usage');
    expect(tabOf('#plan')).toBe('usage');
  });

  it('sends the retired backups tab to Settings › Data', () => {
    expect(tabOf('#backups')).toBe('usage');
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
