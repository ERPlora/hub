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
              mode="md"
              fill="outline"
              label-placement="floating"
              :label="t('employeeForm.fullName')"
              :maxlength="150"
              required
            />
            <!-- «Local user» (hub#355): nombre + PIN, sin email y sin nada en el SaaS. Es la
                 identidad del personal de barra; el usuario de CUENTA lleva email e invitación. -->
            <ion-toggle
              :checked="form.local"
              label-placement="start"
              justify="space-between"
              class="local-toggle"
              @ion-change="form.local = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
            >
              {{ t('employeeForm.localUser') }}
            </ion-toggle>
            <ion-input
              v-if="!form.local"
              v-model="form.email"
              mode="md"
              fill="outline"
              label-placement="floating"
              type="email"
              autocomplete="email"
              :label="t('employeeForm.email')"
              :maxlength="254"
              :helper-text="t('employeeForm.accountEmailHelp')"
              :error-text="issueOn(EMAIL_ISSUES) ? t(`employeeForm.errors.${issueOn(EMAIL_ISSUES)}`) : ''"
              :class="{ 'ion-invalid ion-touched': Boolean(issueOn(EMAIL_ISSUES)) }"
            />
            <ion-select
              v-model="form.role"
              mode="md"
              fill="outline"
              label-placement="floating"
              interface="popover"
              :label="t('employeeForm.role')"
              :error-text="issueOn(ROLE_ISSUES) ? t(`employeeForm.errors.${issueOn(ROLE_ISSUES)}`) : ''"
              :class="{ 'ion-invalid ion-touched': Boolean(issueOn(ROLE_ISSUES)) }"
            >
              <!-- Solo los ASIGNABLES: el runtime rechaza dar un rol declarado que el hub no ha
                   encendido (`ensure_assignable`), así que ofrecerlo sería ofrecer un rechazo. -->
              <ion-select-option v-for="role in assignable" :key="role.name" :value="role.name">
                {{ roleLabel(role.name) }}
              </ion-select-option>
            </ion-select>
            <ion-input
              v-model="form.pin"
              mode="md"
              fill="outline"
              label-placement="floating"
              inputmode="numeric"
              :label="t('employeeForm.pin')"
              :helper-text="form.local ? t('employeeForm.localPinHelp') : t('employeeForm.accountPinHelp')"
              :error-text="pinIssue ? t(`employeeForm.errors.${pinIssue}`) : ''"
              :class="{ 'ion-invalid ion-touched': Boolean(pinIssue) }"
              :maxlength="8"
            />
            <ion-button
              type="submit"
              size="small"
              :disabled="saving || !form.name.trim() || Boolean(altaIssue)"
            >
              <ion-spinner v-if="saving" slot="start" name="crescent" />
              {{ saving ? t('employeeForm.saving') : t('employeeForm.create') }}
            </ion-button>
          </form>
        </ok-data-table>

        <!-- Roles del core: catálogo base ∪ los que declaran los módulos activos ∪ los que ya usa
             alguien. No se crean a mano: un rol existe porque algún módulo lo declara. Encenderlos
             y apagarlos (solo admin) vive en RolesPanel — hub#353. -->
        <RolesPanel v-show="tab === 'roles'" />

        <ApiKeysPanel v-if="isAdmin" v-show="tab === 'apikeys'" />

        <!-- The PIN approval record (hub#512, ADR-0265): who asked for the elevation and who
             authorised it. It belongs here because the row IS two people, and it carries the same
             admin gate as the API keys. `v-if` and not `v-show` on purpose: the read is paged
             server-side since hub#884, but it still belongs to the moment somebody OPENS the tab —
             a visit to People has no business querying an audit trail at all. -->
        <ApprovalsPanel v-if="isAdmin && tab === 'approvals'" />
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
            <ion-segment-button v-if="isAdmin" value="approvals">
              <HubIcon name="finger-print-outline" />
              <ion-label>{{ t('employees.tabApprovals') }}</ion-label>
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
  IonToggle,
  IonToolbar,
  alertController,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import ApiKeysPanel from './ApiKeysPanel.vue';
import ApprovalsPanel from './ApprovalsPanel.vue';
import RolesPanel from './RolesPanel.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import {
  accessEmailWarningOf,
  accessOf,
  assignableRoles,
  canDeactivate,
  accountUserIssue,
  createHubUser,
  deactivateHubUser,
  hubUserErrorKey,
  listHubRoles,
  listHubUsers,
  localUserIssue,
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
type EmployeeTab = 'staff' | 'roles' | 'apikeys' | 'approvals';
const TABS: readonly EmployeeTab[] = ['staff', 'roles', 'apikeys', 'approvals'];
/**
 * The tabs that need an administrator session. The runtime is the authority on both (it revalidates
 * every write on API keys, and gates `hub.approvals.list` on `hub.administer`); here they are only
 * offered or not, and a session that stops being one is taken off them.
 */
const ADMIN_ONLY_TABS: readonly EmployeeTab[] = ['apikeys', 'approvals'];
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
  if (!admin && ADMIN_ONLY_TABS.includes(tab.value)) tab.value = 'staff';
});

const loading = ref(true);
const loadError = ref(false);
const users = ref<HubUser[]>([]);
const roles = ref<HubRole[]>([]);
/** Los que el runtime dejaría asignar hoy (un rol declarado y sin encender, no). */
const assignable = computed(() => assignableRoles(roles.value));

