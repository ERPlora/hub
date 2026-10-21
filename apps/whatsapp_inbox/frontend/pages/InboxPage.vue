<script setup lang="ts">
// WhatsApp inbox → Inbox (WHATSAPP_INBOX-F03, F05, F09, F10, F13), the product's «Bandeja de entrada»: the
// live `whatsapp_inbox.conversation.list` in a server-side DataTable — Contact, Phone, Status, Assigned
// to, Unread and Last message (the time if today, «Yesterday» or the date, on the business clock) —,
// «Filter contact or phone…» (a number typed any way), column filters by status, assignment and unread,
// 50 a page, the latest activity first. «Open» (or the row) opens the conversation in a panel above the
// list, kept in the address (`?conversation=`). Above it: «Reconnecting…», the number not connected or to
// reconnect («Go to Settings», where it is connected, for whoever configures), the month's messages spent, a number
// erased.
import {
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  DataTable,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import ConversationPanel from '../components/ConversationPanel.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatMessageTime } from '../lib/format';
import { kindLabel } from '../lib/thread';
import type { ConversationListIn, ConversationOut, ConversationStatus } from '../operations';
import { inboxTabs } from '../tabs';

const STATUSES: readonly ConversationStatus[] = ['open', 'pending', 'closed'];

const session = useSession();
const canConfigure = computed(() => session.can('whatsapp_inbox.configure'));
/** Where the number is connected, reconnected or disconnected (WHATSAPP_INBOX-F01, F02). */
const SETTINGS = '/whatsapp_inbox/settings';
const t = useT();
const locale = useLocale();
const route = useRoute();
const router = useRouter();

const table = useServerTable({ sort: 'last_message_at', dir: 'desc' });
const filters = ref<DataTableFilters>({});

/** The table's filters as the query takes them: «unread» is a yes/no. */
const query = computed<Partial<ConversationListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.status ? { status: f.status as ConversationStatus } : {}),
    ...(f.assigned ? { assigned: f.assigned } : {}),
    ...(f.unread ? { unread: f.unread === 'true' } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'whatsapp_inbox.conversation.list',
  () => ({ ...query.value, ...table.query.value }) as ConversationListIn,
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const { data: channel } = useLive('whatsapp_inbox.channel.get', {});

// The open conversation lives in the address, so a link (the bell, another app) opens it.
const openId = computed(() => (typeof route.query.conversation === 'string' ? route.query.conversation : ''));
const erased = ref(false);

function open(row: ConversationOut): void {
  erased.value = false;
  void router.replace({ query: { ...route.query, conversation: row.id } });
}

function close(): void {
  const rest = { ...route.query };
  delete rest.conversation;
  void router.replace({ query: rest });
}

function onErased(): void {
  close();
  erased.value = true;
}

watch(openId, (id) => {
  if (id) erased.value = false;
});

function when(value: unknown): string {
  return formatMessageTime(value as string | null, { locale: locale.value, yesterday: t('whatsapp_inbox.yesterday') });
}

/** The last message as the list shows it: its text; a photo, a file or a location named by its type. */
function previewOf(row: ConversationOut): string {
  const kind = row.last_message_kind;
  if (!kind || kind === 'text' || kind === 'template') return row.last_message_preview;
  const label = kindLabel(kind, t);
  return row.last_message_preview ? `${label} · ${row.last_message_preview}` : label;
}

const actions = computed<DataTableAction<ConversationOut>[]>(() => [
  { id: 'open', label: t('whatsapp_inbox.inbox.open'), icon: 'ion:chatbubbles-outline', showLabel: true, pinned: true, color: 'primary' },
]);

const columns = computed<DataTableColumn<ConversationOut>[]>(() => [
  { key: 'contact', label: t('whatsapp_inbox.inbox.columns.contact'), sortable: true, priority: 'high', cell: 'contact', format: (_, row) => row.display_name },
  { key: 'phone', label: t('whatsapp_inbox.inbox.columns.phone'), sortable: true },
  {
    key: 'status',
    label: t('whatsapp_inbox.inbox.columns.status'),
    sortable: true,
    format: (value) => t(`whatsapp_inbox.status.${String(value)}`),
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`whatsapp_inbox.status.${value}`) })) },
  },
  {
    key: 'assigned_to_name',
    label: t('whatsapp_inbox.inbox.columns.assigned'),
    priority: 'low',
    format: (value) => (value ? String(value) : '—'),
    filter: {
      type: 'select',
      key: 'assigned',
      options: [
        { value: 'me', label: t('whatsapp_inbox.inbox.filters.me') },
        { value: 'none', label: t('whatsapp_inbox.inbox.filters.none') },
      ],
    },
  },
  {
    key: 'unread_count',
    label: t('whatsapp_inbox.inbox.columns.unread'),
    sortable: true,
    align: 'right',
    cell: 'unread',
    format: (value) => (Number(value) > 0 ? String(value) : '—'),
    filter: {
      type: 'select',
      key: 'unread',
      options: [
        { value: 'true', label: t('whatsapp_inbox.inbox.filters.withUnread') },
        { value: 'false', label: t('whatsapp_inbox.inbox.filters.allRead') },
      ],
    },
  },
  { key: 'last_message_at', label: t('whatsapp_inbox.inbox.columns.lastMessage'), sortable: true, format: (value) => when(value) },
]);
</script>

