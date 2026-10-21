<script setup lang="ts">
// The box under the thread (WHATSAPP_INBOX-F32, F33, F36), as Square Messages, Shopify Inbox and Fresha
// put it: «Reply» writes to the customer, «Internal note» writes for the team. A reply is free text only
// within Meta's 24 hours from the customer's last message (the server is the judge; the box also closes
// when the window runs out on screen) and «Template» opens the approved ones. With the number not
// connected, the month spent (or a plan that includes none: WHATSAPP_INBOX-F13, with «Upgrade plan» for whoever
// configures) or no erplora.com, nothing is offered and the reason is said. A refusal keeps the text with its
// reason, and sending it again carries the same key: never sent twice.
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonSegment, IonSegmentButton, IonTextarea } from '@ionic/vue';
import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { BUSINESS_ZONE } from '../lib/format';
import { noAllowance } from '../lib/plan';
import type { ChannelOut, ConversationDetailOut } from '../operations';
import TemplateSendModal from './TemplateSendModal.vue';

const props = withDefaults(
  defineProps<{
    conversation: ConversationDetailOut;
    /** The business's number and its month: says which cap stops a send and where the plan is upgraded. */
    channel?: ChannelOut | null;
    /** «Now» for the 24-hour window; the device's clock unless a test pins it. */
    now?: Date;
  }>(),
  { channel: null, now: undefined },
);

const t = useT();
const locale = useLocale();
const mode = ref<'reply' | 'note'>('reply');
const text = ref('');
const noteText = ref('');
const choosing = ref(false);
/** «Send a template» (and its live list of templates) exists from the first «Template» on: opening a
 *  conversation never reopens the tab's stream a second time just for it. */
const templatesUsed = ref(false);
function chooseTemplate(): void {
  templatesUsed.value = true;
  choosing.value = true;
}
/** The key of the message being written: kept until the hub takes it (a failed send may still have
 *  reached it, so a retry — even with the text retouched — goes with the same key and is never sent
 *  twice); a new one once it was taken or for another conversation. */
let key = crypto.randomUUID();

const send = useCommand('whatsapp_inbox.message.send');
const addNote = useCommand('whatsapp_inbox.note.add');

// The window runs out on screen too: a timer flips it at its end (the server still judges each send).
const clock = ref((props.now ?? new Date()).getTime());
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => props.conversation.window_expires_at,
  (end) => {
    clearTimeout(timer);
    clock.value = (props.now ?? new Date()).getTime();
    const left = end ? new Date(end).getTime() - clock.value : 0;
    if (left > 0 && left < 2 ** 31) timer = setTimeout(() => (clock.value = Date.now()), left);
  },
  { immediate: true },
);
onBeforeUnmount(() => clearTimeout(timer));

const session = useSession();
const blocked = computed(() => props.conversation.send_blocked);
/** Why nothing can be sent, in words: a plan that includes none is not «spent until next month». */
const blockedText = computed(() =>
  blocked.value === 'cap_reached' && noAllowance(props.channel)
    ? t('whatsapp_inbox.composer.notIncluded')
    : t(`whatsapp_inbox.composer.blocked.${blocked.value}`),
);
/** «Upgrade plan» at the cap, for whoever configures, with erplora.com to send them to. */
const upgradeUrl = computed(() =>
  blocked.value === 'cap_reached' && session.can('whatsapp_inbox.configure') ? (props.channel?.plans_url ?? '') : '',
);
const windowOpen = computed(() => {
  const end = props.conversation.window_expires_at;
  return props.conversation.window_open && !!end && new Date(end).getTime() > clock.value;
});
const until = computed(() => formatDateTime(props.conversation.window_expires_at, locale.value, { timeZone: BUSINESS_ZONE }));

async function reply(): Promise<void> {
  const body = text.value.trim();
  if (!body || blocked.value || !windowOpen.value || send.pending.value) return;
  try {
    await send.run({ id: props.conversation.id, text: body, client_message_id: key });
  } catch {
    return; // `send.error` holds it, the text stays.
  }
  text.value = '';
  key = crypto.randomUUID();
}

async function note(): Promise<void> {
  const body = noteText.value.trim();
  if (!body || addNote.pending.value) return;
  try {
    await addNote.run({ id: props.conversation.id, text: body });
  } catch {
    return;
  }
  noteText.value = '';
}

function onKey(event: KeyboardEvent, submit: () => void): void {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    submit();
  }
}

// Another conversation, another draft.
watch(
  () => props.conversation.id,
  () => {
    text.value = '';
    noteText.value = '';
    key = crypto.randomUUID();
    send.error.value = null;
    addNote.error.value = null;
  },
);
</script>

