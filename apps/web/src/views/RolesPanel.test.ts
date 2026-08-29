// @vitest-environment happy-dom
// hub#353 — contrato de la pantalla de **activación de roles** (pestaña Personal › Roles).
//
// El backend (hub#352) ya fijó las reglas; esta pantalla las REFLEJA, no las reinventa:
//   - el catálogo es base ∪ lo que declaran los módulos activos ∪ lo que alguien todavía lleva,
//     y de cada rol se ve DE DÓNDE sale y SI está vivo en este hub;
//   - un rol base no se puede apagar (y no se ofrece como si se pudiera);
//   - un rol huérfano (`in_use`) no se puede encender: no lo declara nadie;
//   - encender/apagar persiste y la pantalla se queda con el catálogo que responde el servidor;
//   - un rechazo del servidor se enseña CON SU MOTIVO — los dos motivos son distintos y piden
//     cosas distintas del administrador, así que aplanarlos a «no se pudo» es perder la guarda;
//   - quien no es administrador no activa. No basta con ocultarle el interruptor: la pantalla
//     tampoco debe llamar al runtime si la acción se dispara igualmente.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const listHubRoles = vi.fn();
const setRoleActivation = vi.fn();

/**
 * Espejo del error real del cliente: lo que distingue un rechazo CON motivo de un fallo mudo.
 * Va por `vi.hoisted` porque el factory de `vi.mock` se iza por encima de este fichero.
 */
const { RoleActivationError, HubUsersError } = vi.hoisted(() => ({
  RoleActivationError: class RoleActivationError extends Error {
    readonly code?: string;
    constructor(message: string, code?: string) {
      super(message);
      this.name = 'RoleActivationError';
      this.code = code;
    }
  },
  // hub#1258: `lib/platform-failure.ts` checks `instanceof HubUsersError` too (Personal's own
  // error class) — a full module mock has to export something under that name, or importing it
  // throws before any test in this file runs. RolesPanel itself never touches it.
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

// Mensajes REALES: el motivo del rechazo y el porqué de un interruptor bloqueado llegan al
// usuario como texto, así que un i18n mudo escondería justo lo que estos tests protegen.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      employees: {
        colRole: 'Role',
        colMembers: 'Members',
        colPermissions: 'Permissions',
        searchRole: 'Search role…',
        emptyRoles: 'No roles available yet.',
        roles: { admin: 'Administrator', employee: 'Employee' },
      },
      roleCatalog: {
        colSource: 'Comes from',
        colActive: 'Active in this hub',
        sourceCore: 'Built in',
        sourceModule: 'Module {module}',
        sourceInUse: 'Module removed',
        alwaysOn: 'Always on',
        notDeclared: 'No installed module declares it',
        adminOnly: 'Only an administrator can switch roles on.',
        activated: '“{role}” is now available.',
        deactivated: '“{role}” is no longer available.',
        toggleError: '“{role}” could not be switched.',
        loadError: 'The role catalogue could not be loaded.',
      },
    },
  },
});

/** admin (base) · kitchen (declarado por un módulo, apagado) · waiter (huérfano, en uso). */
const CATALOGUE = [
  { name: 'admin', label: 'Administrator', extends: 'admin', source: { kind: 'core' }, active: true, permissions: 12, members: 1 },
  { name: 'kitchen', label: 'Kitchen', extends: 'employee', source: { kind: 'module', module_id: 'kds' }, active: false, permissions: 3, members: 0 },
  { name: 'waiter', label: 'waiter', extends: '', source: { kind: 'in_use' }, active: false, permissions: 0, members: 2 },
];

type Panel = VueWrapper<{
  setActive: (role: Record<string, unknown>, next: boolean) => Promise<void>;
  columns: { key: string; header: string; render?: (row: Record<string, unknown>) => Node }[];
  rows: Record<string, unknown>[];
}>;

async function mountPanel(): Promise<Panel> {
  const wrapper = mount(RolesPanel, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  }) as unknown as Panel;
  await flushPromises();
  return wrapper;
}

/** La celda que pinta la columna `key` para `role`, ya renderizada a DOM. */
function cell(panel: Panel, key: string, roleName: string): HTMLElement {
  const column = panel.vm.columns.find((c) => c.key === key);
  if (!column?.render) throw new Error(`la columna \`${key}\` no pinta nada`);
  const row = panel.vm.rows.find((r) => r.name === roleName);
  if (!row) throw new Error(`el rol \`${roleName}\` no está en la tabla`);
  const host = document.createElement('div');
  host.append(column.render(row));
  return host;
}

/** El interruptor de activación de un rol (o `null` si esa fila no ofrece ninguno). */
function toggleOf(panel: Panel, roleName: string): HTMLElement | null {
  return cell(panel, 'active', roleName).querySelector('ion-toggle');
}

beforeEach(() => {
  vi.clearAllMocks();
  isAdmin.value = true;
  listHubRoles.mockResolvedValue(CATALOGUE.map((r) => ({ ...r })));
  setRoleActivation.mockImplementation((key: string, active: boolean) =>
    Promise.resolve(CATALOGUE.map((r) => (r.name === key ? { ...r, active } : { ...r }))),
  );
});

