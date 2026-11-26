<script setup lang="ts">
import { IonTextarea } from '@ionic/vue';
import { computed, reactive, watch } from 'vue';

import FoldedSection from './FoldedSection.vue';

const props = withDefaults(defineProps<{ notesError?: string; internalNotesError?: string }>(), {
  notesError: undefined,
  internalNotesError: undefined,
});
const notes = defineModel<string>('notes', { required: true });
const internalNotes = defineModel<string>('internalNotes', { required: true });

type Key = 'notes' | 'internal_notes';
/** Each note's form key, its words and its reason; a note with text comes open. */
const opened = reactive<Record<Key, boolean>>({ notes: notes.value !== '', internal_notes: internalNotes.value !== '' });
const entries = computed(() => [
  { key: 'notes' as const, label: 'appointment.form.notes', model: notes, error: props.notesError },
  { key: 'internal_notes' as const, label: 'appointment.form.internalNotes', model: internalNotes, error: props.internalNotesError },
]);

watch(
  () => entries.value.map((entry) => entry.error),
  () => {
    for (const entry of entries.value) if (entry.error) opened[entry.key] = true;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <div class="booking-notes">
    <FoldedSection
      v-for="entry in entries"
      :key="entry.key"
      v-model:open="opened[entry.key]"
      :title="$t(entry.label)"
      :hint="$t('appointment.form.optional')"
      :testid="`appointment-form-${entry.key}-fold`"
    >
      <ion-textarea
        :data-testid="`appointment-form-${entry.key}`"
        :value="entry.model.value"
        :label="$t(entry.label)"
        label-placement="floating"
        fill="outline"
        mode="md"
        :auto-grow="true"
        :maxlength="2000"
        :name="entry.key"
        :error-text="entry.error"
        :class="{ 'ion-invalid': !!entry.error, 'ion-touched': !!entry.error }"
        @ion-input="entry.model.value = text($event.detail.value)"
      />
    </FoldedSection>
  </div>
</template>

<style scoped>
.booking-notes {
  display: grid;
  gap: 10px;
}
</style>
