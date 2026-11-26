// Test helper of `useTill()`: the till mounted in a probe component, the server's answers and the calls it got. Every
// test file that imports it gets the manager's approval dialog in place of Ionic's modal.
import { afterEach, beforeEach, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { line, memoryStorage, order, settings } from '../components/pos/__tests__/fixtures';
import { type Till, useTill } from '../composables/pos/useTill';
import type { SettingsOut } from '../operations';
import { approvalDialog, asksApproval } from './approval-dialog';
import { type MANAGER, mountSale } from './mount-sale';

vi.mock('@ionic/vue', async (importOriginal) => (await import('./approval-dialog')).ionicWithApprovalDialog(importOriginal));

/** Every test starts on a device that keeps nothing and with no approval asked. */
export function freshEachTest(): void {
  beforeEach(() => {
    vi.stubGlobal('localStorage', memoryStorage());
    approvalDialog.reset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });
}

export async function setup(options: { settings?: Partial<SettingsOut>; session?: typeof MANAGER; locale?: 'en' | 'es' } = {}) {
  let till!: Till;
  const opened: string[] = [];
  const joined: string[] = [];
  const Probe = defineComponent({
    setup() {
      till = useTill({
        settings: () => settings(options.settings),
        onOpened: (id) => opened.push(id),
        onJoined: (id) => joined.push(id),
      });
      return () => h('div');
    },
  });
  const m = await mountSale(Probe, { session: options.session, locale: options.locale });
  /** The server answers every write with `body` (an OrderOut by default). */
  const reply = (body: unknown) => m.net.onApi(() => Response.json(body));
  const calls = () => m.sent().map((c) => [c.path.replace('/api/sale/orders', ''), c.body]);
  return { ...m, till: () => till, reply, calls, opened, joined };
}

export const CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: 'p1' })] });

/** The hub asks for a manager's approval of `operation` (403 `requires_elevation`). */
export const asks = (operation: string, label: string) => Response.json(asksApproval(operation, label), { status: 403 });
/** The server's answers in order; after them, the check (the repeat a manager approved). */
export const answers = (...first: Response[]) => {
  let count = 0;
  return () => first[count++] ?? Response.json(CHECK);
};
