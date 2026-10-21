<script setup lang="ts">
// The thread of a conversation (WHATSAPP_INBOX-F05, F06, F08, F34, F36), as the product's panel painted
// it: oldest first, the customer's messages on the left, the business's on the right with their
// delivery status (Sending…, Sent, Delivered, Read, Not delivered and Meta's reason; «Not sent» with
// «Retry» when erplora.com gave no final answer), the owner's replies from the phone marked «From the
// phone», a message without text nor attachment named by its type in the reader's language, reactions on
// the message they answer, and the team's internal notes in their own colour. An attachment is kept by
// erplora.com: it opens there in a new tab, over https only (the Hub's CSP paints no file of another
// origin; WORKBOOK F06). «View earlier» asks the page for the previous page; the page owns the data.
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed, nextTick, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatMessageTime, mediaKind, safeMediaUrl } from '../lib/format';
import { kindLabel, reactionsByMessage, timeline } from '../lib/thread';
import type { MessageOut, NoteOut } from '../operations';

const props = withDefaults(
  defineProps<{
    messages: readonly MessageOut[];
    notes: readonly NoteOut[];
    loading?: boolean;
    error?: string;
    hasMore?: boolean;
    /** «Now» for «today» and «yesterday»; the device's clock unless a test pins it. */
    now?: Date;
  }>(),
  { loading: false, error: undefined, hasMore: false, now: undefined },
);

const emit = defineEmits<{ earlier: []; deleteNote: [note: NoteOut]; retry: [message: MessageOut] }>();

const t = useT();
const locale = useLocale();
const items = computed(() => timeline(props.messages, props.notes));
const reactions = computed(() => reactionsByMessage(props.messages));
const log = ref<HTMLElement | null>(null);

function when(value: string): string {
  return formatMessageTime(value, { locale: locale.value, yesterday: t('whatsapp_inbox.yesterday'), withTime: true, now: props.now ?? new Date() });
}

/** Meta's type when there is nothing else to show (a location, a button reply). */
function bodiless(message: MessageOut): boolean {
  return !message.body && !mediaKind(message) && message.kind !== 'text' && message.kind !== 'template';
}

/** Handed to erplora.com and no final answer: «Not sent», to retry with the same key. */
function notSent(message: MessageOut): boolean {
  return message.status === 'sending' && !!message.error_code;
}

function statusLabel(message: MessageOut): string {
  return notSent(message) ? t('whatsapp_inbox.thread.messageStatus.notSent') : t(`whatsapp_inbox.thread.messageStatus.${message.status}`);
}

// The newest message is the one to read: keep the end of the thread in view when one arrives.
watch(
  () => items.value.at(-1)?.id,
  async () => {
    await nextTick();
    if (log.value) log.value.scrollTop = log.value.scrollHeight;
  },
);
</script>

