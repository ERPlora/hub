<script setup lang="ts">
// The body of «Channel settings» (WHATSAPP_INBOX-F01, F02, F13, F27…F31), mounted only for whoever
// configures. The number lives in erplora.com (the WhatsApp Business account and Meta's permission): «Your
// number» shows what it reports — connected with the number and the name, not connected or to reconnect — and
// connects, reconnects or disconnects it through erplora.com (NumberConnection); «This month» — messages sent against the plan's,
// the cap when reached, or no limit —; «Meta templates» — the live `whatsapp_inbox.template.list` with
// Name, Language, Category, Status in Meta (Meta's reason, and where it is on its way to Meta) and Text;
// «Add template» and a row open the form (F29, F30), Delete asks first (F31), «Send to Meta again» hands
// over again what did not get there.
import {
  ConfirmDialog,
  type DataTableAction,
  type DataTableColumn,
  DataTable,
  EmptyState,
  InlineFeedback,
  UsageMeter,
} from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { computed, ref } from 'vue';

import NumberConnection from './NumberConnection.vue';
import TemplateFormModal from './TemplateFormModal.vue';

import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { TemplateListIn, TemplateOut } from '../operations';

const t = useT();
const { data: channel, error: channelError } = useLive('whatsapp_inbox.channel.get', {});

// The templates list takes a search and a page (sorted by name on the server).
const table = useServerTable({ sort: 'name' });
const { data: templates, status, refresh } = useLiveList(
  'whatsapp_inbox.template.list',
  () => (table.query.value.search ? { search: table.query.value.search } : {}) as TemplateListIn,
  () => table.windows.value,
);
table.followResult(templates);

const columns = computed<DataTableColumn<TemplateOut>[]>(() => [
  { key: 'name', label: t('whatsapp_inbox.templates.columns.name'), priority: 'high' },
  { key: 'language', label: t('whatsapp_inbox.templates.columns.language') },
  { key: 'category', label: t('whatsapp_inbox.templates.columns.category'), format: (value) => t(`whatsapp_inbox.templates.categories.${String(value)}`) },
  { key: 'status', label: t('whatsapp_inbox.templates.columns.status'), format: (value, row) => statusText(String(value), row) },
  { key: 'body', label: t('whatsapp_inbox.templates.columns.body'), priority: 'low' },
]);

/** Meta's verdict and its reason, and where the template is on its way to Meta (or why it did not get there). */
function statusText(status: string, row: TemplateOut): string {
  if (row.deleting) {
    const deleting = t('whatsapp_inbox.templates.state.deleting');
    return row.submit_error ? `${deleting} · ${row.submit_error}` : deleting;
  }
  const parts = [t(`whatsapp_inbox.templates.statuses.${status}`)];
  if (row.rejected_reason) parts.push(t('whatsapp_inbox.templates.rejectedReason', { reason: row.rejected_reason }));
  if (row.submit_state === 'failed') parts.push(t('whatsapp_inbox.templates.state.notAccepted', { reason: row.submit_error }));
  else if (row.submit_state === 'sending' && row.submit_error)
    parts.push(row.status === 'DRAFT' ? row.submit_error : t('whatsapp_inbox.templates.state.notSent', { reason: row.submit_error }));
  else if (row.submit_state === 'queued' || row.submit_state === 'sending') parts.push(t('whatsapp_inbox.templates.state.sending'));
  return parts.join(' · ');
}

/** It did not reach Meta (refused, or no answer): it can be handed over again. */
const retryable = (row: TemplateOut): boolean =>
  row.deleting ? !!row.submit_error : row.submit_state === 'failed' || (row.submit_state === 'sending' && !!row.submit_error_code);

const actions = computed<DataTableAction<TemplateOut>[]>(() => [
  { id: 'edit', label: t('whatsapp_inbox.templates.actions.edit'), icon: 'create-outline', hidden: (row) => !row.editable || row.deleting },
  { id: 'retry', label: t('whatsapp_inbox.templates.actions.retry'), icon: 'refresh-outline', hidden: (row) => !retryable(row) },
  { id: 'delete', label: t('whatsapp_inbox.templates.actions.delete'), icon: 'trash-outline', color: 'danger', hidden: (row) => row.deleting },
]);

const editing = ref<TemplateOut | null>(null);
const formOpen = ref(false);
function openForm(row: TemplateOut | null): void {
  editing.value = row;
  formOpen.value = true;
}

const remove = useCommand('whatsapp_inbox.template.delete');
const retry = useCommand('whatsapp_inbox.template.retry');
const deleting = ref<TemplateOut | null>(null);
const deleteOpen = ref(false);

async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await remove.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

function onAction({ actionId, row }: { actionId: string; row: TemplateOut }): void {
  if (actionId === 'edit') openForm(row);
  if (actionId === 'retry') void retry.run({ id: row.id }).catch(() => undefined);
  if (actionId === 'delete') {
    remove.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
  }
}
</script>

