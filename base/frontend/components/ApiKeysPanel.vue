<script setup lang="ts">
// Employees › API keys (BASE-G146…G149, G03, G05; the old hub's ApiKeysPanel), for who runs the business: the live
// `base.api_key.list` — Name, Token (its start only), Permissions (the mode, or each app with R/W), State, Created,
// Last use («Never») and Limit («60/min») — and «New API key»: its name, its requests a minute (1 to 10,000) and what it
// may do (full access, read only, write only, or per app over the apps this business has that publish their API; per
// app by default, as the old hub). Its token is shown once, with «Copy» («Copied» for two seconds). «Rotate» gives it a
// new token and «Revoke» stops it for good: both are asked first with their consequence (the old hub rotated at the
// first tap). A business that cannot have keys yet is told so; a refusal is told from its code; a list that cannot be
// read is never «no keys».
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
import { IonButton, IonCheckbox, IonInput } from '@ionic/vue';
import { computed, onBeforeUnmount, ref } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { ApiKeyInput, ApiKeyMode, ApiKeyRow, ApiKind } from '../operations';

const MODES: readonly ApiKeyMode[] = ['full', 'read', 'write', 'per_app'];
const KINDS: readonly ApiKind[] = ['read', 'write'];
const COPIED_MS = 2000;

const { t, locale } = useBaseI18n();
const { data, status, refresh } = useLive('base.api_key.list', {});
const create = useCommand('base.api_key.create');
const rotate = useCommand('base.api_key.rotate');
const revoke = useCommand('base.api_key.revoke');

const rows = computed<ApiKeyRow[]>(() => data.value?.keys ?? []);
const apps = computed(() => data.value?.apps ?? []);
const available = computed(() => data.value?.available ?? false);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const when = (value: string | null) => (value ? formatDateTime(value, locale.value) : t('base.apiKeys.never'));
const appName = (id: string) => apps.value.find((app) => app.id === id)?.name ?? id;

/** «Online shop R/W · Taxes R»: what a key per app may do on each app. */
function scopesText(row: ApiKeyRow): string {
  if (row.mode !== 'per_app') return t(`base.apiKeys.modes.${row.mode}`);
  return Object.entries(row.scopes)
    .map(([app, kinds]) => `${appName(app)} ${kinds.map((kind) => t(`base.apiKeys.short.${kind}`)).join('/')}`)
    .join(' · ');
}

