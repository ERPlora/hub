// Employees (APP-BASE-5; the old hub's EmployeesPage): its tabs in the address hash, how each person gets in and the
// rules a badge follows before it is sent (BASE-G11, G140, G142).
import { describe, expect, it } from 'vitest';

import {
  accessKeys,
  badgeProblem,
  EMPLOYEES_TAB_HASH,
  EMPLOYEES_TABS,
  employeesTabOf,
  employeesTabsFor,
  roleKey,
} from './people';

describe('Employees tabs', () => {
  it('keeps the old hub’s four tabs in its order, each in the address (Personal without a hash)', () => {
    expect(EMPLOYEES_TABS).toEqual(['personal', 'roles', 'apikeys', 'approvals']);
    expect(EMPLOYEES_TAB_HASH).toEqual({ personal: '', roles: '#roles', apikeys: '#apikeys', approvals: '#approvals' });
  });

  it('gives API keys and Approvals only to who runs the business', () => {
    expect(employeesTabsFor(true)).toEqual(['personal', 'roles', 'apikeys', 'approvals']);
    expect(employeesTabsFor(false)).toEqual(['personal', 'roles']);
  });

  it('opens the tab of the address, and Personal for none, an unknown one or one this person does not have', () => {
    expect(employeesTabOf('#roles', false)).toBe('roles');
    expect(employeesTabOf('#apikeys', true)).toBe('apikeys');
    expect(employeesTabOf('#approvals', true)).toBe('approvals');
    expect(employeesTabOf('', true)).toBe('personal');
    expect(employeesTabOf('#nope', true)).toBe('personal');
    // The old hub left a blank page here (HUB_SHELL-F93): now it is Personal.
    expect(employeesTabOf('#approvals', false)).toBe('personal');
    expect(employeesTabOf('#apikeys', false)).toBe('personal');
  });
});

describe('How a person gets in', () => {
  it('names the account always, then the PIN and the badge the hub keeps', () => {
    expect(accessKeys({ account: true, pin: false, badge: false })).toEqual(['base.people.ways.account']);
    expect(accessKeys({ account: true, pin: true, badge: false })).toEqual([
      'base.people.ways.account',
      'base.people.ways.pin',
    ]);
    expect(accessKeys({ account: true, pin: true, badge: true })).toEqual([
      'base.people.ways.account',
      'base.people.ways.pin',
      'base.people.ways.badge',
    ]);
    expect(accessKeys({ account: true, pin: false, badge: true })).toEqual([
      'base.people.ways.account',
      'base.people.ways.badge',
    ]);
  });

  it('names each of erplora.com’s roles by its own key', () => {
    expect(roleKey('hub_owner')).toBe('base.people.roles.hub_owner');
    expect(roleKey('hub_employee')).toBe('base.people.roles.hub_employee');
  });
});

describe('A badge', () => {
  it('takes 4 to 64 letters, digits, «-» and «_», trimmed', () => {
    expect(badgeProblem(' CARD-0003 ')).toBeNull();
    expect(badgeProblem('ab_9')).toBeNull();
    expect(badgeProblem('x'.repeat(64))).toBeNull();
  });

  it('says what is no badge before it is sent', () => {
    expect(badgeProblem('')).toBe('empty');
    expect(badgeProblem('   ')).toBe('empty');
    expect(badgeProblem('abc')).toBe('invalid');
    expect(badgeProblem('x'.repeat(65))).toBe('invalid');
    expect(badgeProblem('CARD 0003')).toBe('invalid');
    expect(badgeProblem('CARD/0003')).toBe('invalid');
  });
});
