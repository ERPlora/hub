<script setup lang="ts">
// Employees › API keys, for whoever runs the business. A key's token is shown only once, when it is created or
// rotated. A list that cannot be read is never shown as «no keys».
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  formatDateTime,
  FormModal,
  type FormModalError,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonCheckbox, IonInput, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, onBeforeUnmount, ref } from 'vue';

import { ACTIONS, askedScopes, EVERY_APP, modeOf } from '../lib/api-key-scopes';
import { useBaseI18n } from '../lib/i18n';
import { useUnsavedFormOnOpen } from '../lib/unsaved-changes';
import type { ApiAction, ApiKeyRow, ApiKeyScopes } from '../operations/api_keys';
import FieldGroup from './FieldGroup.vue';

interface KeyForm {
  name: string;
  where: 'all' | 'apps';
  ticked: ApiKeyScopes;
}

const COPIED_MS = 2000;

const { t, locale } = useBaseI18n();
const { data, status, refresh } = useLive('base.api_key.list', {});
const create = useCommand('base.api_key.create');
const rotate = useCommand('base.api_key.rotate');
const revoke = useCommand('base.api_key.revoke');

const rows = computed<ApiKeyRow[]>(() => data.value?.keys ?? []);
const apps = computed(() => data.value?.apps ?? []);
const grantable = computed<ApiKeyScopes>(() => data.value?.grantable ?? {});
const failed = computed(() => status.value === 'error' && data.value === undefined);
const when = (value: string | null) => (value ? formatDateTime(value, locale.value) : t('base.apiKeys.never'));
const appName = (id: string) => apps.value.find((app) => app.id === id)?.name ?? id;

/** «Full access», or «All apps R/C · Taxes U»: what a key may do on every app and app by app. */
function scopesText(row: ApiKeyRow): string {
  const mode = modeOf(row.scopes);
  if (mode) return t(`base.apiKeys.modes.${mode}`);
  return Object.entries(row.scopes)
    .map(([app, actions]) => {
      const where = app === EVERY_APP ? t('base.apiKeys.allApps') : appName(app);
      return `${where} ${actions.map((action) => t(`base.apiKeys.short.${action}`)).join('/')}`;
    })
    .join(' · ');
}

const columns = computed<DataTableColumn<ApiKeyRow>[]>(() => [
  { key: 'name', label: t('base.apiKeys.columns.name'), width: 'minmax(10rem,2fr)' },
  { key: 'prefix', label: t('base.apiKeys.columns.token'), format: (value) => `${value as string}…`, width: '13rem', sortable: false },
  { key: 'scopes', label: t('base.apiKeys.columns.permissions'), cell: 'scopes', sortValue: scopesText, width: 'minmax(10rem,2fr)' },
  { key: 'revoked_at', label: t('base.apiKeys.columns.state'), cell: 'state', width: '8rem' },
  { key: 'created_by', label: t('base.apiKeys.columns.createdBy'), format: (value) => (value as string) || '—', width: 'minmax(8rem,1fr)' },
  { key: 'created_at', label: t('base.apiKeys.columns.created'), format: (value) => when(value as string), width: '11rem' },
  { key: 'last_used_at', label: t('base.apiKeys.columns.lastUsed'), format: (value) => when(value as string | null), width: '11rem' },
  { key: 'rate_per_minute', label: t('base.apiKeys.columns.limit'), format: (value) => `${value as number}/min`, align: 'right', width: '7rem' },
]);

const actions = computed<DataTableAction<ApiKeyRow>[]>(() => [
  { id: 'rotate', label: t('base.apiKeys.rotate'), icon: 'ion:refresh-outline', hidden: (row) => row.revoked_at !== null },
  { id: 'revoke', label: t('base.apiKeys.revoke'), icon: 'ion:ban-outline', color: 'danger', hidden: (row) => row.revoked_at !== null },
]);

// ── Errors, from their code ──
const ERRORS: Readonly<Record<string, string>> = Object.freeze({
  'base.api_key_revoked': 'base.apiKeys.errors.revoked',
  'base.api_key_not_found': 'base.apiKeys.errors.gone',
  'base.api_key_scopes_required': 'base.apiKeys.errors.scopesRequired',
  'base.api_key_scope_unknown': 'base.apiKeys.errors.scopeUnknown',
  'base.api_key_beyond_maker': 'base.apiKeys.errors.beyondMaker',
  permission_denied: 'base.apiKeys.errors.denied',
});

