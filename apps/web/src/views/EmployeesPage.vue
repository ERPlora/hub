<template>
  <AppPage :title="t('nav.employees')">
    <!-- `.fill` fija el alto al área de `ion-content`; las tablas en modo `fill` resuelven su
         `:host{height:100%}` contra él → cabecera y pager fijos, scroll SOLO en el cuerpo, y se
         adapta a la altura del dispositivo (mismo patrón que ModuleView). -->
    <div class="fill">
      <!-- Staff: tabla con ok-data-table (OutfitKit) — toda la chrome (búsqueda, alta, selector de
           columnas, filas/página, vistas, CSV) vive DENTRO de la tabla, no en la topbar. -->
      <ok-data-table
        v-show="tab === 'staff'"
        ref="staffTable"
        fill
        :columns="employeeColumns"
        :rows="employees"
        :searchKeys="['name', 'email', 'role']"
        :actions="rowActions"
        :primaryAction="newEmployeeAction"
        :search-placeholder="t('employees.searchEmployee')"
        page-size="10"
        views
        csv
        csv-name="empleados"
        column-picker
      ></ok-data-table>

      <!-- Usuarios: placeholder (igual que el original) -->
      <div v-show="tab === 'users'" class="grid place-items-center h-full text-center opacity-60">
        {{ t('employees.usersPlaceholder') }}
      </div>

      <!-- Roles: segunda tabla -->
      <ok-data-table
        v-show="tab === 'roles'"
        ref="rolesTable"
        fill
        :columns="roleColumns"
        :rows="roles"
        :searchKeys="['name', 'scope']"
        :actions="rowActions"
        :primaryAction="newRoleAction"
        :search-placeholder="t('employees.searchRole')"
        page-size="10"
        views
        csv
        csv-name="roles"
        column-picker
      ></ok-data-table>
    </div>
    <!-- Tabs en footer (staff / usuarios / roles) -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment
          :value="tab"
          @ion-change="tab = ($event as CustomEvent<{ value: EmployeeTab }>).detail.value"
        >
          <ion-segment-button value="staff">
            <HubIcon name="people-outline" />
            <ion-label>{{ t('employees.tabStaff') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="users">
            <HubIcon name="person-circle-outline" />
            <ion-label>{{ t('employees.tabUsers') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="roles">
            <HubIcon name="shield-checkmark-outline" />
            <ion-label>{{ t('employees.tabRoles') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { DT_LABELS_ES } from '../lib/data-table-labels';

const { t } = useI18n();

// ok-data-table (OutfitKit) está registrado en main.ts. Tipos locales: OutfitKit no emite .d.ts.
type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  filterable?: boolean;
  filterType?: 'text' | 'select' | 'number' | 'date' | 'range' | 'daterange';
  format?: (row: Row) => string;
  render?: (row: Row) => Node | string;
}
interface DataTableAction { id: string; label: string; icon?: string; color?: string }
interface DataTablePrimaryAction { label: string; icon?: string }

type EmployeeTab = 'staff' | 'users' | 'roles';

const router = useRouter();
const tab = ref<EmployeeTab>('staff');

const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });

// ── Celdas ricas: render devuelve un DOM Node (Lit lo interpola). Es el patrón para consumir
//    ok-data-table desde Vue sin poder producir `html` de Lit. ──────────────────────────────
function nameCell(row: Row): Node {
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:flex;align-items:center;gap:.6rem';
  const avatar = document.createElement('span');
  avatar.textContent = (String(row.name ?? '?')[0] ?? '?').toUpperCase();
  avatar.style.cssText =
    'display:grid;place-items:center;width:2rem;height:2rem;border-radius:999px;font-size:12px;font-weight:700;' +
    'background:color-mix(in srgb,var(--ion-color-primary) 15%,transparent);color:var(--ion-color-primary)';
  const name = document.createElement('span');
  name.textContent = String(row.name ?? '');
  name.style.fontWeight = '500';
  wrap.append(avatar, name);
  return wrap;
}
// Pill de tinte suave (look moderno) con los tokens de color de Ionic. Las CSS vars (--ion-*)
// cruzan el shadow de ok-data-table, así que el color es fiable dentro de la tabla.
function badgeCell(text: string, tone: 'success' | 'medium' | 'primary' | 'danger'): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

// ── Datos demo (mismos que el original React) ───────────────────────────────────────────────
const employees: Row[] = [
  { id: '1', name: 'Demo Admin', email: 'demo@erplora.com', role: 'Administrador', status: 'Activo', createdAt: '2025-01-12' },
  { id: '2', name: 'María López', email: 'maria@erplora.com', role: 'Encargado', status: 'Activo', createdAt: '2025-02-03' },
  { id: '3', name: 'Juan Pérez', email: 'juan@erplora.com', role: 'Cajero', status: 'Activo', createdAt: '2025-02-20' },
  { id: '4', name: 'Ana Ruiz', email: 'ana@erplora.com', role: 'Almacén', status: 'Inactivo', createdAt: '2025-03-15' },
  { id: '5', name: 'Luis Gómez', email: 'luis@erplora.com', role: 'Camarero', status: 'Activo', createdAt: '2025-04-09' },
  { id: '6', name: 'Sara Díaz', email: null, role: 'Cocina', status: 'Activo', createdAt: '2025-05-01' },
];

// `computed` para que las cabeceras se recalculen al cambiar de idioma en caliente.
const employeeColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colEmployee'), render: nameCell },
  { key: 'email', header: t('employees.colEmail'), format: (r) => String(r.email ?? '—') },
  { key: 'role', header: t('employees.colRole'), filterable: true, filterType: 'select' },
  {
    key: 'status', header: t('employees.colStatus'), filterable: true, filterType: 'select',
    render: (r) => badgeCell(String(r.status), r.status === 'Activo' ? 'success' : 'medium')
  },
  { key: 'createdAt', header: t('employees.colCreatedAt'), filterable: true, filterType: 'daterange', format: (r) => fmtDate(String(r.createdAt)) },
]);

// ── Roles (dataset mayor para ver paginación) ───────────────────────────────────────────────
interface RoleBase { id: string; name: string; scope: 'Sistema' | 'Personalizado'; members: number; permissions: number; createdAt: string }
const BASE_ROLES: RoleBase[] = [
  { id: 'admin', name: 'Administrador', scope: 'Sistema', members: 1, permissions: 48, createdAt: '2025-01-12' },
  { id: 'manager', name: 'Encargado', scope: 'Sistema', members: 2, permissions: 31, createdAt: '2025-01-12' },
  { id: 'cashier', name: 'Cajero', scope: 'Personalizado', members: 4, permissions: 9, createdAt: '2025-03-04' },
  { id: 'stock', name: 'Almacén', scope: 'Personalizado', members: 1, permissions: 12, createdAt: '2025-04-21' },
  { id: 'waiter', name: 'Camarero', scope: 'Personalizado', members: 6, permissions: 7, createdAt: '2025-05-18' },
  { id: 'kitchen', name: 'Cocina', scope: 'Personalizado', members: 3, permissions: 5, createdAt: '2025-02-09' },
  { id: 'host', name: 'Recepción', scope: 'Personalizado', members: 2, permissions: 6, createdAt: '2025-03-22' },
  { id: 'accountant', name: 'Contabilidad', scope: 'Sistema', members: 1, permissions: 22, createdAt: '2025-01-30' },
  { id: 'buyer', name: 'Compras', scope: 'Personalizado', members: 2, permissions: 14, createdAt: '2025-04-02' },
  { id: 'marketing', name: 'Marketing', scope: 'Personalizado', members: 1, permissions: 8, createdAt: '2025-05-05' },
  { id: 'support', name: 'Soporte', scope: 'Personalizado', members: 3, permissions: 11, createdAt: '2025-02-18' },
  { id: 'auditor', name: 'Auditor', scope: 'Sistema', members: 1, permissions: 19, createdAt: '2025-01-22' },
];
const roles: Row[] = Array.from({ length: 58 }, (_, i) => {
  const base = BASE_ROLES[i % BASE_ROLES.length];
  return i < BASE_ROLES.length
    ? { ...base }
    : { ...base, id: `${base.id}-${i}`, name: `${base.name} ${Math.floor(i / BASE_ROLES.length) + 1}` };
});

const roleColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colRole') },
  {
    key: 'scope', header: t('employees.colScope'), filterable: true, filterType: 'select',
    render: (r) => badgeCell(String(r.scope), r.scope === 'Sistema' ? 'primary' : 'medium')
  },
  { key: 'members', header: t('employees.colMembers'), align: 'center' },
  { key: 'permissions', header: t('employees.colPermissions'), align: 'center' },
  { key: 'createdAt', header: t('employees.colCreated'), filterable: true, filterType: 'daterange', format: (r) => fmtDate(String(r.createdAt)) },
]);