describe('RolesPanel · el catálogo', () => {
  it('lista el catálogo del hub tal y como lo da el runtime', async () => {
    const panel = await mountPanel();

    expect(listHubRoles).toHaveBeenCalledTimes(1);
    expect(panel.vm.rows.map((r) => r.name)).toEqual(['admin', 'kitchen', 'waiter']);
  });

  it('de cada rol se ve DE DÓNDE sale: el core, el módulo que lo declara, o un módulo que ya no está', async () => {
    const panel = await mountPanel();

    expect(cell(panel, 'source', 'admin').textContent).toContain('Built in');
    // No basta con decir «módulo»: el admin necesita saber CUÁL, porque desinstalarlo se lleva el rol.
    expect(cell(panel, 'source', 'kitchen').textContent).toContain('kds');
    expect(cell(panel, 'source', 'waiter').textContent).toContain('Module removed');
  });

  it('de cada rol se ve SI está vivo en este hub', async () => {
    const panel = await mountPanel();

    expect(toggleOf(panel, 'admin')?.getAttribute('checked')).not.toBeNull();
    expect(toggleOf(panel, 'kitchen')?.getAttribute('checked')).toBeNull();
  });
});

describe('RolesPanel · lo que no se puede tocar', () => {
  it('un rol BASE se ve encendido y NO apagable, y dice por qué', async () => {
    const panel = await mountPanel();

    expect(toggleOf(panel, 'admin')?.hasAttribute('disabled')).toBe(true);
    expect(cell(panel, 'active', 'admin').textContent).toContain('Always on');
  });

  it('un rol base no llega al runtime aunque se dispare la acción a mano', async () => {
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'admin', source: { kind: 'core' }, active: true }, false);

    expect(setRoleActivation).not.toHaveBeenCalled();
  });

  it('un rol HUÉRFANO no se puede encender: no lo declara ningún módulo instalado', async () => {
    const panel = await mountPanel();

    expect(toggleOf(panel, 'waiter')?.hasAttribute('disabled')).toBe(true);
    expect(cell(panel, 'active', 'waiter').textContent).toContain('No installed module declares it');

    await panel.vm.setActive({ name: 'waiter', source: { kind: 'in_use' }, active: false }, true);
    expect(setRoleActivation).not.toHaveBeenCalled();
  });
});

describe('RolesPanel · encender y apagar', () => {
  it('encender un rol declarado persiste y la pantalla lo refleja', async () => {
    const panel = await mountPanel();
    expect(panel.vm.rows.find((r) => r.name === 'kitchen')?.active).toBe(false);

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: false }, true);

    expect(setRoleActivation).toHaveBeenCalledWith('kitchen', true);
    // El catálogo que responde el servidor ES el nuevo estado: nada de pintar un optimismo local.
    expect(panel.vm.rows.find((r) => r.name === 'kitchen')?.active).toBe(true);
  });

  it('apagarlo vuelve a viajar y también se refleja', async () => {
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: true }, false);

    expect(setRoleActivation).toHaveBeenCalledWith('kitchen', false);
    expect(panel.vm.rows.find((r) => r.name === 'kitchen')?.active).toBe(false);
  });

  it('el interruptor de un rol declarado sí se puede tocar', async () => {
    const panel = await mountPanel();

    expect(toggleOf(panel, 'kitchen')?.hasAttribute('disabled')).toBe(false);
  });
});

describe('RolesPanel · el motivo del rechazo', () => {
  it('enseña el motivo REAL cuando el runtime rechaza, no un «no se pudo»', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError(
        'role `admin` is a base role of the hub: base roles are always active and cannot be switched off',
        'invalid_field',
      ),
    );
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: false }, true);
    await flushPromises();

    expect(panel.html()).toContain('base role');
  });

  it('los dos motivos del backend llegan distintos: piden cosas distintas del administrador', async () => {
    setRoleActivation.mockRejectedValue(
      new RoleActivationError(
        'role `waiter` is not declared by any installed module: a hub activates the roles of its catalogue, it does not create new ones',
        'invalid_field',
      ),
    );
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: false }, true);
    await flushPromises();

    const shown = panel.html();
    expect(shown).toContain('not declared by any installed module');
    expect(shown).not.toContain('base role');
  });

  it('un fallo SIN motivo cae al mensaje genérico: no se inventa una explicación', async () => {
    setRoleActivation.mockRejectedValue(new RoleActivationError('Failed to fetch'));
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: false }, true);
    await flushPromises();

    expect(panel.html()).toContain('could not be switched');
  });

  it('un rechazo deja el catálogo como estaba: nada de pintar un cambio que no ocurrió', async () => {
    setRoleActivation.mockRejectedValue(new RoleActivationError('nope', 'invalid_field'));
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: false }, true);
    await flushPromises();

    expect(panel.vm.rows.find((r) => r.name === 'kitchen')?.active).toBe(false);
  });
});

describe('RolesPanel · solo un administrador activa', () => {
  it('quien no es admin NO llama al runtime, aunque la acción se dispare igualmente', async () => {
    isAdmin.value = false;
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: false }, true);

    // Ocultar el interruptor no es una guarda: quien llegue a la acción por cualquier vía
    // (deep-link, teclado, un `v-show` que no oculta de verdad) tampoco debe escribir.
    expect(setRoleActivation).not.toHaveBeenCalled();
  });

  it('y se le dice por qué, en vez de dejar el interruptor mudo', async () => {
    isAdmin.value = false;
    const panel = await mountPanel();

    await panel.vm.setActive({ name: 'kitchen', source: { kind: 'module', module_id: 'kds' }, active: false }, true);
    await flushPromises();

    expect(toast).toHaveBeenCalled();
    expect(String(toast.mock.calls[0][0])).toContain('Only an administrator');
  });

  it('a quien no es admin ni se le ofrece el interruptor activo', async () => {
    isAdmin.value = false;
    const panel = await mountPanel();

    expect(toggleOf(panel, 'kitchen')?.hasAttribute('disabled')).toBe(true);
  });
});
