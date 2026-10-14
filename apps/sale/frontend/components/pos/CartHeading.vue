<script setup lang="ts">
// The heading of the check. The title: a borderless input («New check») that sends a changed title up
// when it is left, and a pencil that focuses it. The context chips: the customer, «Served by …» (who
// the next lines are sealed with; «me» = whoever is signed in; a tap opens the picker), «Customer
// required» when the business demands one and there is none (a tap asks for it), and «Check without
// table or customer» when there is nothing to show.
import { HubIcon } from '@erplora/ui/shell';
import { computed, useTemplateRef } from 'vue';

import { useT } from '../../composables/useT';

const props = defineProps<{
  label: string;
  customerName: string | null;
  /** The professional of the check; `null` = whoever is signed in. */
  staffId: string | null;
  staffName: string | null;
  needsCustomer: boolean;
}>();
const emit = defineEmits<{ rename: [label: string]; staff: []; askCustomer: [] }>();

const t = useT();
const field = useTemplateRef<HTMLInputElement>('field');

const served = computed(() => {
  const name = props.staffName ?? (props.staffId ? t('sale.pos.staffAssigned') : t('sale.pos.staffMe'));
  return t('sale.pos.servedBy', { name });
});

function onChange(): void {
  const next = (field.value?.value ?? '').trim();
  if (next !== props.label) emit('rename', next);
}

function edit(): void {
  field.value?.focus();
  field.value?.select();
}
</script>

<template>
  <div class="pos-heading">
    <div class="pos-heading__title">
      <input
        ref="field"
        class="pos-heading__input"
        data-testid="pos-check-title"
        type="text"
        maxlength="120"
        :value="label"
        :placeholder="$t('sale.pos.newCheckTitle')"
        :aria-label="$t('sale.pos.checkTitleLabel')"
        @change="onChange"
        @keydown.enter="($event.target as HTMLInputElement).blur()"
      >
      <button
        type="button"
        class="pos-heading__edit"
        data-testid="pos-check-title-edit"
        :title="$t('sale.pos.editCheckTitle')"
        :aria-label="$t('sale.pos.editCheckTitle')"
        @click="edit"
      >
        <HubIcon name="ion:create-outline" />
      </button>
    </div>
    <div class="pos-heading__context">
      <span
        v-if="customerName"
        class="pos-chip"
        data-testid="pos-customer-chip"
      >
        <HubIcon name="ion:person-outline" />{{ customerName }}
      </span>
      <button
        type="button"
        class="pos-chip pos-chip--button"
        data-testid="pos-staff-chip"
        :title="$t('sale.pos.staffPickerTitle')"
        :aria-label="`${$t('sale.pos.staffPickerTitle')}: ${served}`"
        @click="emit('staff')"
      >
        <HubIcon name="ion:person-circle-outline" />{{ served }}
      </button>
      <button
        v-if="needsCustomer"
        type="button"
        class="pos-chip pos-chip--button pos-chip--warning"
        data-testid="pos-needs-customer"
        :title="$t('sale.pos.customerRequiredCharge')"
        :aria-label="$t('sale.pos.customerRequiredCharge')"
        @click="emit('askCustomer')"
      >
        <HubIcon name="ion:person-add-outline" />{{ $t('sale.pos.customerRequiredShort') }}
      </button>
      <span
        v-if="!customerName && !needsCustomer"
        class="pos-heading__empty"
        data-testid="pos-check-context-empty"
      >{{ $t('sale.pos.noCheckContext') }}</span>
    </div>
  </div>
</template>

<style scoped>
.pos-heading {
  padding: 0.62rem 0.8rem;
  border-bottom: 1px solid var(--ion-border-color, #e6e3db);
}
.pos-heading__title {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.pos-heading__input {
  flex: 1;
  min-width: 0;
  padding: 0;
  font: inherit;
  font-size: 1rem;
  font-weight: 750;
  color: var(--ion-text-color, #1c1b18);
  background: transparent;
  border: none;
  outline: none;
}
.pos-heading__edit {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  font-size: 1.05rem;
  color: var(--ion-color-medium, #8b897f);
  background: none;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}
.pos-heading__context {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
  margin-top: 0.35rem;
}
.pos-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  height: 1.55rem;
  padding: 0 0.55rem;
  font: inherit;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-color-light, #f2f1ed);
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 999px;
}
.pos-chip--button {
  cursor: pointer;
}
.pos-chip--warning {
  font-weight: 700;
  background: color-mix(in srgb, var(--ion-color-warning, #ffc409) 18%, transparent);
  border-color: var(--ion-color-warning, #ffc409);
}
.pos-heading__empty {
  font-size: 0.72rem;
  color: var(--ion-color-medium, #8b897f);
}
</style>
