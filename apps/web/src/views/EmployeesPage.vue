<template>
  <AppPage :title="t('nav.employees')">
    <div class="fill">
      <div v-if="loading" class="table-loading">
        <ion-spinner name="crescent" />
      </div>

      <template v-else>
        <ok-inline-feedback
          v-if="staffLoadError && (tab === 'staff' || tab === 'roles')"
          class="load-feedback"
          tone="warning"
          icon="cloud-offline-outline"
          :heading="t('employees.loadErrorTitle')"
        >
          {{ t('employees.loadErrorBody') }}
          <ion-button slot="actions" size="small" fill="outline" @click="loadStaff">
            {{ t('employees.retry') }}
          </ion-button>
        </ok-inline-feedback>

        <!-- Personal operativo del módulo staff. Alta y edición rápida viven dentro del panel
             lateral de la tabla; la edición detallada conserva /employees/:id. -->
        <ok-data-table
          v-show="tab === 'staff'"
          ref="staffTable"
          fill
          :addable="!staffLoadError"
          :columns="employeeColumns"
          :rows="employees"
          :searchKeys="['full_name', 'email', 'role_name']"
          :actions="staffRowActions"
          :search-placeholder="t('employees.searchEmployee')"
          :empty-message="t('employees.emptyStaff')"
          page-size="10"
          views
          csv
          csv-name="empleados"
          column-picker
        >
          <form slot="create" class="table-form" @submit.prevent="createEmployee">
            <ok-inline-feedback v-if="staffFormError" tone="danger">
              {{ staffFormError }}
            </ok-inline-feedback>
            <ion-input
              v-model="staffForm.firstName"
              fill="outline"
              label-placement="floating"
              :label="t('employeeForm.firstName')"
              :maxlength="100"
              required
            />
            <ion-input
              v-model="staffForm.lastName"
              fill="outline"
              label-placement="floating"
              :label="t('employeeForm.lastName')"
              :maxlength="100"
              required
            />
            <ion-input
              v-model="staffForm.email"
              fill="outline"
              label-placement="floating"
              type="email"
              autocomplete="email"
              :label="t('employeeForm.email')"
              :maxlength="254"
            />
            <ion-select
              v-model="staffForm.roleId"
              fill="outline"
              label-placement="floating"
              interface="popover"
              :label="t('employeeForm.role')"
            >
              <ion-select-option value="">{{ t('employeeForm.noRole') }}</ion-select-option>
              <ion-select-option v-for="role in roles" :key="String(role.id)" :value="String(role.id)">
                {{ role.name }}
              </ion-select-option>
            </ion-select>
            <ion-button
              type="submit"
              size="small"
              :disabled="staffSaving || !staffForm.firstName.trim() || !staffForm.lastName.trim()"
            >
              <ion-spinner v-if="staffSaving" slot="start" name="crescent" />
              {{ staffSaving ? t('employeeForm.saving') : t('employeeForm.create') }}
            </ion-button>
          </form>
        </ok-data-table>

        <!-- Identidades reales con acceso al Hub. `pinUsers` viene del runtime; añadimos el
             usuario de la sesión si su acceso es Cloud y no tiene PIN local. -->
        <ok-data-table
          v-show="tab === 'users'"
          ref="usersTable"
          fill
          :columns="userColumns"
          :rows="hubUsers"
          :searchKeys="['name', 'email', 'role']"
          :search-placeholder="t('employees.searchUser')"
          :empty-message="t('employees.emptyUsers')"
          page-size="10"
          views
          column-picker
        ></ok-data-table>

        <!-- Roles operativos reales del módulo staff. -->
        <ok-data-table
          v-show="tab === 'roles'"
          ref="rolesTable"
          fill
          :addable="!staffLoadError"
          :columns="roleColumns"
          :rows="roles"
          :searchKeys="['name', 'description']"
          :search-placeholder="t('employees.searchRole')"
          :empty-message="t('employees.emptyRoles')"
          page-size="10"
          views
          csv
          csv-name="roles"
          column-picker
        >
          <form slot="create" class="table-form" @submit.prevent="createRole">
            <ok-inline-feedback v-if="roleFormError" tone="danger">
              {{ roleFormError }}
            </ok-inline-feedback>
            <ion-input
              v-model="roleForm.name"
              fill="outline"
              label-placement="floating"
              :label="t('employees.roleName')"
              :maxlength="100"
              required
            />
            <ion-textarea
              v-model="roleForm.description"
              fill="outline"
              label-placement="floating"
              :label="t('employees.roleDescription')"
              :auto-grow="true"
            />
            <ion-button type="submit" size="small" :disabled="roleSaving || !roleForm.name.trim()">
              <ion-spinner v-if="roleSaving" slot="start" name="crescent" />
              {{ roleSaving ? t('employeeForm.saving') : t('employees.newRole') }}
            </ion-button>
          </form>
        </ok-data-table>

        <ApiKeysPanel v-if="isAdmin" v-show="tab === 'apikeys'" />
      </template>
    </div>

    <template #footer>
      <ion-footer class="ion-no-border">
        <ion-toolbar>
          <ion-segment
            class="ok-tabbar"
            :value="tab"
            scrollable
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
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonButton,
  IonFooter,
  IonInput,
  IonLabel,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToolbar,
  alertController,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import ApiKeysPanel from './ApiKeysPanel.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import { getClient, pinUsers } from '../lib/runtime';