// Acciones de fila (editar / borrar) → evento `rowAction`. `computed` para que las etiquetas
// se recalculen al cambiar de idioma en caliente.
const rowActions = computed<DataTableAction[]>(() => [
  { id: 'edit', label: t('employees.actionEdit'), icon: 'pencil' },
  { id: 'delete', label: t('employees.actionDelete'), icon: 'trash', color: 'danger' },
]);

// Acción primaria (botón "Nuevo") dentro de la propia tabla → evento `primaryAction`.
const newEmployeeAction = computed<DataTablePrimaryAction>(() => ({ label: t('employees.newEmployee'), icon: 'add' }));
const newRoleAction = computed<DataTablePrimaryAction>(() => ({ label: t('employees.newRole'), icon: 'add' }));

function onNew(): void {
  void router.push('/employees/new');
}
function onNewRole(): void {
  // Sin pantalla de alta de rol todavía (pendiente humano); se registra el intento.
  console.info('roles.new');
}

// `rowAction` es camelCase; Vue baja a minúsculas los nombres de evento en plantilla, así que se
// engancha con ref + addEventListener (patrón para eventos camelCase de Web Components desde Vue).
const staffTable = ref<HTMLElement | null>(null);
const rolesTable = ref<HTMLElement | null>(null);

function handleRowAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'edit' && 'id' in row) {
    void router.push(`/employees/${String(row.id)}`);
  } else {
    console.info(actionId, row.id);
  }
}

