<script setup lang="ts">
// A bubble of the assistant's panel. The person's: what it wrote, as it wrote it, and the names of its files. The
// assistant's: three dots until something arrives, then the answer with its format (BASE-G113) and, below, what the
// panel adds and the model never writes — «Go to …» for up to four screens of this hub it names (BASE-G114), the
// notices of what it said against what ran (BASE-G117), a receipt of each action of the turn, a failure with its way
// out (BASE-G124; a spent allowance with its numbers and the plan, BASE-G122) and, under a finished answer, «Read
// aloud» and «Report a problem» (BASE-G123).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonIcon } from '@ionic/vue';
import { computed } from 'vue';

import { actionKey, screenKey } from '../../lib/assistant-card';
import { errorView } from '../../lib/assistant-guide';
import type { Bubble } from '../../lib/assistant-history';
import { ASSISTANT_ICONS } from '../../lib/assistant-icons';
import { linkPaths, parseMarkdown } from '../../lib/assistant-markdown';
import { useBaseI18n } from '../../lib/i18n';
import AssistantMarkdown from './AssistantMarkdown.vue';

const MAX_GO = 4;

const props = defineProps<{
  bubble: Bubble;
  screenExists: (path: string) => boolean;
  nameOf: (path: string) => string | undefined;
  /** The menu's name of an app, in the screen's language; none for an app it does not list. */
  appNameOf: (app: string) => string | undefined;
  /** Who runs the business, on the web: «Upgrade plan» opens the plan's page on erplora.com. */
  canUpgrade: boolean;
  planUrl: string;
  canSpeak: boolean;
  speaking?: boolean;
}>();
const emit = defineEmits<{
  go: [path: string];
  retry: [];
  newConversation: [];
  signIn: [];
  report: [];
  listen: [];
}>();

const { t, locale } = useBaseI18n();

const goes = computed(() =>
  linkPaths(parseMarkdown(props.bubble.text))
    .filter((path) => props.screenExists(path) && props.nameOf(path))
    .slice(0, MAX_GO)
    .map((path) => ({ path, name: props.nameOf(path) as string })),
);

const failure = computed(() => (props.bubble.error ? errorView(props.bubble.error, props.bubble.details ?? {}) : null));

const renews = computed(() => {
  const at = failure.value?.values?.resetsAt;
  if (typeof at !== 'string') return '';
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return '';
  const day = new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'long', timeZone: 'UTC' }).format(date);
  return t('base.assistant.renews', { date: day });
});

/** What happened and, for a spent month, when it comes back: two sentences, one space between them. */
const failureText = computed(() =>
  failure.value ? [t(failure.value.key, failure.value.values), renews.value].filter(Boolean).join(' ') : '',
);

const receipts = computed(() =>
  (props.bubble.executed ?? []).map((row) => ({
    outcome: row.outcome,
    text: t(`base.assistant.receipts.${row.outcome}`, {
      action: t(actionKey(row.name)),
      app: placeOf(row),
    }),
  })),
);

/** Where an action happened, in the language the screen is in, never in the one of its turn (a receipt kept from a
 *  turn in English read «Rectificar en Invoicing» in Spanish): the platform by its screen, an app by its menu; one
 *  neither names (an app the menu does not list, a receipt kept from before it carried its screen), as the server
 *  named it then. */
function placeOf(row: { app: string; app_name?: string; screen?: string }): string {
  const key = screenKey(row.screen);
  return key ? t(key) : props.appNameOf(row.app) || row.app_name || row.app;
}

const writing = computed(() => !props.bubble.done && props.bubble.text === '');
const silent = computed(() => props.bubble.done && !props.bubble.text && !props.bubble.error && !props.bubble.stopped);
const finished = computed(() => props.bubble.done && props.bubble.text !== '' && !writing.value);
</script>

