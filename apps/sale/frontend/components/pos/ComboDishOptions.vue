<script setup lang="ts">
// The options of a dish picked in a menu (SALE-F42), right under its course: the dish's name and each of its groups of
// Modifiers with the rules of the options sheet of a product sold on its own (SALE-F11); while they load, a line that
// says so; when they could not be read, the words of that sheet with «Retry». It rings while the menu waits for it.
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import type { DishGroups } from '../../composables/pos/useDishGroups';
import { useT } from '../../composables/useT';
import type { Choice } from '../../lib/modifierChoice';
import ChoiceGroupSection, { type SectionGroup } from './ChoiceGroupSection.vue';

const props = defineProps<{
  dish: { id: string; name: string };
  groups: DishGroups;
  choice: Choice;
  /** The group the sheet points at, or `true` for the whole dish (its options still loading or unread). */
  attention: string | boolean;
}>();
const emit = defineEmits<{ tap: [group: SectionGroup, optionId: string]; less: [optionId: string]; retry: [] }>();

const t = useT();

const sections = computed<SectionGroup[]>(() =>
  props.groups.state === 'ready'
    ? props.groups.groups.map((group) => ({ ...group, options: group.options.map((option) => ({ ...option, label: option.name })) }))
    : [],
);
</script>

<template>
  <section
    v-if="groups.state !== 'ready' || sections.length"
    class="pos-menu-dish-options"
    :class="{ 'pos-menu-dish-options--missing': attention === true }"
    :aria-label="dish.name"
    :data-testid="`pos-menu-dish-options-${dish.id}`"
  >
    <p class="pos-menu-dish-options__name">
      {{ dish.name }}
    </p>
    <p
      v-if="groups.state === 'loading'"
      class="pos-sheet-hint"
      role="status"
      :data-testid="`pos-menu-dish-options-loading-${dish.id}`"
    >
      <IonSpinner name="dots" /> {{ t('sale.pos.options.loading') }}
    </p>
    <InlineFeedback
      v-else-if="groups.state === 'error'"
      tone="danger"
      :data-testid="`pos-menu-dish-options-error-${dish.id}`"
    >
      {{ t('sale.pos.options.loadFailed') }}
      <template #actions>
        <IonButton
          fill="outline"
          :data-testid="`pos-menu-dish-options-retry-${dish.id}`"
          @click="emit('retry')"
        >
          {{ t('sale.live.retry') }}
        </IonButton>
      </template>
    </InlineFeedback>
    <ChoiceGroupSection
      v-for="group in sections"
      :key="group.id"
      kind="options"
      :group="group"
      :choice="choice"
      :attention="typeof attention === 'string' ? attention : null"
      @tap="emit('tap', group, $event)"
      @less="emit('less', $event)"
    />
  </section>
</template>

<style scoped>
.pos-menu-dish-options {
  display: grid;
  gap: 0.25rem;
  margin: 0 0 0.5rem 0.75rem;
  padding: 0.25rem 0 0.25rem 0.75rem;
  border-left: 3px solid var(--ion-color-primary, #3880ff);
  border-radius: 4px;
}
.pos-menu-dish-options--missing {
  box-shadow: inset 0 0 0 2px var(--ion-color-warning, #f59e0b);
}
.pos-menu-dish-options__name {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  overflow-wrap: break-word;
}
</style>
