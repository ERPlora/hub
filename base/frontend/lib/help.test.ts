import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { LiveClient } from '@erplora/ui/sdk';

import type { AppHelp, HelpFlow, HelpScreen } from '../operations-help';
import {
  assistantQuestion,
  createHelpStore,
  flowMatches,
  organizeFlows,
  resetHelpCache,
  resolvePlatformScreen,
  resolveScreen,
} from './help';

beforeEach(resetHelpCache);

const screens: HelpScreen[] = [
  { id: 'floor', title: 'Floor plan', path: '/table/floor-plan', text: 'Floor text' },
  { id: 'tables', title: 'Tables', path: '/table/tables', text: 'Table text' },
  { id: 'settings', title: 'Settings', path: '/table/settings', text: 'Settings text' },
];

function flow(id: string, title: string, screenIds: string[], steps = 'Open the table'): HelpFlow {
  return { id, title, screens: screenIds, steps, failure: '', videos: [] };
}

const answer: AppHelp = {
  app: 'table',
  name: 'Tables',
  language: 'en',
  video: null,
  purpose: 'Manage the room',
  screens,
  flows: [
    flow('seat', 'Seat a party', ['floor'], 'Choose the number of guests'),
    flow('merge', 'Join two checks', ['floor', 'tables'], 'Open the account'),
    flow('edit', 'Edit the floor plan', ['floor']),
  ],
};

describe('resolveScreen', () => {
  it('chooses the longest screen path that is a segment prefix of a nested route', () => {
    const nested = [...screens, { id: 'detail', title: 'Table detail', path: '/table/tables/detail', text: '' }];
    expect(resolveScreen(nested, '/table/tables/detail/abc/edit')?.id).toBe('detail');
  });

  it('does not confuse a sibling whose path only starts with the same characters', () => {
    expect(resolveScreen(screens, '/table/tables-old')?.id).toBeUndefined();
  });

  it('resolves the settings tab and ignores trailing slashes', () => {
    expect(resolveScreen(screens, '/table/settings/')?.id).toBe('settings');
  });
});

describe('resolvePlatformScreen', () => {
  const platform: HelpScreen[] = [
    { id: 'home', title: 'Home · Summary', path: '/', text: '' },
    { id: 'home_activity', title: 'Home · Activity', path: '/#actividad', text: '' },
    { id: 'employees', title: 'Employees · Staff', path: '/employees', text: '' },
    { id: 'employees_roles', title: 'Employees · Roles', path: '/employees#roles', text: '' },
    { id: 'role', title: 'What it allows', path: '/employees/roles/:role', text: '' },
    { id: 'settings_general', title: 'Settings · General', path: '/settings#general', text: '' },
    { id: 'settings_business', title: 'Settings · Business', path: '/settings#business', text: '' },
  ];
  const at = (pattern: string, hash = '') => resolvePlatformScreen(platform, pattern, hash)?.id;

  it('is the tab the hash names', () => {
    expect(at('/', '#actividad')).toBe('home_activity');
    expect(at('/employees', '#roles')).toBe('employees_roles');
    expect(at('/settings', '#business')).toBe('settings_business');
  });

  it('is the tab a page opens when the hash names none of its tabs', () => {
    expect(at('/')).toBe('home');
    expect(at('/employees')).toBe('employees');
    expect(at('/employees', '#unknown')).toBe('employees');
    expect(at('/settings')).toBe('settings_general');
    expect(at('/settings', '#unknown')).toBe('settings_general');
  });

  it('is a route with parameters by the route itself, never the page above it', () => {
    expect(at('/employees/roles/:role')).toBe('role');
    expect(at('/employees/:person')).toBeUndefined();
  });

  it('is none of them outside the routes the help covers', () => {
    expect(at('/api-docs')).toBeUndefined();
    expect(at('/settings-old')).toBeUndefined();
  });
});

