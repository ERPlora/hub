<script setup lang="ts">
// «Park check» (SALE-F17 step 2): the hint, the optional title — the time in the reader's language,
// pre-selected so typing replaces it — and «Cancel» | «Park this check» (Enter too). The page parks it
// (`sale.order.set_label`) and releases the screen; a refusal is read here and the check stays.
import { IonButton } from '@ionic/vue';
import { nextTick, shallowRef, useTemplateRef, watch } from 'vue';

import { useLocale } from '../../composables/useT';
import PosSheet from './PosSheet.vue';
import { shortTime } from './till';

const props = defineProps<{ pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ park: [label: string] }>();

const locale = useLocale();
const label = shallowRef('');
const field = useTemplateRef<HTMLInputElement>('field');

watch(
  open,
  async (isOpen) => {
    if (!isOpen) return;
    label.value = shortTime(new Date(), locale.value);
    await nextTick();
    field.value?.focus();
    field.value?.select();
  },
  { immediate: true },
);

function park(): void {
  if (!props.pending) emit('park', label.value.trim());
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="$t('sale.pos.parkTitle')"
    testid="pos-park"
  >
    <p
      class="pos-sheet-hint"
      data-testid="pos-park-hint"
    >
      {{ $t('sale.pos.parkNameHint') }}
    </p>
    <input
      ref="field"
      v-model="label"
      class="pos-sheet-text"
      data-testid="pos-park-name"
      type="text"
      maxlength="120"
      :placeholder="$t('sale.pos.parkNamePlaceholder')"
      :aria-label="$t('sale.pos.parkNameLabel')"
      @keydown.enter.prevent="park"
    >
    <template #foot>
      <div class="pos-sheet-foot">
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-park-error"
        >
          {{ error }}
        </p>
        <div class="pos-sheet-actions">
          <ion-button
            fill="clear"
            color="medium"
            data-testid="pos-park-cancel"
            @click="open = false"
          >
            {{ $t('sale.pos.cancel') }}
          </ion-button>
          <ion-button
            class="pos-sheet-confirm"
            data-testid="pos-park-confirm"
            :disabled="pending"
            @click="park"
          >
            {{ $t('sale.pos.parkCurrentSale') }}
          </ion-button>
        </div>
      </div>
    </template>
  </PosSheet>
</template>
