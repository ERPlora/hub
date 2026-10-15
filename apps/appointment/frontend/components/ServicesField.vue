<script setup lang="ts">
// The «Services» field of the booking and series panels (APPOINTMENT-F01, F12): the services chosen, in
// order (a cut, then a colour), as chips that can be removed, and a search of the bookable catalog
// (Services) to add one more — each service once. What it learns of a service it offered (length and
// price) goes into `facts`, which the panel reads for its minutes and total.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonChip, IonLabel } from '@ionic/vue';
import { computed, nextTick, ref } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { type ServiceFacts, searchBookableServices } from '../lib/pickers';

const props = withDefaults(
  defineProps<{
    facts: Map<string, ServiceFacts>;
    testid: string;
    errorText?: string;
    disabled?: boolean;
  }>(),
  { errorText: undefined, disabled: false },
);
const services = defineModel<ComboOption[]>({ required: true });

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const search = computed(() => searchBookableServices(client, locale.value, props.facts));
/** The Combo's pick, shown for one render and then emptied: the field is ready for the next service
 *  (the Combo paints its v-model when it changes). Remounting it instead would orphan its open list. */
const adding = ref<ComboOption | null>(null);

async function add(option: ComboOption | null): Promise<void> {
  if (!option) return;
  if (!services.value.some((chosen) => chosen.id === option.id)) services.value = [...services.value, option];
  adding.value = option;
  await nextTick();
  adding.value = null;
}

function remove(id: string): void {
  services.value = services.value.filter((option) => option.id !== id);
}
</script>

<template>
  <div
    class="services-field"
    :data-testid="`${testid}-services`"
  >
    <span class="services-field__label">{{ $t('appointment.form.services') }}</span>
    <div
      v-if="services.length"
      class="services-field__chips"
    >
      <ion-chip
        v-for="option in services"
        :key="option.id"
        :data-testid="`${testid}-service-${option.id}`"
      >
        <ion-label>{{ option.label }}</ion-label>
        <ion-button
          fill="clear"
          size="small"
          :disabled="disabled"
          :aria-label="t('appointment.form.removeService', { name: option.label })"
          @click="remove(option.id)"
        >
          <HubIcon
            slot="icon-only"
            name="ion:close-outline"
          />
        </ion-button>
      </ion-chip>
    </div>
    <Combo
      :testid="`${testid}-service-add`"
      :model-value="adding"
      :search="search"
      :label="services.length ? t('appointment.form.addService') : t('appointment.form.service')"
      :empty-label="t('appointment.form.servicesNone')"
      :error-text="errorText"
      :disabled="disabled"
      @update:model-value="add"
    />
  </div>
</template>

<style scoped>
.services-field__label {
  display: block;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b7280);
  margin-bottom: 4px;
}
.services-field__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}
</style>