<template>
  <section
    ref="log"
    class="wa-thread"
    role="log"
    aria-live="polite"
    :aria-label="$t('whatsapp_inbox.thread.label')"
    data-testid="whatsapp-inbox-thread"
  >
    <ion-button
      v-if="hasMore"
      class="wa-thread__earlier"
      size="small"
      fill="clear"
      data-testid="whatsapp-inbox-thread-earlier"
      @click="emit('earlier')"
    >
      {{ $t('whatsapp_inbox.thread.earlier') }}
    </ion-button>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="whatsapp-inbox-thread-error"
    >
      {{ error }}
    </InlineFeedback>
    <p
      v-if="loading && !items.length"
      class="wa-thread__quiet"
      data-testid="whatsapp-inbox-thread-loading"
    >
      {{ $t('whatsapp_inbox.loading') }}
    </p>
    <p
      v-else-if="!items.length && !error"
      class="wa-thread__quiet"
      data-testid="whatsapp-inbox-thread-empty"
    >
      {{ $t('whatsapp_inbox.thread.empty') }}
    </p>
    <template
      v-for="item in items"
      :key="`${item.type}-${item.id}`"
    >
      <article
        v-if="item.type === 'message'"
        class="wa-bubble"
        :class="`wa-bubble--${item.message.direction}`"
        :data-side="item.message.direction"
        data-testid="whatsapp-inbox-message"
      >
        <span
          v-if="item.message.kind === 'template'"
          class="wa-bubble__kind"
        >{{ $t('whatsapp_inbox.thread.template', { name: item.message.template_name }) }}</span>
        <div
          v-if="mediaKind(item.message)"
          class="wa-bubble__media"
          data-testid="whatsapp-inbox-message-media"
        >
          <span class="wa-bubble__kind">
            {{ $t(`whatsapp_inbox.thread.kinds.${mediaKind(item.message)}`) }}<template v-if="item.message.media_filename"> · {{ item.message.media_filename }}</template>
          </span>
          <a
            v-if="safeMediaUrl(item.message.media_url)"
            :href="safeMediaUrl(item.message.media_url) ?? undefined"
            target="_blank"
            rel="noopener noreferrer"
          >{{ $t('whatsapp_inbox.thread.openAttachment') }}</a>
          <p
            v-if="item.message.media_caption && item.message.media_caption !== item.message.body"
            class="wa-bubble__body"
          >
            {{ item.message.media_caption }}
          </p>
        </div>
        <span
          v-if="bodiless(item.message)"
          class="wa-bubble__kind"
          data-testid="whatsapp-inbox-message-kind"
        >{{ kindLabel(item.message.kind, t) }}</span>
        <p
          v-if="item.message.body"
          class="wa-bubble__body"
        >
          {{ item.message.body }}
        </p>
        <span class="wa-bubble__meta">
          <span
            v-if="item.message.origin === 'phone_app'"
            data-testid="whatsapp-inbox-message-from-phone"
          >{{ $t('whatsapp_inbox.thread.fromPhone') }}</span>
          <span v-if="item.message.sent_by_name">{{ item.message.sent_by_name }}</span>
          <time :datetime="item.message.sent_at">{{ when(item.message.sent_at) }}</time>
          <span
            v-if="item.message.direction === 'outbound'"
            class="wa-bubble__status"
            :class="`wa-bubble__status--${notSent(item.message) ? 'failed' : item.message.status}`"
            data-testid="whatsapp-inbox-message-status"
          >{{ statusLabel(item.message) }}</span>
          <span
            v-if="item.message.wa_message_id && reactions.get(item.message.wa_message_id)"
            class="wa-bubble__reaction"
            data-testid="whatsapp-inbox-message-reaction"
          >{{ reactions.get(item.message.wa_message_id)?.join(' ') }}</span>
        </span>
        <span
          v-if="item.message.status === 'failed' && item.message.error_message"
          class="wa-bubble__error"
        >{{ $t('whatsapp_inbox.thread.failedReason', { reason: item.message.error_message }) }}</span>
        <span
          v-if="notSent(item.message)"
          class="wa-bubble__error"
        >
          {{ item.message.error_message }}
          <ion-button
            size="small"
            fill="clear"
            class="wa-bubble__retry"
            data-testid="whatsapp-inbox-message-retry"
            @click="emit('retry', item.message)"
          >
            {{ $t('whatsapp_inbox.thread.retry') }}
          </ion-button>
        </span>
      </article>
      <article
        v-else
        class="wa-bubble wa-bubble--note"
        data-side="note"
        data-testid="whatsapp-inbox-note"
      >
        <span class="wa-bubble__kind">{{ $t('whatsapp_inbox.thread.note') }}</span>
        <p class="wa-bubble__body">
          {{ item.note.text }}
        </p>
        <span class="wa-bubble__meta">
          <span>{{ item.note.author_name }}</span>
          <time :datetime="item.note.created_at">{{ when(item.note.created_at) }}</time>
          <ion-button
            v-if="item.note.can_delete"
            size="small"
            fill="clear"
            class="wa-bubble__delete"
            data-testid="whatsapp-inbox-note-delete"
            @click="emit('deleteNote', item.note)"
          >
            {{ $t('whatsapp_inbox.thread.deleteNote') }}
          </ion-button>
        </span>
      </article>
    </template>
  </section>
</template>

<style scoped>
.wa-thread {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin: 0.6rem 0;
  max-height: min(55vh, 34rem);
  overflow-y: auto;
  padding: 0.25rem;
}
.wa-thread__earlier {
  align-self: center;
}
.wa-thread__quiet {
  color: var(--ion-color-medium);
  margin: 0;
}
.wa-bubble {
  max-width: min(38rem, 85%);
  padding: 0.45rem 0.7rem;
  border-radius: 12px;
  background: var(--ep-surface-2, var(--ion-color-step-50, rgba(0, 0, 0, 0.04)));
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.wa-bubble--inbound {
  align-self: flex-start;
}
/* The business's own: a light wash of the primary colour, so its time, status and reason stay legible. */
.wa-bubble--outbound {
  align-self: flex-end;
  background: rgba(var(--ion-color-primary-rgb, 0, 84, 233), 0.1);
}
.wa-bubble--note {
  align-self: center;
  background: var(--ion-color-warning-tint, #fff4cc);
  border: 1px dashed var(--ion-color-warning-shade, #b8860b);
}
.wa-bubble__body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
}
.wa-bubble__kind {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.wa-bubble__media {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.wa-bubble__media a {
  color: var(--ion-color-primary);
  font-weight: 600;
  word-break: break-all;
}
.wa-bubble__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.wa-bubble__status--failed,
.wa-bubble__error {
  color: var(--ep-danger-text, var(--ion-color-danger-shade));
  font-size: 0.75rem;
  font-weight: 600;
}
.wa-bubble__reaction {
  font-size: 1rem;
}
.wa-bubble__retry {
  margin: 0;
}
.wa-bubble__delete {
  --color: var(--ion-color-danger);
  margin: 0;
}
</style>