const columns = computed<DataTableColumn<ApiKeyRow>[]>(() => [
  { key: 'name', label: t('base.apiKeys.columns.name'), width: 'minmax(10rem,2fr)' },
  { key: 'prefix', label: t('base.apiKeys.columns.token'), format: (value) => `${value as string}…`, width: '13rem', sortable: false },
  { key: 'mode', label: t('base.apiKeys.columns.permissions'), cell: 'scopes', sortValue: scopesText, width: 'minmax(10rem,2fr)' },
  { key: 'revoked_at', label: t('base.apiKeys.columns.state'), cell: 'state', width: '8rem' },
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
  'base.api_keys_unavailable': 'base.apiKeys.unavailable',
  'base.api_key_revoked': 'base.apiKeys.errors.revoked',
  'base.api_key_not_found': 'base.apiKeys.errors.gone',
  'base.api_key_scopes_required': 'base.apiKeys.errors.scopesRequired',
  'base.api_key_scope_unknown': 'base.apiKeys.errors.scopeUnknown',
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
const form = ref<ApiKeyInput>({ name: '', rate_per_minute: 60, mode: 'per_app', scopes: {} });
const rateText = ref('60');

function startCreating(): void {
  form.value = { name: '', rate_per_minute: 60, mode: 'per_app', scopes: {} };
  rateText.value = '60';
  createError.value = null;
  creating.value = true;
}

const rateValid = computed(() => /^\d+$/.test(rateText.value) && Number(rateText.value) >= 1 && Number(rateText.value) <= 10000);
const anyScope = computed(() => Object.values(form.value.scopes).some((kinds) => kinds.length > 0));
const canCreate = computed(
  () => form.value.name.trim() !== '' && rateValid.value && (form.value.mode !== 'per_app' || anyScope.value),
);

function ticked(app: string, kind: ApiKind): boolean {
  return form.value.scopes[app]?.includes(kind) ?? false;
}

function tick(app: string, kind: ApiKind, on: boolean): void {
  const kinds = new Set(form.value.scopes[app] ?? []);
  if (on) kinds.add(kind);
  else kinds.delete(kind);
  form.value = { ...form.value, scopes: { ...form.value.scopes, [app]: KINDS.filter((each) => kinds.has(each)) } };
}

async function submitCreate(): Promise<void> {
  if (!canCreate.value || create.pending.value) return;
  createError.value = null;
  const scopes = form.value.mode === 'per_app'
    ? Object.fromEntries(Object.entries(form.value.scopes).filter(([, kinds]) => kinds.length > 0))
    : {};
  try {
    const answer = await create.run({ ...form.value, name: form.value.name.trim(), rate_per_minute: Number(rateText.value), scopes });
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
    <InlineFeedback
      v-if="data && !available"
      tone="info"
      data-testid="api-keys-unavailable"
      :heading="t('base.apiKeys.unavailableHeading')"
    >
      {{ t('base.apiKeys.unavailable') }}
    </InlineFeedback>
    <template v-else>
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
    </template>

    <FormModal
      v-model:open="creating"
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
        <fieldset class="api-key-modes">
          <legend>{{ t('base.apiKeys.form.mode') }}</legend>
          <div
            role="radiogroup"
            class="api-key-modes__options"
          >
            <button
              v-for="mode in MODES"
              :key="mode"
              type="button"
              role="radio"
              class="api-key-mode"
              :class="{ 'api-key-mode--on': form.mode === mode }"
              :aria-checked="form.mode === mode"
              :data-testid="`api-key-form-mode-${mode}`"
              @click="form = { ...form, mode }"
            >
              {{ t(`base.apiKeys.modes.${mode}`) }}
            </button>
          </div>
          <p class="api-keys-hint">
            {{ form.mode === 'per_app' ? t('base.apiKeys.form.perAppHint') : t('base.apiKeys.form.generalHint') }}
          </p>
        </fieldset>
        <div
          v-if="form.mode === 'per_app'"
          class="api-key-apps"
          data-testid="api-key-form-apps"
        >
          <p
            v-if="apps.length === 0"
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
                  v-for="kind in KINDS"
                  :key="kind"
                  scope="col"
                >
                  {{ t(`base.apiKeys.kinds.${kind}`) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="app in apps"
                :key="app.id"
              >
                <th scope="row">
                  {{ app.name }}
                </th>
                <td
                  v-for="kind in KINDS"
                  :key="kind"
                >
                  <ion-checkbox
                    v-if="app[kind]"
                    :data-testid="`api-key-form-${app.id}-${kind}`"
                    :checked="ticked(app.id, kind)"
                    :aria-label="`${app.name} · ${t(`base.apiKeys.kinds.${kind}`)}`"
                    @ion-change="tick(app.id, kind, Boolean($event.detail.checked))"
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
  </section>
</template>

<style scoped>
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
.api-keys-hint {
  flex: 1 1 20rem;
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
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

.api-key-modes {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  border: 0;
}

.api-key-modes legend {
  margin-bottom: 6px;
  font-weight: 600;
}

.api-key-modes__options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.api-key-mode {
  padding: 6px 12px;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  border-radius: 999px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.api-key-mode--on {
  border-color: var(--ion-color-primary);
  background: color-mix(in oklab, var(--ion-color-primary) 12%, transparent);
  color: var(--ion-color-primary);
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
  width: 6rem;
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
