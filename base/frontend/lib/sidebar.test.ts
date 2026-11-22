import { createShellSession, type SessionMe, SESSION_KEY } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { defineComponent, h, type MaybeRefOrGetter, ref, toValue } from 'vue';
import { afterEach, describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import { createTestClient, flush, resultFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { EMPLOYEE, OWNER } from '../__tests__/mount-base';
import { shellSidebar, SIDEBAR, useApiDocsShown } from './sidebar';

/** Runs `visible` in a component's setup, as the shell does, and reads its value. */
function probe(visible: () => MaybeRefOrGetter<boolean>, me: SessionMe | undefined) {
  const harness = createTestClient({ routes: OPERATION_ROUTES });
  const session = ref<SessionMe | undefined>(me);
  let value: MaybeRefOrGetter<boolean> = false;
  const wrapper = mount(
    defineComponent({
      setup() {
        value = visible();
        return () => h('div');
      },
    }),
    {
      global: {
        provide: {
          [SESSION_KEY as symbol]: createShellSession(session, ref('live')),
          [LIVE_CLIENT_KEY as symbol]: harness.client,
        },
      },
    },
  );
  return { ...harness, session, wrapper, shown: () => toValue(value) };
}

const subscriptions = (client: ReturnType<typeof createTestClient>['client']) => client.stream.subscriptions('base.api_doc.settings');

const mounted: { unmount(): void }[] = [];
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
});

const withPermissions = (...permissions: string[]): SessionMe => ({ ...EMPLOYEE, permissions });

/** The shell's entry `id`, as `shellSidebar` hands it over. */
function shellEntry(id: string) {
  const entry = shellSidebar(SIDEBAR).groups.flat().find((item) => item.id === id);
  if (!entry?.visible) throw new Error(`no entry ${id} with its visible`);
  return { ...entry, visible: entry.visible };
}

describe('SIDEBAR', () => {
  it("declares the platform's entries in two groups, each with the permission its screen asks, and no module", () => {
    expect(SIDEBAR.groups).toEqual([
      [
        { id: 'employees', labelKey: 'sidebar.employees', icon: 'ion:people-outline', to: '/employees', permission: 'base.view_home' },
        { id: 'files', labelKey: 'sidebar.files', icon: 'ion:folder-outline', to: '/files', permission: 'base.view_files' },
      ],
      [
        { id: 'apps', labelKey: 'sidebar.apps', icon: 'ion:storefront-outline', to: '/apps', permission: 'base.view_home' },
        { id: 'system', labelKey: 'sidebar.system', icon: 'ion:hardware-chip-outline', to: '/system', permission: 'base.administer_hub' },
        {
          id: 'api',
          labelKey: 'sidebar.api',
          icon: 'ion:code-slash-outline',
          to: '/api-docs',
          permission: 'base.view_home',
          shownWhile: useApiDocsShown,
        },
        { id: 'settings', labelKey: 'sidebar.settings', icon: 'ion:settings-outline', to: '/settings', permission: 'base.view_home' },
      ],
    ]);
  });
});

describe('shellSidebar', () => {
  it("hands the shell each entry as it is, with a `visible` in place of its permission", () => {
    const groups = shellSidebar(SIDEBAR).groups;
    expect(groups.map((group) => group.map((item) => item.id))).toEqual([
      ['employees', 'files'],
      ['apps', 'system', 'api', 'settings'],
    ]);
    for (const item of groups.flat()) {
      expect(item, item.id).not.toHaveProperty('permission');
      expect(item, item.id).not.toHaveProperty('shownWhile');
      expect(typeof item.visible, item.id).toBe('function');
    }
    expect(groups[0]![1]).toMatchObject({ id: 'files', labelKey: 'sidebar.files', icon: 'ion:folder-outline', to: '/files' });
  });

  it('shows each entry to whoever holds the permission its screen asks, and to nobody else', () => {
    expect(probe(shellEntry('system').visible, OWNER).shown()).toBe(true);
    expect(probe(shellEntry('system').visible, EMPLOYEE).shown()).toBe(false);
    expect(probe(shellEntry('settings').visible, EMPLOYEE).shown()).toBe(true);
    expect(probe(shellEntry('files').visible, withPermissions('base.view_files')).shown()).toBe(true);
    expect(probe(shellEntry('files').visible, withPermissions('base.view_home')).shown()).toBe(false);
    expect(probe(shellEntry('settings').visible, undefined).shown()).toBe(false);
  });

  it('follows the session: the permission given or taken away shows or hides it at once', () => {
    const p = probe(shellEntry('system').visible, EMPLOYEE);
    expect(p.shown()).toBe(false);
    p.session.value = OWNER;
    expect(p.shown()).toBe(true);
    p.session.value = EMPLOYEE;
    expect(p.shown()).toBe(false);
  });

  it('shows «API» only with both: its permission and the documentation shown', async () => {
    const shownWith = async (me: SessionMe, docsEnabled: boolean) => {
      const p = probe(shellEntry('api').visible, me);
      mounted.push(p.wrapper);
      const call = await p.goLive();
      call.push(resultFrame(subscriptions(p.client)[0]!.id, { docs_enabled: docsEnabled, can_change: false }, 1));
      await flush();
      return p.shown();
    };
    expect(await shownWith(OWNER, true)).toBe(true);
    expect(await shownWith(OWNER, false)).toBe(false);
    expect(await shownWith(withPermissions('base.view_files'), true)).toBe(false);
  });
});

describe('useApiDocsShown', () => {
  it('shows «API» while the documentation is shown, and hides it when it is hidden again, live', async () => {
    const p = probe(useApiDocsShown, OWNER);
    mounted.push(p.wrapper);
    expect(p.shown()).toBe(false);
    expect(subscriptions(p.client).map((sub) => sub.params)).toEqual([{}]);
    const call = await p.goLive();
    const id = subscriptions(p.client)[0]!.id;
    call.push(resultFrame(id, { docs_enabled: true, can_change: true }, 1));
    await flush();
    expect(p.shown()).toBe(true);
    call.push(resultFrame(id, { docs_enabled: false, can_change: true }, 2));
    await flush();
    expect(p.shown()).toBe(false);
  });

  it('without a session it asks nothing (the live stream refuses whoever is not signed in) and shows nothing', async () => {
    const p = probe(useApiDocsShown, undefined);
    mounted.push(p.wrapper);
    expect(subscriptions(p.client)).toHaveLength(0);
    expect(p.shown()).toBe(false);
    p.session.value = OWNER;
    await flush();
    expect(subscriptions(p.client)).toHaveLength(1);
    p.session.value = undefined;
    await flush();
    expect(subscriptions(p.client)).toHaveLength(0);
    expect(p.shown()).toBe(false);
  });

  it('leaves the subscription when the menu goes', async () => {
    const p = probe(useApiDocsShown, OWNER);
    p.wrapper.unmount();
    await flush();
    expect(subscriptions(p.client)).toHaveLength(0);
  });
});
