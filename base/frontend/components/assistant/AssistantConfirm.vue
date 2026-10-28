<script setup lang="ts">
// The card of a write the assistant wants to run (BASE-G115, G116, G119), over everything: the platform's
// ConfirmDialog. A normal write says its action, its app and its first data in one line, and runs with one click; a
// dangerous one (`risk="high"`) lists every datum by its name and, before it runs, asks to type the word in the
// person's language — or, over records named one by one, how many (the dialog compares it, and the server again with
// what was typed). When its app declares one, it first says what will happen (BASE-F98: the preview, as the app's read
// answers it for this person). «Cancel all» stops this action and the rest of the turn when more wait behind it.
// Nothing runs on Cancel or Escape.
// Mounted with the panel: it opens when a card arrives (after mounting: Ionic presents a modal only once it is in the
// page) and closes when the card goes; the last card stays painted while the dialog closes.
import { ConfirmDialog } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed, onMounted, ref, shallowRef, watch } from 'vue';

import { actionKey, type AssistantCard, cardLine, fieldLines } from '../../lib/assistant-card';
import type { Money } from '../../lib/home';
import { useBaseI18n } from '../../lib/i18n';

const props = defineProps<{ card: AssistantCard | null; more: boolean; money?: Money }>();
const emit = defineEmits<{ decide: [accepted: boolean, typed: string, stop: boolean] }>();

const { t, locale } = useBaseI18n();
const open = ref(false);
const shown = shallowRef<AssistantCard | null>(null);
/** What the person typed on a dangerous card, as typed: the server checks it again (BASE-G116). */
const typed = ref('');

function follow(card: AssistantCard | null): void {
  if (card) shown.value = card;
  open.value = card !== null;
}

onMounted(() => follow(props.card));
watch(() => props.card, follow);

const high = computed(() => shown.value?.risk === 'high');
const format = computed(() => ({ locale: locale.value, money: props.money ?? shown.value?.money ?? undefined, t }));
const action = computed(() => (shown.value ? t(actionKey(shown.value.action)) : ''));
const message = computed(() => {
  const card = shown.value;
  if (!card) return '';
  return high.value
    ? t('base.assistant.card.highMessage', { action: action.value, app: card.app_name })
    : t('base.assistant.card.message', { action: action.value, app: card.app_name, line: cardLine(card, format.value) });
});
const lines = computed(() => fieldLines(shown.value?.fields ?? [], format.value));
/** What it will do: a dangerous card only (a normal one is a single line). */
const preview = computed(() => (high.value ? fieldLines(shown.value?.preview ?? [], format.value) : []));

function decide(accepted: boolean, stop = false): void {
  const card = shown.value;
  if (!card || !open.value) return;
  open.value = false;
  emit('decide', accepted, accepted && high.value ? typed.value : '', stop);
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    v-model:typed="typed"
    :title="t('base.assistant.card.title')"
    :tone="high ? 'danger' : 'primary'"
    :confirm-label="t('base.assistant.card.run')"
    :cancel-label="t('base.assistant.card.cancel')"
    :consequences="high ? lines : []"
    :require-text="high && shown ? shown.confirm_word : undefined"
    testid="assistant-confirm"
    @confirm="decide(true)"
    @cancel="decide(false)"
  >
    <p class="assistant-confirm-text">
      {{ message }}
    </p>
    <p
      v-if="shown?.count"
      class="assistant-confirm-text"
    >
      {{ t('base.assistant.card.count', { count: shown.count }) }}
    </p>
    <section
      v-if="preview.length"
      class="assistant-confirm-preview"
      data-testid="assistant-confirm-preview"
    >
      <h3 class="assistant-confirm-preview-title">
        {{ t('base.assistant.card.preview') }}
      </h3>
      <ul class="assistant-confirm-preview-lines">
        <li
          v-for="line in preview"
          :key="line"
        >
          {{ line }}
        </li>
      </ul>
    </section>
    <ion-button
      v-if="more"
      fill="clear"
      size="small"
      color="medium"
      data-testid="assistant-cancel-all"
      @click="decide(false, true)"
    >
      {{ t('base.assistant.card.cancelAll') }}
    </ion-button>
  </ConfirmDialog>
</template>

<style scoped>
.assistant-confirm-text {
  margin: 0 0 8px;
  overflow-wrap: anywhere;
}
.assistant-confirm-preview {
  margin: 4px 0 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--ion-color-light, #f4f5f8);
}
.assistant-confirm-preview-title {
  margin: 0 0 6px;
  font-size: 0.85rem;
  font-weight: 600;
}
.assistant-confirm-preview-lines {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 0.9rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
</style>
