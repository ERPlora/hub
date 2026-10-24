<script setup lang="ts">
// The open conversation, in a panel above the inbox as the product's «Abrir» opened it
// (WHATSAPP_INBOX-F05, F07, F10, F35, F36, F37): who it is and their number, its status and «Close»; the
// customer card it is joined to («View card», «Unlink») or Customers' own search to join one and
// «Create card»; «Assigned to» (the team, for whoever may assign anybody) and «Assign to me», which never
// takes it from somebody else; the status buttons Open / Pending / Closed; the live thread with its notes
// («View earlier» follows 50 more); the composer; and «Erase this number's data» for owner and admin,
// asked first naming the number. Opening it leaves it read, and so does a message arriving while open.
import { Combo, type ComboOption, InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { useLiveList } from '../composables/useLiveList';
import { useT } from '../composables/useT';
import type { ChannelOut, ConversationStatus, NoteOut } from '../operations';
import MessageComposer from './MessageComposer.vue';
import ThreadView from './ThreadView.vue';

const PAGE = 50;
const STATUS_TONES = { open: 'success', pending: 'warning', closed: 'neutral' } as const;

const props = withDefaults(
  defineProps<{
    conversationId: string;
    /** The business's number and its month (the inbox's own `channel.get`): the box says why nothing is sent. */
    channel?: ChannelOut | null;
  }>(),
  { channel: null },
);
const emit = defineEmits<{ close: []; erased: [] }>();

const t = useT();
const session = useSession();
const client = useLiveClient();
const { confirm } = useConfirm();
const canAssign = computed(() => session.can('whatsapp_inbox.assign'));
const canErase = computed(() => session.can('whatsapp_inbox.erase'));

const { data: conversation, error: detailError } = useLive('whatsapp_inbox.conversation.detail', () => ({ id: props.conversationId }));

// The thread: the newest 50 first, «View earlier» follows 50 more (each window its own subscription).
const pages = ref(1);
watch(
  () => props.conversationId,
  () => (pages.value = 1),
);
const windows = computed(() => Array.from({ length: pages.value }, (_, i) => ({ limit: PAGE, offset: i * PAGE })));
const { data: messages, status: messagesStatus, error: messagesError } = useLiveList(
  'whatsapp_inbox.message.list',
  () => ({ id: props.conversationId }),
  () => windows.value,
);
const { data: notes } = useLive('whatsapp_inbox.note.list', () => ({ id: props.conversationId, limit: 100 }));
const hasMore = computed(() => (messages.value?.total ?? 0) > pages.value * PAGE);

const markRead = useCommand('whatsapp_inbox.conversation.mark_read');
const assign = useCommand('whatsapp_inbox.conversation.assign');
const setStatus = useCommand('whatsapp_inbox.conversation.set_status');
const link = useCommand('whatsapp_inbox.conversation.link_customer');
const erase = useCommand('whatsapp_inbox.conversation.erase');
const deleteNote = useCommand('whatsapp_inbox.note.delete');
const retry = useCommand('whatsapp_inbox.message.retry');

/** The last refusal of an action of this panel, said under its actions. */
const actionError = ref<ApiError | null>(null);

async function act(job: () => Promise<unknown>): Promise<boolean> {
  actionError.value = null;
  try {
    await job();
    return true;
  } catch (error) {
    actionError.value = error as ApiError;
    return false;
  }
}

// A conversation on screen is a conversation read, also when a message arrives while it is open.
watch(
  () => conversation.value?.unread_count,
  (unread) => {
    if (unread && !markRead.pending.value) markRead.run({ id: props.conversationId }).catch(() => undefined);
  },
  { immediate: true },
);
watch(
  () => props.conversationId,
  () => (actionError.value = null),
);

const me = computed(() => session.user.value?.id ?? '');
const assignedToMe = computed(() => conversation.value?.assigned_to_id != null && String(conversation.value.assigned_to_id) === me.value);
const canUnassign = computed(() => !!conversation.value?.assigned_to_id && (canAssign.value || assignedToMe.value));
const assignee = computed<ComboOption | null>(() =>
  conversation.value?.assigned_to_id != null ? { id: String(conversation.value.assigned_to_id), label: conversation.value.assigned_to_name } : null,
);

async function searchTeam(query: string): Promise<ComboOption[]> {
  const page = await client.api.call('whatsapp_inbox.agent.list', { ...(query ? { search: query } : {}), limit: 20 });
  return page.rows.map((person) => ({ id: String(person.id), label: person.name }));
}

function pickAssignee(option: ComboOption | null): void {
  void act(() =>
    option ? assign.run({ id: props.conversationId, assignee_id: Number(option.id) }) : assign.run({ id: props.conversationId, unassign: true }),
  );
}

function chooseStatus(value: unknown): void {
  const status = String(value ?? '') as ConversationStatus;
  if (!['open', 'pending', 'closed'].includes(status) || status === conversation.value?.status) return;
  void act(() => setStatus.run({ id: props.conversationId, status }));
}

function linkCard(card: CustomerSnapshot | null): void {
  if (card) void act(() => link.run({ id: props.conversationId, customer_id: card.customer_id }));
}

async function eraseNumber(): Promise<void> {
  const phone = conversation.value?.phone || conversation.value?.display_name || '—';
  const yes = await confirm({
    title: t('whatsapp_inbox.conversation.eraseTitle'),
    message: t('whatsapp_inbox.conversation.eraseMessage', { phone }),
    tone: 'danger',
    confirmLabel: t('whatsapp_inbox.conversation.eraseConfirm'),
    cancelLabel: t('whatsapp_inbox.cancel'),
  });
  if (!yes) return;
  if (await act(() => erase.run({ id: props.conversationId }))) emit('erased');
}

async function removeNote(note: NoteOut): Promise<void> {
  const yes = await confirm({
    title: t('whatsapp_inbox.thread.deleteNoteTitle'),
    message: note.text,
    tone: 'danger',
    confirmLabel: t('whatsapp_inbox.thread.deleteNote'),
    cancelLabel: t('whatsapp_inbox.cancel'),
  });
  if (yes) await act(() => deleteNote.run({ id: note.id }));
}
</script>

<template>
  <section
    class="wa-detail"
    data-testid="whatsapp-inbox-detail"
  >
    <InlineFeedback
      v-if="detailError"
      tone="danger"
      data-testid="whatsapp-inbox-detail-error"
      :heading="t('whatsapp_inbox.conversation.loadError')"
    >
      {{ detailError.message }}
    </InlineFeedback>
    <header class="wa-detail__head">
      <h3 data-testid="whatsapp-inbox-detail-name">
        {{ conversation?.display_name ?? '' }}
      </h3>
      <span
        class="wa-detail__phone"
        data-testid="whatsapp-inbox-detail-phone"
      >{{ conversation?.phone ?? '' }}</span>
      <StatusPill
        v-if="conversation"
        size="sm"
        data-testid="whatsapp-inbox-detail-status"
        :tone="STATUS_TONES[conversation.status]"
        :label="t(`whatsapp_inbox.status.${conversation.status}`)"
      />
      <span class="wa-detail__spacer" />
      <ion-button
        size="small"
        fill="clear"
        data-testid="whatsapp-inbox-detail-close"
        @click="emit('close')"
      >
        {{ $t('whatsapp_inbox.conversation.close') }}
      </ion-button>
    </header>

    <template v-if="conversation">
      <div class="wa-detail__row">
        <span class="wa-detail__label">{{ $t('whatsapp_inbox.conversation.customer') }}</span>
        <template v-if="conversation.customer_id">
          <strong data-testid="whatsapp-inbox-detail-customer">{{ conversation.customer_name }}</strong>
          <RouterLink
            class="wa-detail__link"
            data-testid="whatsapp-inbox-detail-view-card"
            :to="`/customer/customers/${conversation.customer_id}`"
          >
            {{ $t('whatsapp_inbox.conversation.viewCard') }}
          </RouterLink>
          <ion-button
            size="small"
            fill="clear"
            data-testid="whatsapp-inbox-detail-unlink"
            :disabled="link.pending.value"
            @click="act(() => link.run({ id: conversationId, unlink: true }))"
          >
            {{ $t('whatsapp_inbox.conversation.unlink') }}
          </ion-button>
        </template>
        <template v-else>
          <span
            class="wa-detail__quiet"
            data-testid="whatsapp-inbox-detail-no-customer"
          >{{ $t('whatsapp_inbox.conversation.noCustomer') }}</span>
          <CustomerSearch
            :model-value="null"
            @update:model-value="linkCard"
          />
          <ion-button
            size="small"
            fill="outline"
            data-testid="whatsapp-inbox-detail-create-card"
            :disabled="link.pending.value"
            @click="act(() => link.run({ id: conversationId, create: true }))"
          >
            {{ $t('whatsapp_inbox.conversation.createCard') }}
          </ion-button>
        </template>
      </div>

      <div class="wa-detail__row">
        <span class="wa-detail__label">{{ $t('whatsapp_inbox.conversation.assignedTo') }}</span>
        <Combo
          v-if="canAssign"
          class="wa-detail__assignee"
          testid="whatsapp-inbox-detail-assignee"
          :model-value="assignee"
          :search="searchTeam"
          :label="t('whatsapp_inbox.conversation.assignedTo')"
          :placeholder="t('whatsapp_inbox.conversation.assignPlaceholder')"
          :empty-label="t('whatsapp_inbox.conversation.noPeople')"
          :clearable="false"
          @update:model-value="pickAssignee"
        />
        <strong
          v-else
          data-testid="whatsapp-inbox-detail-assigned"
        >{{ conversation.assigned_to_name || $t('whatsapp_inbox.conversation.nobody') }}</strong>
        <ion-button
          v-if="!assignedToMe"
          size="small"
          fill="outline"
          data-testid="whatsapp-inbox-detail-assign-me"
          :disabled="assign.pending.value"
          @click="act(() => assign.run({ id: conversationId, assignee: 'me', only_if_unassigned: true }))"
        >
          {{ $t('whatsapp_inbox.conversation.assignToMe') }}
        </ion-button>
        <ion-button
          v-if="canUnassign"
          size="small"
          fill="clear"
          data-testid="whatsapp-inbox-detail-unassign"
          :disabled="assign.pending.value"
          @click="act(() => assign.run({ id: conversationId, unassign: true }))"
        >
          {{ $t('whatsapp_inbox.conversation.unassign') }}
        </ion-button>
      </div>

      <div class="wa-detail__row">
        <span class="wa-detail__label">{{ $t('whatsapp_inbox.conversation.statusLabel') }}</span>
        <ion-segment
          class="wa-detail__status"
          mode="md"
          :value="conversation.status"
          data-testid="whatsapp-inbox-detail-status-choice"
          @ion-change="chooseStatus($event.detail.value)"
        >
          <ion-segment-button
            v-for="status in (['open', 'pending', 'closed'] as const)"
            :key="status"
            :value="status"
            :data-testid="`whatsapp-inbox-detail-status-${status}`"
          >
            {{ $t(`whatsapp_inbox.status.${status}`) }}
          </ion-segment-button>
        </ion-segment>
      </div>

      <InlineFeedback
        v-if="actionError"
        tone="danger"
        dismissible
        data-testid="whatsapp-inbox-action-error"
        :heading="t('whatsapp_inbox.conversation.actionError')"
        @dismiss="actionError = null"
      >
        {{ actionError.message }}
      </InlineFeedback>

      <ThreadView
        :messages="messages?.rows ?? []"
        :notes="notes?.rows ?? []"
        :loading="messagesStatus === 'loading'"
        :error="messagesError && !detailError ? messagesError.message : undefined"
        :has-more="hasMore"
        :reconnect-needed="props.channel?.status === 'reconnect_needed'"
        @earlier="pages += 1"
        @delete-note="removeNote"
        @retry="(message) => act(() => retry.run({ id: message.id }))"
      />
      <MessageComposer
        :conversation="conversation"
        :channel="props.channel"
      />

      <div
        v-if="canErase"
        class="wa-detail__danger"
      >
        <ion-button
          size="small"
          fill="clear"
          class="wa-detail__erase"
          data-testid="whatsapp-inbox-detail-erase"
          :disabled="erase.pending.value"
          @click="eraseNumber"
        >
          {{ $t('whatsapp_inbox.conversation.erase') }}
        </ion-button>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* The thread lives ABOVE the list (the product's panel), in a card of its own. */
.wa-detail {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 12px;
  padding: 1rem;
  margin: 0 0 1rem;
  background: var(--ion-card-background, var(--ion-background-color));
}
.wa-detail__head {
  display: flex;
  gap: 0.6rem;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.wa-detail__head h3 {
  margin: 0;
  font-size: 1.05rem;
}
.wa-detail__phone,
.wa-detail__quiet {
  color: var(--ion-color-medium-shade);
}
.wa-detail__spacer {
  flex: 1;
}
.wa-detail__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.35rem 0;
}
.wa-detail__label {
  font-size: 0.85rem;
  font-weight: 600;
  min-width: 7rem;
}
.wa-detail__assignee {
  min-width: 14rem;
  flex: 0 1 18rem;
}
.wa-detail__status {
  max-width: 24rem;
}
.wa-detail__link {
  color: var(--ion-color-primary);
  font-weight: 600;
}
.wa-detail__danger {
  margin-top: 0.75rem;
}
.wa-detail__erase {
  --color: var(--ion-color-danger);
}
/* 44px minimum touch target: this screen is used one-handed, at a counter. */
ion-button {
  --min-height: 44px;
}
</style>
