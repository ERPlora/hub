<template>
  <AppPage :title="t('nav.employees')">
    <!-- `.fill` fija el alto al área de `ion-content`; las tablas en modo `fill` resuelven su
         `:host{height:100%}` contra él → cabecera y pager fijos, scroll SOLO en el cuerpo, y se
         adapta a la altura del dispositivo (mismo patrón que ModuleView). -->
    <div class="fill">
      <!-- Carga: miembros + roles en paralelo (cada uno degrada a vacío). -->
      <div v-if="loading" class="table-loading">
        <ion-spinner name="crescent" />
      </div>
      <template v-else>
      <!-- Staff: tabla con ok-data-table (OutFitKit) — toda la chrome (búsqueda, alta, selector de
           columnas, filas/página, vistas, CSV) vive DENTRO de la tabla, no en la topbar.
           Datos REALES del módulo staff (query staff.members_list). Sin módulo → empty-state. -->
      <ok-data-table
        v-show="tab === 'staff'"
        ref="staffTable"
        fill
        :columns="employeeColumns"
        :rows="employees"
        :searchKeys="['full_name', 'email', 'role_name']"
        :actions="rowActions"
        :primaryAction="newEmployeeAction"
        :search-placeholder="t('employees.searchEmployee')"
        page-size="10"
        views
        csv
        csv-name="empleados"
        column-picker
      ></ok-data-table>

      <!-- Usuarios: aún sin backend de usuarios del hub → estado guiado. -->
      <div v-show="tab === 'users'" class="users-empty">
        <ok-empty-state
          icon="person-circle-outline"
          :heading="t('employees.tabUsers')"
          :message="t('employees.usersPlaceholder')"
        />
      </div>

      <!-- Roles: datos REALES del módulo staff (query staff.roles_list). -->
      <ok-data-table
        v-show="tab === 'roles'"
        ref="rolesTable"
        fill
        :columns="roleColumns"
        :rows="roles"
        :searchKeys="['name']"
        :actions="rowActions"
        :primaryAction="newRoleAction"
        :search-placeholder="t('employees.searchRole')"
        page-size="10"
        views
        csv
        csv-name="roles"
        column-picker
      ></ok-data-table>
      </template>

      <!-- API keys: credenciales de máquina del Hub (ADR-0057), gestionadas junto a los usuarios.
           Panel propio (lista + crear + rotar + revocar); v-show conserva su estado al cambiar de
           pestaña, igual que las tablas de arriba. Solo owner/admin (mismo gate que el backend):
           si no es admin, ni se monta el panel. -->
      <ApiKeysPanel v-if="isAdmin" v-show="tab === 'apikeys'" />
    </div>
    <!-- Tabs en footer (staff / usuarios / roles) -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment class="ok-tabbar"
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
          <!-- API keys: solo owner/admin (gestión de credenciales del Hub). El backend exige el
               mismo rol en cada endpoint; aquí ocultamos la pestaña a quien no pueda gestionarlas. -->
          <ion-segment-button v-if="isAdmin" value="apikeys">
            <HubIcon name="keypad-outline" />
            <ion-label>{{ t('employees.tabApiKeys') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import ApiKeysPanel from './ApiKeysPanel.vue';
import { DT_LABELS_ES } from '../lib/data-table-labels';
import { getClient } from '../lib/runtime';
// `isAdmin` (owner/admin) gatea la pestaña «API keys» — mismo criterio que el backend.
import { isAdmin } from '../lib/session';

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

type EmployeeTab = 'staff' | 'users' | 'roles' | 'apikeys';
const TABS: readonly EmployeeTab[] = ['staff', 'users', 'roles', 'apikeys'];

const route = useRoute();
const router = useRouter();
// Deep-link por HASH (/employees#roles). 'apikeys' solo es válido para admins (lo valida el gate
// de abajo); un no-admin con ese hash cae a 'staff' por el watch de isAdmin.
const tab = ref<EmployeeTab>(TABS.find((v) => v === route.hash.slice(1)) ?? 'staff');
// Sincroniza tab ↔ hash (replace = no apila historial).
watch(tab, (value) => {
  if (value !== (route.hash.slice(1) || 'staff')) void router.replace({ hash: `#${value}` });
});
watch(() => route.hash, (h) => {
  const next = TABS.find((v) => v === h.slice(1)) ?? 'staff';
  if (next !== tab.value) tab.value = next;
});

// Defensa: si el usuario deja de ser admin (logout/cambio de sesión) estando en «API keys»,
// volvemos a «staff» para no dejar una pestaña vacía seleccionada. La autoridad real es el backend.
watch(isAdmin, (admin) => {
  if (!admin && tab.value === 'apikeys') tab.value = 'staff';
});

const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });

// ── Celdas ricas: render devuelve un DOM Node (Lit lo interpola). Es el patrón para consumir
//    ok-data-table desde Vue sin poder producir `html` de Lit. ──────────────────────────────
function nameCell(row: Row): Node {
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:flex;align-items:center;gap:.6rem';
  const avatar = document.createElement('span');
  avatar.textContent = (String(row.full_name ?? '?')[0] ?? '?').toUpperCase();
  avatar.style.cssText =
    'display:grid;place-items:center;width:2rem;height:2rem;border-radius:999px;font-size:12px;font-weight:700;' +
    'background:color-mix(in srgb,var(--ion-color-primary) 15%,transparent);color:var(--ion-color-primary)';
  const name = document.createElement('span');
  name.textContent = String(row.full_name ?? '');
  name.style.fontWeight = '500';
  wrap.append(avatar, name);
  return wrap;
}
// Pill de tinte suave (look moderno) con los tokens de color de Ionic. Las CSS vars (--ion-*)
// cruzan el shadow de ok-data-table, así que el color es fiable dentro de la tabla.
function badgeCell(text: string, tone: 'success' | 'neutral' | 'primary' | 'danger'): Node {
  // 'neutral' mapea al color Ionic medium (no existe --ion-color-neutral).
  const ion = tone === 'neutral' ? 'medium' : tone;
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${ion}-rgb), 0.14);` +
    `color:var(--ion-color-${ion}-shade, var(--ion-color-${ion}))`;
  return span;
}

// ── Datos REALES del módulo staff ───────────────────────────────────────────────────────────
// La query staff.members_list devuelve: id, full_name, email, role_name, status, hire_date…
// (campos de members_list.sql). El runtime es la autoridad; si el módulo no está instalado,
// degrada a vacío (ok-data-table pinta su empty interno). Cero mocks.
const client = getClient();
const loading = ref<boolean>(true);
const employees = ref<Row[]>([]);
const roles = ref<Row[]>([]);

async function loadStaff(): Promise<void> {
  loading.value = true;
  try {
    const [memPage, rolePage] = await Promise.all([
      client.queryPage<Row>('staff.members_list', { limit: 200 }).catch(() => ({ rows: [] as Row[] })),
      client.queryPage<Row>('staff.roles_list', { limit: 200 }).catch(() => ({ rows: [] as Row[] })),
    ]);
    employees.value = memPage.rows;
    roles.value = rolePage.rows;
  } catch {
    employees.value = [];
    roles.value = [];
  } finally {
    loading.value = false;
  }
}

// `computed` para que las cabeceras se recalculen al cambiar de idioma en caliente.
const employeeColumns = computed<DataTableColumn[]>(() => [
  { key: 'full_name', header: t('employees.colEmployee'), render: nameCell },
  { key: 'email', header: t('employees.colEmail'), format: (r) => String(r.email ?? '—') },
  { key: 'role_name', header: t('employees.colRole'), filterable: true, filterType: 'select' },
  {
    key: 'status', header: t('employees.colStatus'), filterable: true, filterType: 'select',
    render: (r) => badgeCell(String(r.status), r.status === 'active' ? 'success' : 'neutral')
  },
  { key: 'hire_date', header: t('employees.colCreatedAt'), filterable: true, filterType: 'daterange', format: (r) => fmtDate(String(r.hire_date ?? '')) },
]);

// ── Roles (datos REALES de staff.roles_list) ────────────────────────────────────────────────
// Schema: name, description, member_count, is_active. Sin scope/permissions (no existen en el
// modelo real de staff_role). La cuenta de miembros viene precalculada en la propia query.
const roleColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colRole') },
  {
    key: 'is_active', header: t('employees.colScope'), filterable: true, filterType: 'select',
    render: (r) => badgeCell(r.is_active ? t('employees.active') : t('employees.inactive'), r.is_active ? 'primary' : 'neutral')
  },
  { key: 'member_count', header: t('employees.colMembers'), align: 'center' },
  { key: 'description', header: t('employees.colPermissions'), format: (r) => String(r.description ?? '—') },
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

// Las tablas solo están en el DOM tras la carga (v-else del spinner). Enganchamos labels +
// listeners cuando aparecen (watch del ref, patrón del Dashboard con activityTable).
function bindTable(
  el: HTMLElement | null,
  onRow: (e: Event) => void,
  onPrimary: () => void,
): void {
  if (!el) return;
  (el as HTMLElement & { labels: typeof DT_LABELS_ES }).labels = DT_LABELS_ES;
  el.addEventListener('rowAction', onRow);
  el.addEventListener('primaryAction', onPrimary);
}
function unbindTable(el: HTMLElement | null, onRow: (e: Event) => void, onPrimary: () => void): void {
  if (!el) return;
  el.removeEventListener('rowAction', onRow);
  el.removeEventListener('primaryAction', onPrimary);
}

watch(staffTable, (el) => bindTable(el, handleRowAction, handleStaffPrimary));
watch(rolesTable, (el) => bindTable(el, handleRowAction, handleRolesPrimary));

onMounted(() => {
  void loadStaff();
});
onBeforeUnmount(() => {
  unbindTable(staffTable.value, handleRowAction, handleStaffPrimary);
  unbindTable(rolesTable.value, handleRowAction, handleRolesPrimary);
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

/* Estado de carga de las tablas (miembros + roles en paralelo). Centrado, mismo lenguaje
   que el resto del shell (ion-spinner crescent sobre el lienzo). */
.table-loading {
  display: flex;
  justify-content: center;
  padding: 2.5rem 0;
}

/* Pestaña Usuarios: estado guiado (sin backend de usuarios del hub todavía). ok-empty-state
   aporta el layout centrado; aquí le damos aire para no competir con el tabbar. */
.users-empty {
  padding: 2rem 0;
}
</style>