<template>
  <div
    v-if="bubble.role === 'user'"
    class="assistant-row assistant-row--user"
  >
    <div
      class="assistant-bubble assistant-bubble--user"
      data-testid="assistant-bubble-user"
    >
      <span class="assistant-user-text">{{ bubble.text }}</span>
      <span
        v-for="file in bubble.files"
        :key="file"
        class="assistant-file-chip"
      >{{ file }}</span>
    </div>
  </div>
  <div
    v-else
    class="assistant-row"
    data-testid="assistant-answer"
  >
    <!-- A failure before any word has no bubble: its sentence is the answer (BASE-G124). -->
    <div
      v-if="!(bubble.error && !bubble.text)"
      class="assistant-bubble"
      data-testid="assistant-bubble-assistant"
    >
      <span
        v-if="writing"
        class="assistant-dots"
        role="status"
        data-testid="assistant-writing"
        :aria-label="t('base.assistant.writing')"
      ><i /><i /><i /></span>
      <AssistantMarkdown
        v-else-if="bubble.text"
        :text="bubble.text"
        :screen-exists="screenExists"
        :name-of="nameOf"
        @go="emit('go', $event)"
      />
      <p
        v-else-if="silent"
        class="assistant-muted"
      >
        {{ t('base.assistant.noAnswer') }}
      </p>
      <p
        v-if="bubble.stopped"
        class="assistant-muted"
      >
        {{ t('base.assistant.stopped') }}
      </p>
    </div>

    <div
      v-if="goes.length"
      class="assistant-goes"
    >
      <ion-button
        v-for="go in goes"
        :key="go.path"
        size="small"
        fill="outline"
        data-testid="assistant-go"
        @click="emit('go', go.path)"
      >
        {{ t('base.assistant.goTo', { name: go.name }) }}
      </ion-button>
    </div>

    <ul
      v-if="receipts.length"
      class="assistant-receipts"
    >
      <li
        v-for="(receipt, index) in receipts"
        :key="index"
        :class="`assistant-receipt--${receipt.outcome}`"
        data-testid="assistant-receipt"
      >
        <HubIcon :name="receipt.outcome === 'ok' ? 'ion:checkmark-circle-outline' : 'ion:close-circle-outline'" />
        {{ receipt.text }}
      </li>
    </ul>

    <p
      v-if="bubble.blocked"
      class="assistant-notice"
      data-testid="assistant-not-from-chat"
    >
      <HubIcon name="ion:warning-outline" />
      <span>{{ t('base.assistant.card.notFromChat') }}</span>
    </p>
    <p
      v-for="notice in bubble.notices"
      :key="notice"
      class="assistant-notice"
      role="status"
      :data-testid="`assistant-notice-${notice}`"
    >
      <HubIcon name="ion:warning-outline" />
      <span>{{ t(`base.assistant.notices.${notice}`) }}</span>
    </p>

    <div
      v-if="failure"
      class="assistant-failure"
      role="alert"
      data-testid="assistant-failure"
    >
      <p>
        <HubIcon name="ion:alert-circle-outline" />
        <span>{{ failureText }}</span>
      </p>
      <ion-button
        v-if="failure.recovery === 'retry'"
        size="small"
        fill="outline"
        data-testid="assistant-retry"
        @click="emit('retry')"
      >
        <HubIcon
          slot="start"
          name="ion:refresh-outline"
        />
        {{ t('base.assistant.retry') }}
      </ion-button>
      <ion-button
        v-else-if="failure.recovery === 'new'"
        size="small"
        fill="outline"
        data-testid="assistant-failure-new"
        @click="emit('newConversation')"
      >
        {{ t('base.assistant.newConversation') }}
      </ion-button>
      <ion-button
        v-else-if="failure.recovery === 'signin'"
        size="small"
        fill="outline"
        data-testid="assistant-sign-in"
        @click="emit('signIn')"
      >
        {{ t('base.assistant.signIn') }}
      </ion-button>
      <template v-else-if="failure.recovery === 'upgrade'">
        <!-- A plain link, as the menu's «Upgrade plan» (UpgradePlanLink): erplora.com's plan page, in a new tab. -->
        <a
          v-if="canUpgrade && planUrl"
          class="assistant-upgrade"
          :href="planUrl"
          target="_blank"
          rel="noopener"
          data-testid="assistant-upgrade"
        >
          <HubIcon name="ion:sparkles-outline" />
          {{ t('base.assistant.upgrade') }}
        </a>
        <p
          v-else
          class="assistant-muted"
        >
          {{ t('base.assistant.askOwner') }}
        </p>
      </template>
    </div>

    <div
      v-if="finished"
      class="assistant-actions"
    >
      <ion-button
        v-if="canSpeak"
        size="small"
        fill="clear"
        data-testid="assistant-listen"
        :aria-pressed="speaking ? 'true' : 'false'"
        @click="emit('listen')"
      >
        <ion-icon
          slot="start"
          :src="ASSISTANT_ICONS.listen"
          aria-hidden="true"
        />
        {{ speaking ? t('base.assistant.stopListening') : t('base.assistant.listen') }}
      </ion-button>
      <ion-button
        size="small"
        fill="clear"
        color="medium"
        data-testid="assistant-report"
        @click="emit('report')"
      >
        <HubIcon
          slot="start"
          name="ion:chatbubbles-outline"
        />
        {{ t('base.assistant.report.action') }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.assistant-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 14px;
}
.assistant-row--user {
  align-items: flex-end;
}
.assistant-bubble {
  max-width: 100%;
  padding: 10px 12px;
  border-radius: 14px;
  background: var(--ion-color-light, #f4f5f8);
  color: var(--ion-text-color, #111);
}
.assistant-bubble--user {
  max-width: 85%;
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast, #fff);
}
.assistant-user-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.assistant-file-chip {
  display: block;
  margin-top: 6px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgb(255 255 255 / 0.2);
  font-size: 0.85em;
}
.assistant-muted {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.9em;
}
.assistant-dots {
  display: inline-flex;
  gap: 4px;
  padding: 4px 0;
}
.assistant-dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ion-color-medium);
  animation: assistant-dot 1.2s infinite ease-in-out;
}
.assistant-dots i:nth-child(2) {
  animation-delay: 0.2s;
}
.assistant-dots i:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes assistant-dot {
  0%,
  80%,
  100% {
    opacity: 0.3;
  }
  40% {
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .assistant-dots i {
    animation: none;
  }
}
.assistant-goes,
.assistant-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.assistant-receipts {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 0.88em;
}
.assistant-receipts li {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* The text in the readable grey (WCAG AA on white, hub#1291); the colour says it in the icon only. */
.assistant-receipts li {
  color: var(--ion-color-medium-shade, #5f6368);
}
.assistant-receipt--ok :deep(ion-icon) {
  color: var(--ion-color-success-shade, #2b8a3e);
}
.assistant-receipt--cancelled,
.assistant-receipt--error,
.assistant-receipt--refused {
  color: var(--ion-color-medium-shade, #666);
}
.assistant-notice,
.assistant-failure p {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 0;
  font-size: 0.88em;
}
.assistant-notice {
  color: var(--ion-color-medium-shade, #5f6368);
}
.assistant-notice :deep(ion-icon) {
  flex: none;
  margin-top: 2px;
  color: var(--ion-color-warning-shade, #b07d00);
}
.assistant-upgrade {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast, #fff);
  font-size: 0.9em;
  font-weight: 600;
  text-decoration: none;
}
.assistant-failure {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  color: var(--ion-color-danger-shade, #c0392b);
}
</style>