import { isAdmin, user } from '../lib/session';
import { toast } from '../lib/toast';

const { t, locale } = useI18n();

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
type DataTableElement = HTMLElement & {
  labels: Record<string, string>;
  close?: () => void;
};

type EmployeeTab = 'staff' | 'users' | 'roles' | 'apikeys';
const TABS: readonly EmployeeTab[] = ['staff', 'users', 'roles', 'apikeys'];
const route = useRoute();
const router = useRouter();
const tab = ref<EmployeeTab>(TABS.find((value) => value === route.hash.slice(1)) ?? 'staff');

watch(tab, (value) => {
  if (value !== (route.hash.slice(1) || 'staff')) void router.replace({ hash: `#${value}` });
});
watch(() => route.hash, (hash) => {
  const next = TABS.find((value) => value === hash.slice(1)) ?? 'staff';
  if (next !== tab.value) tab.value = next;
});
watch(isAdmin, (admin) => {
  if (!admin && tab.value === 'apikeys') tab.value = 'staff';
});

const client = getClient();
const loading = ref(true);
const staffLoadError = ref(false);
const employees = ref<Row[]>([]);
const roles = ref<Row[]>([]);

const staffForm = reactive({ firstName: '', lastName: '', email: '', roleId: '' });
const roleForm = reactive({ name: '', description: '' });
const staffSaving = ref(false);
const roleSaving = ref(false);
const staffFormError = ref('');
const roleFormError = ref('');

const hubUsers = computed<Row[]>(() => {
  const rows = pinUsers.value.map((entry) => ({
    id: entry.id,
    name: entry.name,
    email: '',
    role: entry.role,
    access: 'pin',
  }));
  const active = user.value;
  if (active && !rows.some((entry) => entry.id === active.id)) {
    rows.push({
      id: active.id,
      name: active.name,
      email: active.email ?? '',
      role: active.role ?? '',
      access: 'cloud',
    });
  }
  return rows;
});

