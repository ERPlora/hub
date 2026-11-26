<script setup lang="ts">
// What the till shows while something it needs is on its way (its settings, a check opened by its address): a spinner,
// with its words when it has them; once it failed, why, with the one button that gets the person out (`act`).
// Hooks: `<testid>-loading`, `-error`, `-action`.
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton, IonSpinner } from '@ionic/vue';

defineProps<{
  /** Why it failed; `null` while it loads. */
  error: string | null;
  /** The error's button («Retry», «Continue»). */
  action: string;
  /** What is on its way, said beside the spinner; none: the spinner alone. */
  loading?: string;
  testid: string;
}>();
const emit = defineEmits<{ act: [] }>();
</script>

<template>
  <InlineFeedback
    v-if="error"
    tone="danger"
    :data-testid="`${testid}-error`"
  >
    {{ error }}
    <template #actions>
      <ion-button
        size="small"
        fill="outline"
        :data-testid="`${testid}-action`"
        @click="emit('act')"
      >
        {{ action }}
      </ion-button>
    </template>
  </InlineFeedback>
  <div
    v-else
    class="pos-load-state"
    role="status"
    :data-testid="`${testid}-loading`"
  >
    <ion-spinner />
    <span v-if="loading">{{ loading }}</span>
  </div>
</template>

<style scoped>
.pos-load-state {
  display: flex;
  flex: 1;
  gap: 0.75rem;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--ep-text-muted);
}
</style>
