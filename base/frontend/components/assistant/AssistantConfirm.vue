<script setup lang="ts">
// The card of a write the assistant wants to run (BASE-G115, G116, G119), over everything: the platform's
// ConfirmDialog. A normal write says its action, its app and its first data in one line, and runs with one click; a
// dangerous one (`risk="high"`) lists every datum by its name and, before it runs, asks to type the word in the
// person's language — or, over records named one by one, how many (the dialog compares it as the server does). «Cancel
// all» stops this action and the rest of the turn when more wait behind it. Nothing runs on Cancel or Escape.
import { ConfirmDialog } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';

import { actionKey, type AssistantCard, cardLine, fieldLabelKey, fieldText } from '../../lib/assistant-card';
import type { Money } from '../../lib/home';
import { useBaseI18n } from '../../lib/i18n';

const props = defineProps<{ card: AssistantCard; more: boolean; money?: Money }>();
const emit = defineEmits<{ decide: [accepted: boolean, typed: string, stop: boolean] }>();

const { t, locale } = useBaseI18n();
const open = ref(true);

const high = computed(() => props.card.risk === 'high');
const format = computed(() => ({ locale: locale.value, money: props.money, t }));
const action = computed(() => t(actionKey(props.card.action)));
const message = computed(() =>
  high.value
    ? t('base.assistant.card.highMessage', { action: action.value, app: props.card.app_name })
    : t('base.assistant.card.message', { action: action.value, app: props.card.app_name, line: cardLine(props.card, format.value) }),
);
const lines = computed(() =>
  props.card.fields.map((field) => {
    const key = fieldLabelKey(field.name);
    return `${key ? t(key) : field.label}: ${fieldText(field, format.value)}`;
  }),
);
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    :title="t('base.assistant.card.title')"
    :tone="high ? 'danger' : 'primary'"
    :confirm-label="t('base.assistant.card.run')"
    :cancel-label="t('base.assistant.card.cancel')"
    :consequences="high ? lines : []"
    :require-text="high ? card.confirm_word : undefined"
    testid="assistant-confirm"
    @confirm="emit('decide', true, card.confirm_word, false)"
    @cancel="emit('decide', false, '', false)"
  >
    <p class="assistant-confirm-text">
      {{ message }}
    </p>
    <p
      v-if="card.count"
      class="assistant-confirm-text"
    >
      {{ t('base.assistant.card.count', { count: card.count }) }}
    </p>
    <ion-button
      v-if="more"
      fill="clear"
      size="small"
      color="medium"
      data-testid="assistant-cancel-all"
      @click="emit('decide', false, '', true)"
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
</style>