function failure(reason: unknown, fallback: string): FormModalError {
  const error = reason instanceof ApiError ? reason : undefined;
  return {
    message: t((error?.code && ERRORS[error.code]) ?? fallback),
    code: error?.code,
    status: error?.status,
    fields: error?.fields,
  };
}

// ── «New API key» ──
const creating = ref(false);
const createError = ref<FormModalError | null>(null);
const form = ref<KeyForm>({ name: '', where: 'apps', ticked: {} });
const rateText = ref('60');

function startCreating(): void {
  form.value = { name: '', where: 'apps', ticked: {} };
  rateText.value = '60';
  createError.value = null;
  creating.value = true;
}

const rateValid = computed(() => /^\d+$/.test(rateText.value) && Number(rateText.value) >= 1 && Number(rateText.value) <= 10000);
const everyApp = computed(() => form.value.where === 'all' && grantable.value[EVERY_APP] !== undefined);
/** A row of boxes per app who asks may give something on, or a single one for every app. */
const boxRows = computed(() =>
  everyApp.value ? [{ id: EVERY_APP, name: t('base.apiKeys.allApps') }] : apps.value.filter((app) => grantable.value[app.id] !== undefined),
);
const asked = computed(() => askedScopes(form.value.ticked, grantable.value, everyApp.value));
const canCreate = computed(() => form.value.name.trim() !== '' && rateValid.value && Object.keys(asked.value).length > 0);

function choose(where: unknown): void {
  form.value = { ...form.value, where: where === 'all' ? 'all' : 'apps' };
}

function ticked(app: string, action: ApiAction): boolean {
  return form.value.ticked[app]?.includes(action) ?? false;
}

function tick(app: string, action: ApiAction, on: boolean): void {
  const given = ACTIONS.filter((each) => (each === action ? on : ticked(app, each)));
  form.value = { ...form.value, ticked: { ...form.value.ticked, [app]: given } };
}

/** The apps with a box ticked: a box ticked and unticked again is no change. */
const tickedScopes = () => Object.fromEntries(Object.entries(form.value.ticked).filter(([, given]) => given.length > 0));

const canDismiss = useUnsavedFormOnOpen(
  'api-key-form',
  () => ({ name: form.value.name, rate: rateText.value, where: form.value.where, scopes: tickedScopes() }),
  creating,
);

async function submitCreate(): Promise<void> {
  if (!canCreate.value || create.pending.value) return;
  createError.value = null;
  try {
    const answer = await create.run({ name: form.value.name.trim(), rate_per_minute: Number(rateText.value), scopes: asked.value });
    creating.value = false;
    showToken(answer.token);
  } catch (reason) {
    createError.value = failure(reason, 'base.apiKeys.errors.create');
  }
}

// ── The token, once ──
const token = ref('');
const tokenOpen = ref(false);
const copied = ref(false);
const copyError = ref('');
let copiedTimer: ReturnType<typeof setTimeout> | undefined;

function showToken(value: string): void {
  token.value = value;
  copied.value = false;
  copyError.value = '';
  tokenOpen.value = true;
}

async function copyToken(): Promise<void> {
  copyError.value = '';
  try {
    await navigator.clipboard.writeText(token.value);
    copied.value = true;
    clearTimeout(copiedTimer);
    copiedTimer = setTimeout(() => (copied.value = false), COPIED_MS);
  } catch {
    copyError.value = t('base.apiKeys.token.copyFailed');
  }
}

function closeToken(): void {
  tokenOpen.value = false;
  token.value = '';
  clearTimeout(copiedTimer);
}

onBeforeUnmount(() => clearTimeout(copiedTimer));

// ── «Rotate» and «Revoke», asked first ──
const rotating = ref<ApiKeyRow | null>(null);
const revoking = ref<ApiKeyRow | null>(null);
const rotateError = ref<FormModalError | null>(null);
const revokeError = ref<FormModalError | null>(null);

function onAction(event: DataTableActionEvent<ApiKeyRow>): void {
  if (event.actionId === 'rotate') {
    rotateError.value = null;
    rotating.value = event.row;
  } else if (event.actionId === 'revoke') {
    revokeError.value = null;
    revoking.value = event.row;
  }
}

async function confirmRotate(): Promise<void> {
  if (!rotating.value || rotate.pending.value) return;
  try {
    const answer = await rotate.run({ id: rotating.value.id });
    rotating.value = null;
    showToken(answer.token);
  } catch (reason) {
    rotateError.value = failure(reason, 'base.apiKeys.errors.rotate');
  }
}

