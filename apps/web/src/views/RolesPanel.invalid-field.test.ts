// @vitest-environment happy-dom
// Ajustes → Roles habla en el idioma del hub (hub#1190, hub#1241).
//
// PR #1185 dio a cada rechazo del core su `field`/`reason` estables y, al hacerlo, escribió los
// mensajes en INGLÉS (regla del idioma del código). Correcto en el runtime; el problema es que
// esta pantalla pintaba `error.message` tal cual, así que quien intentaba apagar un rol base en un
// hub en español leía:
//
//   role `admin` is a base role of the hub: base roles are always active and cannot be switched off
//
// Este test monta la pantalla con el catálogo `es` REAL (no un i18n de mentira: la traducción que
// se prueba es justo la que se enviaría) y exige la frase española, no la inglesa.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

const listHubRoles = vi.fn();
const setRoleActivation = vi.fn();

const { RoleActivationError, HubUsersError } = vi.hoisted(() => ({
  RoleActivationError: class RoleActivationError extends Error {
    readonly code?: string;
    readonly field?: string;
    readonly reason?: string;
    // hub#1258: `module`/`query` of a PLATFORM refusal — same rule as `field`/`reason` above.
    readonly module?: string;
    readonly query?: string;
    constructor(
      message: string,
      code?: string,
      field?: string,
      reason?: string,
      module?: string,
      query?: string,
    ) {
      super(message);
      this.name = 'RoleActivationError';
      this.code = code;
      this.field = field;
      this.reason = reason;
      this.module = module;
      this.query = query;
    }
  },
  // `lib/platform-failure.ts` also checks `instanceof HubUsersError` (Personal's own error class):
  // a full module mock has to export SOMETHING under that name, or importing it throws before any
  // test in this file gets to run. RolesPanel itself never touches it.
  HubUsersError: class HubUsersError extends Error {},
}));

vi.mock('../lib/hub-users', () => ({
  listHubRoles: (...a: unknown[]) => listHubRoles(...a),
  setRoleActivation: (...a: unknown[]) => setRoleActivation(...a),
  RoleActivationError,
  HubUsersError,
}));

const { isAdmin } = vi.hoisted(() => ({ isAdmin: { value: true } }));
vi.mock('../lib/session', () => ({ isAdmin }));
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('../lib/toast', () => ({ toast: (...a: unknown[]) => toast(...a) }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import RolesPanel from './RolesPanel.vue';

const CATALOGUE = [
  { name: 'admin', label: 'Administrator', extends: 'admin', source: { kind: 'core' }, active: true, permissions: 12, members: 1 },
  { name: 'kitchen', label: 'Kitchen', extends: 'employee', source: { kind: 'module', module_id: 'kds' }, active: false, permissions: 3, members: 0 },
];

/** La frase EXACTA que hoy llega del runtime y que el usuario español no debe leer. */
const ENGLISH_FROM_THE_RUNTIME =
  'role `admin` is a base role of the hub: base roles are always active and cannot be switched off';

function panelIn(locale: 'es' | 'en') {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { es, en } });
  return mount(RolesPanel, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  }) as unknown as ReturnType<typeof mount> & {
    vm: { setActive: (row: Record<string, unknown>, next: boolean) => Promise<void> };
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  isAdmin.value = true;
  listHubRoles.mockResolvedValue(CATALOGUE.map((r) => ({ ...r })));
});

describe('Ajustes → Roles traduce el rechazo del core (hub#1190)', () => {
  it('🔴 con el hub en español NO enseña la frase inglesa del runtime', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError(ENGLISH_FROM_THE_RUNTIME, 'invalid_field', 'role_key', 'immutable'),
    );
    const panel = panelIn('es');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).not.toContain(ENGLISH_FROM_THE_RUNTIME);
    expect(panel.text()).toContain(es.invalidField.byField.role_key.immutable);
  });

  it('con el hub en inglés enseña la MISMA frase, la del catálogo `en` (fuente, ADR-0055)', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError(ENGLISH_FROM_THE_RUNTIME, 'invalid_field', 'role_key', 'immutable'),
    );
    const panel = panelIn('en');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).toContain(en.invalidField.byField.role_key.immutable);
  });

  it('un rechazo que NO es `invalid_field` conserva su motivo de negocio', async () => {
    // Regla 2 de hub#1102: lo que no sabemos traducir se queda con la frase que vino, que dice
    // más que cualquier genérico que pudiéramos inventar.
    setRoleActivation.mockRejectedValue(
      new RoleActivationError('Solo un administrador puede tocar el catálogo', 'permission_denied'),
    );
    const panel = panelIn('es');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).toContain('Solo un administrador puede tocar el catálogo');
  });

  it('un fallo mudo (red/500) cae al mensaje genérico de la pantalla', async () => {
    setRoleActivation.mockRejectedValue(new Error('network down'));
    const panel = panelIn('es');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', label: 'Kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).not.toContain('network down');
    expect(panel.text()).toContain('Kitchen');
  });
});

describe('Ajustes → Roles traduce un rechazo de PLATAFORMA, no de negocio (hub#1258)', () => {
  // 🔴 El bug: antes de este PR estos códigos caían al `message` del runtime tal cual.
  const ENGLISH_PLUMBING = 'the request could not be completed — the hub recorded the details';

  it.each(['db', 'io', 'wasm', 'native', 'schema', 'manifest'] as const)(
    'el código de plontería "%s" pinta la MISMA frase traducida, nunca la línea inglesa redactada',
    async (code) => {
      setRoleActivation.mockRejectedValue(new RoleActivationError(ENGLISH_PLUMBING, code));
      const panel = panelIn('es');
      await flushPromises();

      await panel.vm.setActive({ name: 'kitchen', label: 'Kitchen', source: { kind: 'module' } }, true);
      await flushPromises();

      expect(panel.text()).not.toContain(ENGLISH_PLUMBING);
      expect(panel.text()).toContain(es.platformFailure.unavailable);
    },
  );

  it('nombra la app que falta para `module_not_installed`', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError('módulo no instalado: `taxes`', 'module_not_installed', undefined, undefined, 'taxes'),
    );
    const panel = panelIn('es');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', label: 'Kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).not.toContain('módulo no instalado');
    expect(panel.text()).toContain(es.platformFailure.moduleMissing.replace('{app}', 'taxes'));
  });

  it('nombra la app desactivada para `module_inactive` — frase DISTINTA de "falta"', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError('módulo desactivado: `taxes`', 'module_inactive', undefined, undefined, 'taxes'),
    );
    const panel = panelIn('es');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', label: 'Kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).toContain(es.platformFailure.moduleInactive.replace('{app}', 'taxes'));
  });

  it('nombra la app que falta como dependencia para `missing_dependency`', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError('falta dependencia: `inventory`', 'missing_dependency', undefined, undefined, 'inventory'),
    );
    const panel = panelIn('es');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', label: 'Kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).toContain(es.platformFailure.moduleMissing.replace('{app}', 'inventory'));
  });

  it('deriva la app de `read_unavailable` desde `query` cuando no viene `module`', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError(
        'a required read (`taxes.rules.list`) could not be resolved',
        'read_unavailable',
        undefined,
        undefined,
        undefined,
        'taxes.rules.list',
      ),
    );
    const panel = panelIn('es');
    await flushPromises();

    await panel.vm.setActive({ name: 'kitchen', label: 'Kitchen', source: { kind: 'module' } }, true);
    await flushPromises();

    expect(panel.text()).not.toContain('rules.list');
    expect(panel.text()).toContain(es.platformFailure.moduleMissing.replace('{app}', 'taxes'));
  });
});