const form = reactive({ name: '', email: '', role: 'employee', pin: '', local: false });
const saving = ref(false);
const formError = ref('');
/** ¿Se ha intentado ya crear? Decide cuándo se pinta «falta el email» (ver `issueOn`). */
const submitted = ref(false);
/**
 * Motivo por el que el runtime rechazaría este alta local, adelantado en la UI (hub#355). El
 * runtime revalida y sigue siendo la autoridad; esto solo evita pulsar «Crear» para enterarse.
 * `pin_in_use` no cabe aquí: los PIN están hasheados y el shell no los ve — llega del servidor.
 */
const altaIssue = computed(() =>
  form.local
    ? localUserIssue({ name: form.name, role: form.role, pin: form.pin }, users.value)
    : accountUserIssue({ email: form.email, role: form.role, pin: form.pin }, users.value),
);

/** Qué campo se lleva cada motivo, para que el error salga donde se arregla. */
const EMAIL_ISSUES = ['account_needs_email', 'invalid_email', 'email_taken', 'local_has_email'];
const ROLE_ISSUES = ['account_role_not_grantable', 'local_cannot_administer'];
/**
 * «Falta el email» es el estado normal del alta rápida recién abierta —el alta de cuenta es la que
 * sale por defecto—, así que ese motivo no se pinta hasta que se intenta crear.
 */
const ISSUES_THAT_WAIT_FOR_SUBMIT = ['account_needs_email'];

/** El motivo actual si pertenece a este campo (y ya toca enseñarlo), o `''`. */
function issueOn(field: string[]): string {
  const issue = altaIssue.value;
  if (!issue || !field.includes(issue)) return '';
  return !submitted.value && ISSUES_THAT_WAIT_FOR_SUBMIT.includes(issue) ? '' : issue;
}

/** El motivo del PIN es el que queda: todo lo que no es del email ni del rol. */
const pinIssue = computed(() =>
  altaIssue.value && ![...EMAIL_ISSUES, ...ROLE_ISSUES].includes(altaIssue.value)
    ? altaIssue.value
    : '',
);

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

/**
 * El email, con su aviso si esa dirección no administra nada (hub#463).
 *
 * El aviso lleva el MOTIVO, porque las dos razones son decisiones distintas: si otra fila ya
 * responde por la dirección hay que editar una de las dos, y si dos perfiles la reclaman hay que
 * decidir cuál es la persona. La salida se dice en el `title`, que es donde cabe la frase entera
 * sin romper la tabla.
 */
function emailCell(row: Row): Node {
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:inline-flex;align-items:center;gap:.45rem';
  const text = document.createElement('span');
  text.textContent = String(row.email ?? '') || '—';
  wrap.append(text);

  const reason = accessEmailWarningOf(row as unknown as HubUser);
  if (reason) {
    const badge = badgeCell(t('employees.accessEmailConflict.badge'), 'danger') as HTMLElement;
    badge.title = t(`employees.accessEmailConflict.${reason}`);
    wrap.append(badge);
  }
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
  // hub#463 — el email se pinta, y si NO revoca nada se dice ahí mismo. La dirección sale de un
  // `COALESCE(hub_user.email, perfil.email)`, así que una fila que el backfill v19 no pudo resolver
  // enseña un email de aspecto sano mientras su baja no revoca la membresía en el SaaS y su primer
  // login aterriza en otra fila. Va PEGADO a la celda del email —no en una columna aparte— porque
  // es esa dirección concreta la que no vale.
  { key: 'email', header: t('employees.colEmail'), render: emailCell },
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
        // `danger` está reservado a `none` — «no puede entrar» —, así que toda vía real es
        // `primary`; la placa (hub#658) es una credencial más, no una anomalía.
        access === 'none' ? 'danger' : access === 'cloud' ? 'neutral' : 'primary',
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

const userRowActions = computed<DataTableAction[]>(() =>
  isAdmin.value
    ? [
        { id: 'edit', label: t('employees.actionEdit'), icon: 'pencil' },
        // `person-remove-outline`, not `person-remove` (hub#793): the latter is not in the
        // registry, so ionicons tried to FETCH it over the network and in the Hub —offline, under
        // CSP— the button came out empty. `-outline` is also the family the rest of the app uses.
        { id: 'delete', label: t('employees.actionDeactivate'), icon: 'person-remove-outline', color: 'danger' },
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
  submitted.value = true;
  if (!form.name.trim() || altaIssue.value) return;
  saving.value = true;
  formError.value = '';
  try {
    await createHubUser({
      name: form.name.trim(),
      // Un usuario local no lleva email: el runtime rechaza el alta si viene uno.
      email: form.local ? '' : form.email.trim(),
      role: form.role || 'employee',
      pin: form.pin.trim(),
      local: form.local,
    });
    Object.assign(form, { name: '', email: '', role: 'employee', pin: '', local: form.local });
    submitted.value = false;
    staffTable.value?.close?.();
    await load();
    void toast(t('employees.created'), 'success');
  } catch (error) {
    formError.value = rejectionMessage(error);
  } finally {
    saving.value = false;
  }
}

/** Motivo TRADUCIDO de un rechazo del runtime; su mensaje inglés solo como último recurso. */
function rejectionMessage(error: unknown): string {
  const key = hubUserErrorKey(error);
  if (key) return t(`employeeForm.errors.${key}`);
  return error instanceof Error ? error.message : t('employees.saveError');
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
watch(locale, () => {
  bindTable(staffTable.value, handleUserRowAction);
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

.local-toggle {
  width: 100%;
  padding-block: 0.25rem;
}
</style>