async function confirmRevoke(): Promise<void> {
  if (!revoking.value || revoke.pending.value) return;
  const name = revoking.value.name;
  try {
    await revoke.run({ id: revoking.value.id });
    revoking.value = null;
    toastSuccess(t('base.apiKeys.revoked', { name }));
  } catch (reason) {
    revokeError.value = failure(reason, 'base.apiKeys.errors.revoke');
  }
}
</script>

<template>
  <section class="api-keys">
    <header class="api-keys-head">
      <p class="api-keys-intro">
        {{ t('base.apiKeys.intro') }}
      </p>
      <ion-button
        v-if="data"
        data-testid="api-keys-new"
        @click="startCreating()"
      >
        {{ t('base.apiKeys.new') }}
      </ion-button>
    </header>
    <DataTable
      testid="api-keys"
      :columns="columns"
      :rows="rows"
      :actions="actions"
      :page-size="20"
      :page-size-options="[]"
      :views="['table', 'cards']"
      :card-title="(row: ApiKeyRow) => row.name"
      card-title-column="name"
      :search-keys="['name', 'prefix']"
      :search-placeholder="t('base.apiKeys.search')"
      :empty-message="t('base.apiKeys.empty')"
      :loading="data === undefined && !failed"
      :error="failed ? t('base.apiKeys.loadError') : undefined"
      @action="onAction"
      @retry="refresh()"
    >
      <template #scopes="{ row }">
        <span data-testid="api-keys-scopes">{{ scopesText(row as ApiKeyRow) }}</span>
      </template>
      <template #state="{ row }">
        <StatusPill
          size="sm"
          :tone="(row as ApiKeyRow).revoked_at ? 'neutral' : 'success'"
          :label="t((row as ApiKeyRow).revoked_at ? 'base.apiKeys.states.revoked' : 'base.apiKeys.states.active')"
        />
      </template>
    </DataTable>

    <FormModal
      v-model:open="creating"
      :can-dismiss="canDismiss"
      testid="api-key-form"
      size="md"
      :title="t('base.apiKeys.form.title')"
      :submit-label="t('base.apiKeys.form.submit')"
      :cancel-label="t('base.apiKeys.form.cancel')"
      :pending="create.pending.value"
      :submit-disabled="!canCreate"
      :error="createError"
      @submit="submitCreate()"
      @cancel="creating = false"
    >
      <div class="api-key-form">
        <ion-input
          data-testid="api-key-form-name"
          :value="form.name"
          :label="t('base.apiKeys.form.name')"
          :placeholder="t('base.apiKeys.form.namePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="80"
          @ion-input="form = { ...form, name: String($event.detail.value ?? '') }"
        />
        <ion-input
          data-testid="api-key-form-rate"
          type="number"
          inputmode="numeric"
          :value="rateText"
          :label="t('base.apiKeys.form.rate')"
          :helper-text="t('base.apiKeys.form.rateHint')"
          :error-text="t('base.apiKeys.form.rateHint')"
          :class="{ 'ion-invalid ion-touched': !rateValid }"
          label-placement="floating"
          fill="outline"
          mode="md"
          :min="1"
          :max="10000"
          @ion-input="rateText = String($event.detail.value ?? '')"
        />
        <FieldGroup class="api-key-scopes">
          <legend>{{ t('base.apiKeys.form.mode') }}</legend>
          <ion-segment
            v-if="grantable[EVERY_APP]"
            data-testid="api-key-form-where"
            :value="form.where"
            :aria-label="t('base.apiKeys.form.mode')"
            @ion-change="choose($event.detail.value)"
          >
            <ion-segment-button
              value="all"
              data-testid="api-key-form-where-all"
            >
              <ion-label>{{ t('base.apiKeys.allApps') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button
              value="apps"
              data-testid="api-key-form-where-apps"
            >
              <ion-label>{{ t('base.apiKeys.form.chooseApps') }}</ion-label>
            </ion-segment-button>
          </ion-segment>
          <p class="api-keys-hint">
            {{ t(everyApp ? 'base.apiKeys.form.allAppsHint' : 'base.apiKeys.form.perAppHint') }}
          </p>
        </FieldGroup>
        <div
          class="api-key-apps"
          data-testid="api-key-form-apps"
        >
          <p
            v-if="boxRows.length === 0"
            class="api-keys-hint"
          >
            {{ t('base.apiKeys.form.noApps') }}
          </p>
          <table v-else>
            <thead>
              <tr>
                <th scope="col">
                  {{ t('base.apiKeys.form.app') }}
                </th>
                <th
                  v-for="action in ACTIONS"
                  :key="action"
                  scope="col"
                  class="ion-text-center"
                >
                  {{ t(`base.apiKeys.actions.${action}`) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in boxRows"
                :key="row.id"
              >
                <th scope="row">
                  {{ row.name }}
                </th>
                <td
                  v-for="action in ACTIONS"
                  :key="action"
                >
                  <ion-checkbox
                    v-if="grantable[row.id]?.includes(action)"
                    :data-testid="`api-key-form-${row.id}-${action}`"
                    :checked="ticked(row.id, action)"
                    :aria-label="`${row.name} · ${t(`base.apiKeys.actions.${action}`)}`"
                    @ion-change="tick(row.id, action, Boolean($event.detail.checked))"
                  />
                  <span v-else>—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </FormModal>

    <FormModal
      v-model:open="tokenOpen"
      testid="api-key-token"
      size="md"
      :title="t('base.apiKeys.token.title')"
      :dismiss-on-backdrop="false"
      @cancel="closeToken()"
    >
      <InlineFeedback
        tone="warning"
        :heading="t('base.apiKeys.token.heading')"
      >
        {{ t('base.apiKeys.token.once') }}
      </InlineFeedback>
      <code
        class="api-key-token"
        data-testid="api-key-token-value"
      >{{ token }}</code>
      <p
        v-if="copyError"
        class="api-keys-error"
        role="alert"
      >
        {{ copyError }}
      </p>
      <template #footer>
        <ion-button
          fill="outline"
          data-testid="api-key-token-copy"
          @click="copyToken()"
        >
          {{ copied ? t('base.apiKeys.token.copied') : t('base.apiKeys.token.copy') }}
        </ion-button>
        <ion-button
          data-testid="api-key-token-done"
          @click="closeToken()"
        >
          {{ t('base.apiKeys.token.done') }}
        </ion-button>
      </template>
    </FormModal>

    <ConfirmDialog
      :open="rotating !== null"
      testid="api-key-rotate"
      :title="t('base.apiKeys.rotateConfirm.title')"
      :message="t('base.apiKeys.rotateConfirm.message', { name: rotating?.name ?? '' })"
      :confirm-label="t('base.apiKeys.rotateConfirm.confirm')"
      :cancel-label="t('base.apiKeys.form.cancel')"
      :pending="rotate.pending.value"
      :error="rotateError"
      @confirm="confirmRotate()"
      @cancel="rotating = null"
    />
    <ConfirmDialog
      :open="revoking !== null"
      testid="api-key-revoke"
      tone="danger"
      :title="t('base.apiKeys.revokeConfirm.title')"
      :message="t('base.apiKeys.revokeConfirm.message', { name: revoking?.name ?? '' })"
      :confirm-label="t('base.apiKeys.revokeConfirm.confirm')"
      :cancel-label="t('base.apiKeys.form.cancel')"
      :pending="revoke.pending.value"
      :error="revokeError"
      @confirm="confirmRevoke()"
      @cancel="revoking = null"
    />
    <RouterLink
      to="/api-docs"
      class="api-keys-docs"
      data-testid="api-keys-docs"
    >
      {{ t('base.apiKeys.docs') }}
    </RouterLink>
  </section>
</template>

<style scoped>
.api-keys-docs {
  align-self: flex-start;
  color: var(--ion-color-primary);
  font-size: 0.875rem;
  font-weight: 600;
}

.api-keys {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.api-keys-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.api-keys-intro,
.api-keys-hint,
.api-key-apps thead th {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.api-keys-intro {
  flex: 1 1 20rem;
}

.api-keys-error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}

.api-key-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.api-key-scopes {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.api-key-scopes legend {
  margin-bottom: 6px;
  font-weight: 600;
}

.api-key-apps table {
  width: 100%;
  border-collapse: collapse;
}

.api-key-apps th,
.api-key-apps td {
  padding: 6px 4px;
  border-bottom: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  text-align: left;
}

.api-key-apps td {
  width: 3.5rem;
  text-align: center;
}

.api-key-token {
  display: block;
  margin: 12px 0;
  padding: 12px;
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-color-light, #f4f5f8);
  overflow-wrap: anywhere;
  user-select: all;
}
</style>