<template>
  <div class="wa-settings">
    <InlineFeedback
      v-if="channelError"
      tone="danger"
      data-testid="whatsapp-inbox-settings-error"
      :heading="t('whatsapp_inbox.settings.loadError')"
    >
      {{ channelError.message }}
    </InlineFeedback>
    <section
      class="wa-settings__block"
      data-testid="whatsapp-inbox-settings-number"
    >
      <h2>{{ $t('whatsapp_inbox.settings.number') }}</h2>
      <NumberConnection
        v-if="channel"
        :channel="channel"
      />
      <p
        v-else
        class="wa-settings__hint"
      >
        {{ $t('whatsapp_inbox.loading') }}
      </p>
    </section>

    <section
      v-if="channel"
      class="wa-settings__block"
      data-testid="whatsapp-inbox-settings-month"
    >
      <h2>{{ $t('whatsapp_inbox.settings.month') }}</h2>
      <template v-if="channel.monthly_limit > 0">
        <UsageMeter
          :label="t('whatsapp_inbox.settings.sent')"
          :value="channel.monthly_usage"
          :max="channel.monthly_limit"
          :hint="t('whatsapp_inbox.settings.usage', { used: channel.monthly_usage, limit: channel.monthly_limit })"
        />
        <p
          v-if="channel.cap_reached"
          class="wa-settings__warning"
        >
          {{ $t('whatsapp_inbox.settings.capReached') }}
        </p>
      </template>
      <p v-else>
        {{ $t('whatsapp_inbox.settings.noLimit', { used: channel.monthly_usage }) }}
      </p>
    </section>

    <section class="wa-settings__block wa-settings__block--templates">
      <h2 data-testid="whatsapp-inbox-templates-title">
        {{ $t('whatsapp_inbox.settings.templatesTitle') }}
      </h2>
      <DataTable
        v-model:search="table.search.value"
        testid="whatsapp-inbox-templates"
        server-side
        searchable
        :rows="templates?.rows ?? []"
        :total="templates?.total ?? 0"
        :page="table.page.value"
        :page-size="table.pageSize.value"
        :views="['table', 'cards']"
        :card-title="(row: TemplateOut) => row.name"
        :entity-label="{ one: $t('whatsapp_inbox.templates.entity.one'), many: $t('whatsapp_inbox.templates.entity.many') }"
        :loading="status === 'loading'"
        :error="status === 'error' ? $t('whatsapp_inbox.templates.loadError') : undefined"
        :search-placeholder="$t('whatsapp_inbox.templates.search')"
        :labels="{ add: $t('whatsapp_inbox.templates.add'), loadError: $t('whatsapp_inbox.templates.loadError'), retry: $t('whatsapp_inbox.live.retry') }"
        :columns="columns"
        addable
        row-clickable
        :actions="actions"
        @page-change="table.goToPage"
        @load-more="table.loadMore"
        @page-size-change="table.setPageSize"
        @retry="refresh()"
        @add="openForm(null)"
        @row-click="(row: TemplateOut) => row.editable && !row.deleting && openForm(row)"
        @action="onAction"
      >
        <template #empty>
          <EmptyState
            data-testid="whatsapp-inbox-templates-empty"
            icon="file-tray-outline"
            :heading="table.filtered.value ? $t('whatsapp_inbox.noResults') : $t('whatsapp_inbox.templates.empty')"
            :message="table.filtered.value ? $t('whatsapp_inbox.noResultsMessage') : $t('whatsapp_inbox.templates.emptyHint')"
          />
        </template>
      </DataTable>
      <InlineFeedback
        v-if="retry.error.value"
        tone="danger"
        data-testid="whatsapp-inbox-templates-retry-error"
        :heading="retry.error.value.message"
      />
    </section>
    <TemplateFormModal
      v-model:open="formOpen"
      :template="editing"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="whatsapp-inbox-template-delete"
      tone="danger"
      :title="t('whatsapp_inbox.templates.delete.title')"
      :message="deleting ? t('whatsapp_inbox.templates.delete.message', { name: deleting.name, language: deleting.language }) : ''"
      :consequences="[t('whatsapp_inbox.templates.delete.impact')]"
      :confirm-label="t('whatsapp_inbox.templates.delete.confirm')"
      :cancel-label="t('whatsapp_inbox.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </div>
</template>

<style scoped>
.wa-settings {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.wa-settings__block {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 12px;
  padding: 1rem;
}
.wa-settings__block h2 {
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
}
.wa-settings__hint {
  color: var(--ion-color-medium-shade);
  margin: 0 0 0.5rem;
}
.wa-settings__warning {
  color: var(--ion-color-warning-shade);
  font-weight: 600;
}
</style>
