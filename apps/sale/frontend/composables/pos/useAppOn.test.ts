// What the till offers of another app: only while that app is on in the business and the person may read it (the
// options of Modifiers in a product's sheet and in a menu's dishes, the menus of Menus…).
import { describe, expect, it } from 'vitest';
import type { ComputedRef } from 'vue';

import { MANAGER, mountComposable } from '../../__tests__/mount-sale';
import { useAppOn } from './useAppOn';

let on: ComputedRef<boolean> | undefined;

async function setup(apps: { label: string; state: 'on' | 'off' }[], permissions: string[]) {
  await mountComposable(
    () => {
      on = useAppOn('modifier', 'modifier.view');
    },
    { session: { ...MANAGER, apps, permissions: [...MANAGER.permissions, ...permissions] } as typeof MANAGER },
  );
  return on!;
}

describe('useAppOn', () => {
  it('is on when the app is on and the person may read it', async () => {
    expect((await setup([{ label: 'modifier', state: 'on' }], ['modifier.view'])).value).toBe(true);
  });

  it('is off when the app is off, or absent, in the business', async () => {
    expect((await setup([{ label: 'modifier', state: 'off' }], ['modifier.view'])).value).toBe(false);
    expect((await setup([], ['modifier.view'])).value).toBe(false);
  });

  it('is off when the person may not read the app', async () => {
    expect((await setup([{ label: 'modifier', state: 'on' }], [])).value).toBe(false);
  });
});
