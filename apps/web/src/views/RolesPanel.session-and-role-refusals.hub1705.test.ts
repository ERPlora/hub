// @vitest-environment happy-dom
// hub#1705 — Settings → Roles: a dead session and a missing role read as what they are.
//
// Before: the door answered `401 {"error": "<prose>"}`, the client kept `roles/cashier → 401`, and
// that is what the administrator read. The door now sends `unauthorized` / `forbidden`
// (`crates/server/src/hub_users.rs`); this panel translates both, in the two catalogues the till
// ships (ADR-0055/0199). A missing role must never suggest signing in again: it would not help.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const listHubRoles = vi.fn();
const setRoleActivation = vi.fn();

const { RoleActivationError, HubUsersError } = vi.hoisted(() => ({
  RoleActivationError: class RoleActivationError extends Error {
    readonly code?: string;
    constructor(message: string, code?: string) {
      super(message);
      this.name = 'RoleActivationError';
      this.code = code;
    }
  },
  HubUsersError: class HubUsersError extends Error {},
}));

vi.mock('../lib/hub-users', () => ({
  listHubRoles: (...a: unknown[]) => listHubRoles(...a),
  setRoleActivation: (...a: unknown[]) => setRoleActivation(...a),
  RoleActivationError,
  HubUsersError,
}));
vi.mock('../lib/session', () => ({ isAdmin: { value: true } }));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import RolesPanel from './RolesPanel.vue';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const KITCHEN = {
  name: 'kitchen',
  label: 'Kitchen',
  extends: 'employee',
  source: { kind: 'module', module_id: 'kds' },
  active: false,
  permissions: 3,
  members: 0,
};

type Panel = { vm: { setActive: (role: Record<string, unknown>, next: boolean) => Promise<void> }; html: () => string };

async function refusedWith(locale: 'en' | 'es', code: string): Promise<string> {
  setRoleActivation.mockRejectedValue(new RoleActivationError(`raw runtime prose for ${code}`, code));
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const panel = mount(RolesPanel, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  }) as unknown as Panel;
  await flushPromises();
  await panel.vm.setActive({ ...KITCHEN }, true);
  await flushPromises();
  return panel.html();
}

beforeEach(() => {
  vi.clearAllMocks();
  listHubRoles.mockResolvedValue([{ ...KITCHEN }]);
});

for (const locale of ['en', 'es'] as const) {
  const errors = (locale === 'en' ? enCatalogue : esCatalogue).employeeForm.errors as Record<string, string>;

  describe(`[${locale}] RolesPanel · sesión caducada y rol sin permiso (hub#1705)`, () => {
    it('a session that expired says to sign in again, not `roles/kitchen → 401`', async () => {
      expect(errors.unauthorized, `employeeForm.errors.unauthorized is missing in ${locale}`).toBeTruthy();
      const html = await refusedWith(locale, 'unauthorized');
      expect(html).toContain(errors.unauthorized);
      expect(html).not.toContain('raw runtime prose');
    });

    it('a role without the permission says who can, and never invites to sign in again', async () => {
      expect(errors.forbidden, `employeeForm.errors.forbidden is missing in ${locale}`).toBeTruthy();
      const html = await refusedWith(locale, 'forbidden');
      expect(html).toContain(errors.forbidden);
      expect(html).not.toContain(errors.unauthorized);
      expect(html).not.toContain('raw runtime prose');
    });
  });
}
