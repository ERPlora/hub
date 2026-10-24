// The side menu's `visible` (APP-BASE-5; FIX-UI-SIDEBAR-SYSTEM-VISIBLE-TO-EMPLOYEE): an entry shows only to whoever may
// open its screen (Square, Toast: the menu never offers what the person cannot open), and «API» only while the business
// shows its API's documentation — followed live, and asked only with a session (an anonymous stream is refused: 401).
import { createShellSession, type SessionMe, SESSION_KEY } from '@erplora/ui/shell';
import { LIVE_CLIENT_KEY } from '@erplora/ui/sdk';
import { mount } from '@vue/test-utils';
import { defineComponent, h, type MaybeRefOrGetter, ref, toValue } from 'vue';
import { afterEach, describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';
import { createTestClient, flush, resultFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { EMPLOYEE, OWNER } from '../__tests__/mount-base';
import { allowedTo, useApiDocsShown } from './sidebar';

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

describe('allowedTo', () => {
  it('shows the entry to whoever holds the permission its screen asks, and to nobody else', () => {
    expect(probe(allowedTo('base.administer_hub'), OWNER).shown()).toBe(true);
    expect(probe(allowedTo('base.administer_hub'), EMPLOYEE).shown()).toBe(false);
    expect(probe(allowedTo('base.view_home'), EMPLOYEE).shown()).toBe(true);
    expect(probe(allowedTo('base.view_home'), undefined).shown()).toBe(false);
  });

  it('follows the session: the permission given or taken away shows or hides it at once', () => {
    const p = probe(allowedTo('base.administer_hub'), EMPLOYEE);
    expect(p.shown()).toBe(false);
    p.session.value = OWNER;
    expect(p.shown()).toBe(true);
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