// `primaryAction` (botón "Nuevo" de la tabla) también es camelCase → addEventListener.
function handleStaffPrimary(): void { onNew(); }
function handleRolesPrimary(): void { onNewRole(); }

onMounted(() => {
  // Etiquetas en español para las tablas del shell (ok-data-table usa inglés por defecto).
  if (staffTable.value) (staffTable.value as HTMLElement & { labels: typeof DT_LABELS_ES }).labels = DT_LABELS_ES;
  if (rolesTable.value) (rolesTable.value as HTMLElement & { labels: typeof DT_LABELS_ES }).labels = DT_LABELS_ES;
  staffTable.value?.addEventListener('rowAction', handleRowAction);
  rolesTable.value?.addEventListener('rowAction', handleRowAction);
  staffTable.value?.addEventListener('primaryAction', handleStaffPrimary);
  rolesTable.value?.addEventListener('primaryAction', handleRolesPrimary);
});
onBeforeUnmount(() => {
  staffTable.value?.removeEventListener('rowAction', handleRowAction);
  rolesTable.value?.removeEventListener('rowAction', handleRowAction);
  staffTable.value?.removeEventListener('primaryAction', handleStaffPrimary);
  rolesTable.value?.removeEventListener('primaryAction', handleRolesPrimary);
});
</script>

<style scoped>
/* Fija el alto al área de `ion-content` (no `min-height`): las tablas en modo `fill` resuelven
   su `:host{height:100%}` contra este contenedor → cabecera + pager fijos y scroll SOLO en el
   cuerpo, adaptándose a la altura disponible del dispositivo. Mismo patrón que `.outlet` de
   ModuleView. */
.fill {
  height: 100%;
}
</style>
