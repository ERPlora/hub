<!--
  Personal — pantalla CORE de los usuarios del Hub.

  Fuente de verdad: la tabla `hub_user` del runtime (`lib/hub-users.ts` → `/api/hub/users`), NO el
  módulo `staff`. `staff` es un módulo de negocio (profesional reservable, comisiones, horarios) con
  su propia navegación; pedirle la lista dejaba esta pantalla muerta («No se pudo cargar el
  personal») en cualquier hub sin él, y escondía al owner/administrador, que entra por Cloud y no
  tiene PIN. Aquí salen TODOS: owner, admins, personal solo-local, activos y dados de baja.

  Pestañas: Personal (los usuarios) · Roles (catálogo del core, lectura) · API keys (solo admin).
  El alta y la edición rápida viven en el panel lateral de la tabla; la edición detallada en
  /employees/:id. Escribir exige rol owner/admin: el runtime revalida y aquí solo se muestra/oculta.
-->
<template>
  <AppPage :title="t('nav.employees')">
    <div class="fill">
      <div v-if="loading" class="table-loading">
        <ion-spinner name="crescent" />
      </div>

      <template v-else>
        <ok-inline-feedback
          v-if="loadError"
          class="load-feedback"
          tone="warning"
          icon="cloud-offline-outline"
          :heading="t('employees.loadErrorTitle')"
        >
          {{ t('employees.loadErrorBody') }}
          <ion-button slot="actions" size="small" fill="outline" @click="load">
            {{ t('employees.retry') }}
          </ion-button>
        </ok-inline-feedback>

        <!-- Usuarios del hub. Alta solo para admin (el runtime rechazaría al resto). -->
        <ok-data-table
          v-show="tab === 'staff'"
          ref="staffTable"
          fill
          :addable="isAdmin && !loadError"
          :columns="userColumns"
          :rows="users"
          :searchKeys="['name', 'email', 'role']"
          :actions="userRowActions"
          :search-placeholder="t('employees.searchEmployee')"
          :empty-message="t('employees.emptyStaff')"
          page-size="10"
          views
          csv
          csv-name="personal"
          column-picker
        >
          <form slot="create" class="table-form" @submit.prevent="createUser">
            <ok-inline-feedback v-if="formError" tone="danger">
              {{ formError }}
            </ok-inline-feedback>
            <ion-input
              v-model="form.name"
              fill="outline"
              label-placement="floating"
              :label="t('employeeForm.fullName')"
              :maxlength="150"
              required
            />
            <ion-input
              v-model="form.email"
              fill="outline"
              label-placement="floating"
              type="email"
              autocomplete="email"
              :label="t('employeeForm.email')"
              :maxlength="254"
            />
            <ion-select
              v-model="form.role"
              fill="outline"
              label-placement="floating"
              interface="popover"
              :label="t('employeeForm.role')"
            >
              <ion-select-option v-for="role in roles" :key="role.name" :value="role.name">
                {{ roleLabel(role.name) }}
              </ion-select-option>
            </ion-select>
            <ion-input
              v-model="form.pin"
              fill="outline"
              label-placement="floating"
              inputmode="numeric"
              :label="t('employeeForm.pin')"
              :helper-text="t('employeeForm.pinHelp')"
              :maxlength="8"
            />
            <ion-button type="submit" size="small" :disabled="saving || !form.name.trim()">
              <ion-spinner v-if="saving" slot="start" name="crescent" />
              {{ saving ? t('employeeForm.saving') : t('employeeForm.create') }}
            </ion-button>
          </form>
        </ok-data-table>

        <!-- Roles del core: catálogo base ∪ los que declaran los módulos activos ∪ los que ya usa
             alguien. No se crean a mano: un rol existe porque algún módulo le concede permisos. -->
        <ok-data-table
          v-show="tab === 'roles'"
          ref="rolesTable"
          fill
          :columns="roleColumns"
          :rows="roles"
          :searchKeys="['name']"
          :search-placeholder="t('employees.searchRole')"
          :empty-message="t('employees.emptyRoles')"
          page-size="10"
          views
          column-picker
        ></ok-data-table>

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
  IonToolbar,
  alertController,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import ApiKeysPanel from './ApiKeysPanel.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import {
  accessOf,
  canDeactivate,
  createHubUser,
  deactivateHubUser,
  listHubRoles,
  listHubUsers,
  type HubRole,
  type HubUser,
} from '../lib/hub-users';
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

// La pestaña «Usuarios» separada desapareció: el personal del Hub SON sus usuarios. Se mantiene el
// valor 'staff' del hash para no romper los deep-links (/employees#staff) ya publicados.
type EmployeeTab = 'staff' | 'roles' | 'apikeys';
const TABS: readonly EmployeeTab[] = ['staff', 'roles', 'apikeys'];
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

const loading = ref(true);
const loadError = ref(false);
const users = ref<HubUser[]>([]);
const roles = ref<HubRole[]>([]);

const form = reactive({ name: '', email: '', role: 'employee', pin: '' });
const saving = ref(false);
const formError = ref('');