function fmtDate(iso: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(locale.value === 'en' ? 'en-GB' : 'es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

function nameCell(row: Row): Node {
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:flex;align-items:center;gap:.6rem';
  const avatar = document.createElement('span');
  avatar.textContent = (String(row.full_name ?? row.name ?? '?')[0] ?? '?').toUpperCase();
  avatar.style.cssText =
    'display:grid;place-items:center;width:2rem;height:2rem;border-radius:999px;font-size:12px;font-weight:700;' +
    'background:color-mix(in srgb,var(--ion-color-primary) 15%,transparent);color:var(--ion-color-primary)';
  const name = document.createElement('span');
  name.textContent = String(row.full_name ?? row.name ?? '');
  name.style.fontWeight = '500';
  wrap.append(avatar, name);
  return wrap;
}

function badgeCell(text: string, tone: 'success' | 'neutral' | 'primary' | 'danger'): Node {
  const ion = tone === 'neutral' ? 'medium' : tone;
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${ion}-rgb), 0.14);` +
    `color:var(--ion-color-${ion}-shade, var(--ion-color-${ion}))`;
  return span;
}

const employeeColumns = computed<DataTableColumn[]>(() => [
  { key: 'full_name', header: t('employees.colEmployee'), render: nameCell },
  { key: 'email', header: t('employees.colEmail'), format: (row) => String(row.email ?? '—') || '—' },
  { key: 'role_name', header: t('employees.colRole'), filterable: true, filterType: 'select' },
  {
    key: 'status',
    header: t('employees.colStatus'),
    filterable: true,
    filterType: 'select',
    render: (row) => badgeCell(
      t(`employees.status.${String(row.status ?? 'inactive')}`),
      row.status === 'active' ? 'success' : row.status === 'terminated' ? 'danger' : 'neutral',
    ),
  },
  {
    key: 'hire_date',
    header: t('employees.colCreatedAt'),
    filterable: true,
    filterType: 'daterange',
    format: (row) => fmtDate(String(row.hire_date ?? '')),
  },
]);

const userColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colUser'), render: nameCell },
  { key: 'email', header: t('employees.colEmail'), format: (row) => String(row.email ?? '') || '—' },
  { key: 'role', header: t('employees.colRole'), filterable: true, filterType: 'select' },
  {
    key: 'access',
    header: t('employees.colAccess'),
    render: (row) => badgeCell(
      row.access === 'pin' ? t('employees.accessPin') : t('employees.accessCloud'),
      row.access === 'pin' ? 'primary' : 'neutral',
    ),
  },
]);

const roleColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colRole') },
  {
    key: 'is_active',
    header: t('employees.colStatus'),
    filterable: true,
    filterType: 'select',
    render: (row) => badgeCell(
      row.is_active ? t('employees.active') : t('employees.inactive'),
      row.is_active ? 'primary' : 'neutral',
    ),
  },
  { key: 'member_count', header: t('employees.colMembers'), align: 'center' },
  { key: 'description', header: t('employees.roleDescription'), format: (row) => String(row.description ?? '—') },
]);

const staffRowActions = computed<DataTableAction[]>(() => [
  { id: 'edit', label: t('employees.actionEdit'), icon: 'pencil' },
  { id: 'delete', label: t('employees.actionDelete'), icon: 'trash', color: 'danger' },
]);

async function loadStaff(): Promise<void> {
  loading.value = true;
  staffLoadError.value = false;
  const [memberResult, roleResult] = await Promise.allSettled([
    client.queryPage<Row>('staff.members.list', { limit: 200 }),
    client.queryPage<Row>('staff.roles.list', { limit: 200 }),
  ]);
  employees.value = memberResult.status === 'fulfilled' ? memberResult.value.rows : [];
  roles.value = roleResult.status === 'fulfilled' ? roleResult.value.rows : [];
  staffLoadError.value = memberResult.status === 'rejected' || roleResult.status === 'rejected';
  loading.value = false;
}

async function createEmployee(): Promise<void> {
  if (!staffForm.firstName.trim() || !staffForm.lastName.trim()) return;
  staffSaving.value = true;
  staffFormError.value = '';
  try {
    await client.command('staff.members.create', {
      first_name: staffForm.firstName.trim(),
      last_name: staffForm.lastName.trim(),
      email: staffForm.email.trim(),
      role_id: staffForm.roleId || null,
      is_bookable: 1,
      status: 'active',
    });
    Object.assign(staffForm, { firstName: '', lastName: '', email: '', roleId: '' });
    staffTable.value?.close?.();
    await loadStaff();
    void toast(t('employees.created'), 'success');
  } catch (error) {
    staffFormError.value = error instanceof Error ? error.message : t('employees.saveError');
  } finally {
    staffSaving.value = false;
  }
}

async function createRole(): Promise<void> {
  if (!roleForm.name.trim()) return;
  roleSaving.value = true;
  roleFormError.value = '';
  try {
    await client.command('staff.roles.create', {
      name: roleForm.name.trim(),
      description: roleForm.description.trim(),
      color: '',
      order: 0,
    });
    Object.assign(roleForm, { name: '', description: '' });
    rolesTable.value?.close?.();
    await loadStaff();
    void toast(t('employees.roleCreated'), 'success');
  } catch (error) {
    roleFormError.value = error instanceof Error ? error.message : t('employees.saveError');
  } finally {
    roleSaving.value = false;
  }
}

async function deleteEmployee(row: Row): Promise<void> {
  const alert = await alertController.create({
    header: t('employees.deleteTitle'),
    message: t('employees.deleteBody', { name: String(row.full_name ?? '') }),
    buttons: [
      { text: t('employeeForm.cancel'), role: 'cancel' },
      { text: t('employees.actionDelete'), role: 'confirm', cssClass: 'alert-button-danger' },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss();
  if (result.role !== 'confirm') return;
  try {
    await client.command('staff.members.delete', { staff_id: String(row.id) });
    await loadStaff();
    void toast(t('employees.deleted'), 'success');
  } catch {
    void toast(t('employees.deleteError'), 'danger');
  }
}

const staffTable = ref<DataTableElement | null>(null);
const usersTable = ref<DataTableElement | null>(null);
const rolesTable = ref<DataTableElement | null>(null);

function handleStaffRowAction(event: Event): void {
  const { actionId, row } = (event as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'edit' && row.id) void router.push(`/employees/${encodeURIComponent(String(row.id))}`);
  if (actionId === 'delete' && row.id) void deleteEmployee(row);
}

function bindTable(element: DataTableElement | null, rowHandler?: (event: Event) => void): void {
  if (!element) return;
  element.labels = dataTableLabels(locale.value);
  if (rowHandler) {
    element.removeEventListener('rowAction', rowHandler);
    element.addEventListener('rowAction', rowHandler);
  }
}

watch(staffTable, (element) => bindTable(element, handleStaffRowAction));
watch(usersTable, (element) => bindTable(element));
watch(rolesTable, (element) => bindTable(element));
watch(locale, () => {
  bindTable(staffTable.value, handleStaffRowAction);
  bindTable(usersTable.value);
  bindTable(rolesTable.value);
});

onMounted(() => {
  void loadStaff();
});
onBeforeUnmount(() => {
  staffTable.value?.removeEventListener('rowAction', handleStaffRowAction);
});
</script>

<style scoped>
.fill {
  height: 100%;
}

.table-loading {
  display: flex;
  justify-content: center;
  padding: 2.5rem 0;
}

.load-feedback {
  margin-bottom: 0.75rem;
}

.table-form {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}
</style>