<template>
  <section
    class="wa-composer"
    data-testid="whatsapp-inbox-composer"
  >
    <ion-segment
      :value="mode"
      mode="md"
      data-testid="whatsapp-inbox-composer-mode"
      @ion-change="mode = $event.detail.value === 'note' ? 'note' : 'reply'"
    >
      <ion-segment-button
        value="reply"
        data-testid="whatsapp-inbox-composer-mode-reply"
      >
        {{ $t('whatsapp_inbox.composer.reply') }}
      </ion-segment-button>
      <ion-segment-button
        value="note"
        data-testid="whatsapp-inbox-composer-mode-note"
      >
        {{ $t('whatsapp_inbox.composer.note') }}
      </ion-segment-button>
    </ion-segment>

    <template v-if="mode === 'reply'">
      <InlineFeedback
        v-if="blocked"
        tone="warning"
        data-testid="whatsapp-inbox-composer-blocked"
        :data-code="blocked"
      >
        {{ blockedText }}
        <template
          v-if="upgradeUrl"
          #actions
        >
          <a
            class="wa-composer__link"
            data-testid="whatsapp-inbox-composer-upgrade"
            :href="upgradeUrl"
            target="_blank"
            rel="noopener"
          >{{ $t('whatsapp_inbox.upgradePlan') }}</a>
        </template>
      </InlineFeedback>
      <InlineFeedback
        v-else-if="!windowOpen"
        tone="info"
        data-testid="whatsapp-inbox-composer-closed"
      >
        {{ $t('whatsapp_inbox.conversation.windowClosed') }}
      </InlineFeedback>
      <template v-if="windowOpen || blocked">
        <ion-textarea
          :value="text"
          data-testid="whatsapp-inbox-composer-text"
          :label="t('whatsapp_inbox.composer.label')"
          :placeholder="t('whatsapp_inbox.composer.placeholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :rows="2"
          :maxlength="4096"
          :disabled="!!blocked"
          @ion-input="text = String($event.detail.value ?? '')"
          @keydown="onKey($event, reply)"
        />
        <small
          v-if="windowOpen && !blocked"
          class="wa-composer__hint"
          data-testid="whatsapp-inbox-composer-window"
        >{{ $t('whatsapp_inbox.conversation.windowOpenUntil', { time: until }) }}</small>
      </template>
      <InlineFeedback
        v-if="send.error.value"
        tone="danger"
        data-testid="whatsapp-inbox-composer-error"
      >
        {{ send.error.value.message }}
      </InlineFeedback>
      <div class="wa-composer__actions">
        <ion-button
          fill="outline"
          data-testid="whatsapp-inbox-composer-template"
          :disabled="!!blocked"
          @click="chooseTemplate"
        >
          {{ $t('whatsapp_inbox.composer.template') }}
        </ion-button>
        <ion-button
          data-testid="whatsapp-inbox-composer-send"
          :disabled="!!blocked || !windowOpen || !text.trim() || send.pending.value"
          @click="reply"
        >
          {{ $t('whatsapp_inbox.composer.send') }}
        </ion-button>
      </div>
    </template>

    <template v-else>
      <ion-textarea
        :value="noteText"
        data-testid="whatsapp-inbox-composer-note"
        :label="t('whatsapp_inbox.composer.note')"
        :placeholder="t('whatsapp_inbox.composer.notePlaceholder')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :auto-grow="true"
        :rows="2"
        :maxlength="5000"
        @ion-input="noteText = String($event.detail.value ?? '')"
        @keydown="onKey($event, note)"
      />
      <InlineFeedback
        v-if="addNote.error.value"
        tone="danger"
        data-testid="whatsapp-inbox-composer-note-error"
      >
        {{ addNote.error.value.message }}
      </InlineFeedback>
      <div class="wa-composer__actions">
        <ion-button
          data-testid="whatsapp-inbox-composer-add-note"
          :disabled="!noteText.trim() || addNote.pending.value"
          @click="note"
        >
          {{ $t('whatsapp_inbox.composer.addNote') }}
        </ion-button>
      </div>
    </template>

    <TemplateSendModal
      v-if="templatesUsed"
      v-model:open="choosing"
      :conversation-id="conversation.id"
    />
  </section>
</template>

<style scoped>
.wa-composer {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.wa-composer__hint {
  color: var(--ion-color-medium-shade);
}
.wa-composer__link {
  color: var(--ion-color-primary);
  font-weight: 600;
}
.wa-composer__actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.5rem;
}
/* 44px minimum touch target: this screen is used one-handed, at a counter. */
ion-button {
  --min-height: 44px;
}
</style>
