<script setup lang="ts">
// «Void «<item>»» (SALE-F20): what voiding a line already sent to the kitchen means, the one-tap reasons
// (they write the reason), the box to type another, and «Void item» (destructive), which waits for a
// reason. The page voids it (`sale.order.void_line`); a refusal is read here. Opens blank.
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../../composables/useT';
import PosSheet from './PosSheet.vue';

defineProps<{ name: string; pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ void: [reason: string] }>();

const t = useT();
const reason = shallowRef('');
watch(open, (isOpen) => {
  if (isOpen) reason.value = '';
});

const REASONS = ['mistake', 'changed', 'soldOut', 'duplicate'] as const;
const KEYS: Record<(typeof REASONS)[number], string> = {
  mistake: 'sale.pos.voidReasonMistake',
  changed: 'sale.pos.voidReasonChanged',
  soldOut: 'sale.pos.voidReasonSoldOut',
  duplicate: 'sale.pos.voidReasonDuplicate',
};
const reasons = computed(() => REASONS.map((id) => ({ id, text: t(KEYS[id]) })));
const ready = computed(() => reason.value.trim().length > 0);
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="$t('sale.pos.voidLineOf', { name })"
    testid="pos-void"
  >
    <p
      class="pos-sheet-hint"
      data-testid="pos-void-hint"
    >
      {{ $t('sale.pos.voidLineHint') }}
    </p>
    <div class="pos-sheet-chips">
      <button
        v-for="item in reasons"
        :key="item.id"
        type="button"
        class="pos-sheet-chip"
        :data-testid="`pos-void-reason-${item.id}`"
        :aria-pressed="reason === item.text ? 'true' : 'false'"
        @click="reason = item.text"
      >
        {{ item.text }}
      </button>
    </div>
    <textarea
      v-model="reason"
      class="pos-sheet-text"
      data-testid="pos-void-reason"
      rows="2"
      maxlength="255"
      :aria-label="$t('sale.pos.voidLineReasonPlaceholder')"
      :placeholder="$t('sale.pos.voidLineReasonPlaceholder')"
    />
    <template #foot>
      <div class="pos-sheet-foot">
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-void-error"
        >
          {{ error }}
        </p>
        <ion-button
          expand="block"
          class="pos-sheet-confirm pos-sheet-danger"
          data-testid="pos-void-confirm"
          :disabled="!ready || pending"
          @click="emit('void', reason.trim())"
        >
          {{ $t('sale.pos.voidLineConfirm') }}
        </ion-button>
      </div>
    </template>
  </PosSheet>
</template>
