<script setup lang="ts">
// «Which data?» (WORKBOOK FLOW-F11; the old module's `erp-flows-field-picker`): the one picker the editor
// shares. The data a step can insert are offered grouped by where they come from — what started the
// automation, with a real example of this business beside each, and what each earlier action or read
// leaves — and are chosen, never typed. A list is never offered: a path cannot index one.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonItem, IonList, IonModal, IonNote, IonTitle, IonToolbar } from '@ionic/vue';
import { computed } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import type { DataChoice } from '../lib/document';
import { pathLabel } from '../lib/phrasing';
import type { CatalogOut, Step } from '../operations';

const props = defineProps<{ open: boolean; choices: readonly DataChoice[]; steps: readonly Step[]; catalog: CatalogOut | null }>();
const emit = defineEmits<{ pick: [path: string]; 'update:open': [open: boolean] }>();
const phrasing = usePhrasing();

const groups = computed(() => {
  const out: { id: string; choices: DataChoice[] }[] = [];
  for (const choice of props.choices) {
    const group = out.find((candidate) => candidate.id === choice.group);
    if (group) group.choices.push(choice);
    else out.push({ id: choice.group, choices: [choice] });
  }
  return out;
});

function heading(group: string): string {
  if (group === 'input') return phrasing.value.t('flow.picker.input');
  return phrasing.value.t('flow.picker.step', { n: props.steps.findIndex((step) => step.id === group) + 1 });
}

function example(value: unknown): string {
  if (value === undefined) return '';
  return phrasing.value.t('flow.picker.example', { value: typeof value === 'object' ? JSON.stringify(value) : String(value) });
}

function choose(path: string): void {
  emit('pick', path);
  emit('update:open', false);
}
</script>

<template>
  <IonModal
    :is-open="open"
    data-testid="flow-picker"
    @did-dismiss="emit('update:open', false)"
  >
    <IonHeader>
      <IonToolbar>
        <IonTitle>{{ $t('flow.picker.title') }}</IonTitle>
        <IonButtons slot="end">
          <IonButton
            data-testid="flow-picker-close"
            @click="emit('update:open', false)"
          >
            <HubIcon
              name="ion:close-outline"
              :label="$t('flow.picker.close')"
            />
          </IonButton>
        </IonButtons>
      </IonToolbar>
    </IonHeader>
    <IonContent class="ion-padding">
      <p
        v-if="!choices.length"
        class="flow-picker__none"
        data-testid="flow-picker-none"
      >
        {{ $t('flow.picker.none') }}
      </p>
      <IonList
        v-for="group in groups"
        :key="group.id"
      >
        <h3
          class="flow-picker__group"
          :data-testid="`flow-picker-group-${group.id}`"
        >
          {{ heading(group.id) }}
        </h3>
        <IonItem
          v-for="choice in group.choices"
          :key="choice.path"
          button
          :detail="false"
          :data-testid="`flow-picker-${choice.path}`"
          @click="choose(choice.path)"
        >
          <span class="flow-picker__label">{{ pathLabel(choice.path, steps, catalog, phrasing) }}</span>
          <IonNote
            v-if="choice.example !== undefined"
            slot="end"
          >
            {{ example(choice.example) }}
          </IonNote>
        </IonItem>
      </IonList>
    </IonContent>
  </IonModal>
</template>

<style scoped>
.flow-picker__group {
  margin: 0.75rem 0 0.25rem;
  font-size: 0.78rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-picker__label {
  flex: 1 1 auto;
}
.flow-picker__none {
  color: var(--ep-muted, var(--ion-color-medium));
}
</style>