describe('flow filtering and grouping', () => {
  it('matches titles and steps without regard to accents or letter case', () => {
    const accented = flow('seat', 'Sentar un grupo', ['floor'], 'Elige el número de comensales');
    expect(flowMatches(accented, 'sentar')).toBe(true);
    expect(flowMatches(accented, 'COMENSA')).toBe(true);
    expect(flowMatches(accented, 'invoice')).toBe(false);
  });

  it('puts current-screen flows first and repeats a shared flow in each screen group', () => {
    const groups = organizeFlows(answer, 'tables', '');
    expect(groups.map((group) => group.screen.id)).toEqual(['tables', 'floor']);
    expect(groups[0].flows.map((item) => item.id)).toEqual(['merge']);
    expect(groups[1].flows.map((item) => item.id)).toEqual(['seat', 'merge', 'edit']);
  });

  it('removes empty groups and flows whose text does not match', () => {
    const groups = organizeFlows(answer, 'floor', 'guests');
    expect(groups).toHaveLength(1);
    expect(groups[0].flows.map((item) => item.id)).toEqual(['seat']);
  });

  it('adds flows whose screens are not listed as a final untitled group', () => {
    const withOrphan = { ...answer, flows: [...answer.flows, flow('orphan', 'Old screen task', ['removed'])] };
    const groups = organizeFlows(withOrphan, 'floor', '');
    expect(groups.at(-1)?.screen.title).toBe('');
    expect(groups.at(-1)?.flows.map((item) => item.id)).toEqual(['orphan']);
  });
});

describe('createHelpStore', () => {
  function clientWith(call: ReturnType<typeof vi.fn>): LiveClient {
    return { api: { call } } as unknown as LiveClient;
  }

  it('calls the typed operation and reuses an answer for the same app and language', async () => {
    const call = vi.fn().mockResolvedValue(answer);
    const store = createHelpStore(clientWith(call));
    await expect(store.read('table', 'en')).resolves.toBe(answer);
    await expect(store.read('table', 'en')).resolves.toBe(answer);
    expect(call).toHaveBeenCalledOnce();
    expect(call).toHaveBeenCalledWith('base.help.get', { app: 'table' });
  });

  it('serves a reopening from memory when the network is offline', async () => {
    const call = vi.fn().mockResolvedValueOnce(answer).mockRejectedValue(new Error('offline'));
    const store = createHelpStore(clientWith(call));
    await store.read('table', 'en');
    await expect(store.read('table', 'en')).resolves.toEqual(answer);
    expect(call).toHaveBeenCalledOnce();
  });

  it('shares cached answers across store instances', async () => {
    const online = vi.fn().mockResolvedValue(answer);
    await createHelpStore(clientWith(online)).read('table', 'en');
    const offline = vi.fn().mockRejectedValue(new Error('offline'));
    await expect(createHelpStore(clientWith(offline)).read('table', 'en')).resolves.toBe(answer);
    expect(offline).not.toHaveBeenCalled();
  });

  it('keeps languages and apps separate and does not cache a failure', async () => {
    const call = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(answer);
    const store = createHelpStore(clientWith(call));
    await expect(store.read('table', 'en')).rejects.toThrow('offline');
    await store.read('table', 'en');
    await store.read('table', 'es');
    await store.read('sale', 'en');
    expect(call).toHaveBeenCalledTimes(4);
  });
});

describe('assistantQuestion', () => {
  const templates = { flow: 'How do I do this: {title}?', screen: 'How do I use {app} on {screen}?' };

  it('uses the last expanded flow title when there is one', () => {
    expect(assistantQuestion({ flow: 'Join two checks', app: 'Tables', screen: 'Floor plan' }, templates)).toBe(
      'How do I do this: Join two checks?',
    );
  });

  it('falls back to the app and current screen', () => {
    expect(assistantQuestion({ app: 'Tables', screen: 'Floor plan' }, templates)).toBe('How do I use Tables on Floor plan?');
  });
});