function fmtDate(iso: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(locale.value === 'en' ? 'en-GB' : 'es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/** Etiqueta traducida de un rol conocido; los que aporta un módulo se muestran tal cual. */
function roleLabel(role: string): string {
  const key = `employees.roles.${role}`;
  const label = t(key);
  return label === key ? role : label;
}

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

const userColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colEmployee'), render: nameCell },
  { key: 'email', header: t('employees.colEmail'), format: (row) => String(row.email ?? '') || '—' },
  {
    key: 'role',
    header: t('employees.colRole'),
    filterable: true,
    filterType: 'select',
    format: (row) => roleLabel(String(row.role ?? '')),
  },
  {
    // Cómo entra cada uno: PIN local (personal de tienda), cuenta online (owner/admin del portal)
    // o NINGUNA — alguien dado de alta como persona que no inicia sesión en el Hub.
    key: 'has_pin',
    header: t('employees.colAccess'),
    render: (row) => {
      const access = accessOf(row as unknown as HubUser);
      return badgeCell(
        t(`employees.access.${access}`),
        access === 'pin' ? 'primary' : access === 'cloud' ? 'neutral' : 'danger',
      );
    },
  },
  {
    key: 'is_active',
    header: t('employees.colStatus'),
    filterable: true,
    filterType: 'select',
    render: (row) => badgeCell(
      row.is_active ? t('employees.active') : t('employees.inactive'),
      row.is_active ? 'success' : 'neutral',
    ),
  },
  {
    key: 'created_at',
    header: t('employees.colCreatedAt'),
    filterable: true,
    filterType: 'daterange',
    format: (row) => fmtDate(String(row.created_at ?? '')),
  },
]);

const roleColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colRole'), format: (row) => roleLabel(String(row.name ?? '')) },
  { key: 'members', header: t('employees.colMembers'), align: 'center' },
  { key: 'permissions', header: t('employees.colPermissions'), align: 'center' },
]);

const userRowActions = computed<DataTableAction[]>(() =>
  isAdmin.value
    ? [
        { id: 'edit', label: t('employees.actionEdit'), icon: 'pencil' },
        { id: 'delete', label: t('employees.actionDeactivate'), icon: 'person-remove', color: 'danger' },
      ]
    : [],
);

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = false;
  const [userResult, roleResult] = await Promise.allSettled([listHubUsers(), listHubRoles()]);
  users.value = userResult.status === 'fulfilled' ? userResult.value : [];
  roles.value = roleResult.status === 'fulfilled' ? roleResult.value : [];
  loadError.value = userResult.status === 'rejected' || roleResult.status === 'rejected';
  loading.value = false;
}

async function createUser(): Promise<void> {
  if (!form.name.trim()) return;
  saving.value = true;
  formError.value = '';
  try {
    await createHubUser({
      name: form.name.trim(),
      email: form.email.trim(),
      role: form.role || 'employee',
      pin: form.pin.trim(),
    });
    Object.assign(form, { name: '', email: '', role: 'employee', pin: '' });
    staffTable.value?.close?.();
    await load();
    void toast(t('employees.created'), 'success');
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('employees.saveError');
  } finally {
    saving.value = false;
  }
}

async function deactivateUser(row: Row): Promise<void> {
  const id = String(row.id ?? '');
  // Espejo del guard del runtime: si el servidor lo rechazaría, ni se pregunta.
  if (!canDeactivate(users.value, user.value?.id ?? '', id)) {
    void toast(t('employees.deactivateBlocked'), 'warning');
    return;
  }
  const alert = await alertController.create({
    header: t('employees.deactivateTitle'),
    message: t('employees.deactivateBody', { name: String(row.name ?? '') }),
    buttons: [
      { text: t('employeeForm.cancel'), role: 'cancel' },
      { text: t('employees.actionDeactivate'), role: 'confirm', cssClass: 'alert-button-danger' },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss();
  if (result.role !== 'confirm') return;
  try {
    await deactivateHubUser(id);
    await load();
    void toast(t('employees.deactivated'), 'success');
  } catch (error) {
    void toast(error instanceof Error ? error.message : t('employees.deleteError'), 'danger');
  }
}

const staffTable = ref<DataTableElement | null>(null);
const rolesTable = ref<DataTableElement | null>(null);

function handleUserRowAction(event: Event): void {
  const { actionId, row } = (event as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'edit' && row.id) void router.push(`/employees/${encodeURIComponent(String(row.id))}`);
  if (actionId === 'delete' && row.id) void deactivateUser(row);
}

function bindTable(element: DataTableElement | null, rowHandler?: (event: Event) => void): void {
  if (!element) return;
  element.labels = dataTableLabels(locale.value);
  if (rowHandler) {
    element.removeEventListener('rowAction', rowHandler);
    element.addEventListener('rowAction', rowHandler);
  }
}

watch(staffTable, (element) => bindTable(element, handleUserRowAction));
watch(rolesTable, (element) => bindTable(element));
watch(locale, () => {
  bindTable(staffTable.value, handleUserRowAction);
  bindTable(rolesTable.value);
});

onMounted(() => {
  void load();
});
onBeforeUnmount(() => {
  staffTable.value?.removeEventListener('rowAction', handleUserRowAction);
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
