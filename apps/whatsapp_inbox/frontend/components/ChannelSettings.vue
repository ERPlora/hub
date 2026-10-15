<script setup lang="ts">
// The body of «Channel settings» (WHATSAPP_INBOX-F01, F02, F13, F27, F28), mounted only for whoever
// configures. The number and the templates are erplora.com's (the WhatsApp Business account lives
// there): this shows what it reported and leads there to change it. «Your number» — connected with the
// number and the name, not connected or to reconnect —, «Manage in erplora.com»; «This month» — messages
// sent against the plan's, the cap when reached, or no limit —; «Meta templates» — the live
// `whatsapp_inbox.template.list` with Name, Language, Category, Status in Meta (and Meta's reason) and Text.
import {
  type DataTableColumn,
  DataTable,
  EmptyState,
  InlineFeedback,
  StatusPill,
  UsageMeter,
} from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { TemplateListIn, TemplateOut } from '../operations';

const NUMBER_TONES = { connected: 'success', not_connected: 'neutral', reconnect_needed: 'warning' } as const;
const NUMBER_LABELS = { connected: 'connected', not_connected: 'notConnected', reconnect_needed: 'reconnectNeeded' } as const;

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
  {
    key: 'status',
    label: t('whatsapp_inbox.templates.columns.status'),
    format: (value, row) => {
      const label = t(`whatsapp_inbox.templates.statuses.${String(value)}`);
      return row.rejected_reason ? `${label} · ${t('whatsapp_inbox.templates.rejectedReason', { reason: row.rejected_reason })}` : label;
    },
  },
  { key: 'body', label: t('whatsapp_inbox.templates.columns.body'), priority: 'low' },
]);
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
      <template v-if="channel">
        <p class="wa-settings__line">
          <StatusPill
            size="sm"
            :tone="NUMBER_TONES[channel.status]"
            :label="t(`whatsapp_inbox.settings.${NUMBER_LABELS[channel.status]}`)"
          />
          <strong v-if="channel.phone_number">{{ channel.phone_number }}</strong>
          <span v-if="channel.display_name">{{ channel.display_name }}</span>
        </p>
        <p
          v-if="channel.status === 'not_connected'"
          class="wa-settings__hint"
        >
          {{ $t('whatsapp_inbox.settings.notConnectedHint') }}
        </p>
        <p
          v-else-if="channel.status === 'reconnect_needed'"
          class="wa-settings__hint"
        >
          {{ $t('whatsapp_inbox.settings.reconnectHint') }}
        </p>
        <a
          v-if="channel.manage_url"
          class="wa-settings__link"
          data-testid="whatsapp-inbox-settings-manage"
          :href="channel.manage_url"
          target="_blank"
          rel="noopener"
        >{{ $t('whatsapp_inbox.settings.manage') }}</a>
      </template>
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
          :label="t('whatsapp_inbox.settings.month')"
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
        :labels="{ loadError: $t('whatsapp_inbox.templates.loadError'), retry: $t('whatsapp_inbox.live.retry') }"
        :columns="columns"
        @page-change="table.goToPage"
        @load-more="table.loadMore"
        @page-size-change="table.setPageSize"
        @retry="refresh()"
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
    </section>
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
.wa-settings__line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0 0 0.5rem;
}
.wa-settings__hint {
  color: var(--ion-color-medium-shade);
  margin: 0 0 0.5rem;
}
.wa-settings__warning {
  color: var(--ion-color-warning-shade);
  font-weight: 600;
}
.wa-settings__link {
  color: var(--ion-color-primary);
  font-weight: 600;
}
</style>