<template>
  <AppPage
    :title="$t('whatsapp_inbox.title')"
    content-layout="fill"
    :tabs="inboxTabs($t)"
    :tabs-label="$t('whatsapp_inbox.tabs.label')"
  >
    <div class="wa-inbox">
      <PageNotices
        testid="whatsapp-inbox"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="channel?.status === 'not_connected'"
        tone="info"
        data-testid="whatsapp-inbox-not-connected"
      >
        {{ $t('whatsapp_inbox.inbox.notConnected') }}
        <template
          v-if="canConfigure"
          #actions
        >
          <a
            class="wa-inbox__link"
            data-testid="whatsapp-inbox-go-to-settings"
            :href="SETTINGS"
            @click.prevent="router.push(SETTINGS)"
          >{{ $t('whatsapp_inbox.inbox.goToSettings') }}</a>
        </template>
      </InlineFeedback>
      <InlineFeedback
        v-else-if="channel?.status === 'reconnect_needed'"
        tone="warning"
        data-testid="whatsapp-inbox-reconnect"
      >
        {{ $t('whatsapp_inbox.inbox.reconnectNeeded') }}
        <template
          v-if="canConfigure"
          #actions
        >
          <a
            class="wa-inbox__link"
            data-testid="whatsapp-inbox-go-to-settings"
            :href="SETTINGS"
            @click.prevent="router.push(SETTINGS)"
          >{{ $t('whatsapp_inbox.inbox.goToSettings') }}</a>
        </template>
      </InlineFeedback>
      <InlineFeedback
        v-if="channel?.cap_reached"
        tone="warning"
        data-testid="whatsapp-inbox-cap-reached"
      >
        {{ $t('whatsapp_inbox.inbox.capReached') }}
      </InlineFeedback>
      <InlineFeedback
        v-if="erased"
        tone="success"
        dismissible
        data-testid="whatsapp-inbox-erased"
        @dismiss="erased = false"
      >
        {{ $t('whatsapp_inbox.inbox.erased') }}
      </InlineFeedback>
      <ConversationPanel
        v-if="openId && !blocked"
        :conversation-id="openId"
        @close="close"
        @erased="onErased"
      />
    </div>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="whatsapp-inbox"
      fill
      server-side
      searchable
      filterable
      row-clickable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: ConversationOut) => row.display_name"
      card-title-column="contact"
      :entity-label="{ one: $t('whatsapp_inbox.inbox.entity.one'), many: $t('whatsapp_inbox.inbox.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' ? $t('whatsapp_inbox.inbox.loadError') : undefined"
      :search-placeholder="$t('whatsapp_inbox.inbox.search')"
      :labels="{ loadError: $t('whatsapp_inbox.inbox.loadError'), retry: $t('whatsapp_inbox.live.retry') }"
      :actions="actions"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="open"
      @action="(event) => event.actionId === 'open' && open(event.row)"
      @retry="refresh()"
    >
      <template #contact="{ row }">
        <span
          class="wa-inbox__contact"
          :class="{ 'wa-inbox__contact--unread': row.unread_count > 0 }"
        >
          {{ row.display_name }}
          <small
            v-if="previewOf(row)"
            class="wa-inbox__preview"
            data-testid="whatsapp-inbox-preview"
          >{{ previewOf(row) }}</small>
        </span>
      </template>
      <template #unread="{ row }">
        <span
          class="wa-inbox__unread"
          :class="{ 'wa-inbox__unread--on': row.unread_count > 0 }"
          data-testid="whatsapp-inbox-unread"
        >{{ row.unread_count > 0 ? row.unread_count : '—' }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="whatsapp-inbox-empty"
          icon="chatbubbles-outline"
          :heading="table.filtered.value ? $t('whatsapp_inbox.noResults') : $t('whatsapp_inbox.inbox.empty')"
          :message="table.filtered.value ? $t('whatsapp_inbox.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
  </AppPage>
</template>

<style scoped>
/* The notices and the open conversation, above the list. The DataTable is a direct child of AppPage's
   `.page-fill` stack (polish.css), never inside a nested one: on a phone a nested stack let the list's
   `min-height: 100%` grow by the notices' height and pushed «No conversations.» under the tab bar. */
.wa-inbox {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.wa-inbox:not(:empty) {
  margin-bottom: 0.75rem;
}
.wa-inbox__link {
  color: var(--ion-color-primary);
  font-weight: 600;
}
.wa-inbox__contact {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.wa-inbox__contact--unread {
  font-weight: 700;
}
.wa-inbox__unread--on {
  font-weight: 700;
  color: var(--ion-color-primary);
}
.wa-inbox__preview {
  font-weight: 400;
  color: var(--ion-color-medium-shade);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
