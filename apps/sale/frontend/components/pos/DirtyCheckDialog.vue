<script setup lang="ts">
// «You have a check in progress» (SALE-F17 step 4): before another check comes on screen while this one
// has lines. «Cancel» | «Delete it and open» (only for whoever may void the check) | «Park it and open»
// (only where parking is allowed). The page parks or voids it and then opens the other; a refusal is
// read here and the check stays on screen.
import { IonButton } from '@ionic/vue';

import PosSheet from './PosSheet.vue';

defineProps<{ canPark: boolean; canDiscard: boolean; pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ choose: [choice: 'park' | 'discard'] }>();
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="$t('sale.pos.dirtyCartTitle')"
    testid="pos-dirty"
  >
    <p
      class="pos-sheet-hint"
      data-testid="pos-dirty-body"
    >
      {{ $t('sale.pos.dirtyCartBody') }}
    </p>
    <template #foot>
      <div class="pos-sheet-foot">
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-dirty-error"
        >
          {{ error }}
        </p>
        <div class="pos-sheet-actions pos-dirty__actions">
          <ion-button
            fill="clear"
            color="medium"
            data-testid="pos-dirty-cancel"
            @click="open = false"
          >
            {{ $t('sale.pos.cancel') }}
          </ion-button>
          <ion-button
            v-if="canDiscard"
            fill="outline"
            color="danger"
            data-testid="pos-dirty-discard"
            :disabled="pending"
            @click="emit('choose', 'discard')"
          >
            {{ $t('sale.pos.discardAndOpen') }}
          </ion-button>
          <ion-button
            v-if="canPark"
            class="pos-sheet-confirm"
            data-testid="pos-dirty-park"
            :disabled="pending"
            @click="emit('choose', 'park')"
          >
            {{ $t('sale.pos.parkAndOpen') }}
          </ion-button>
        </div>
      </div>
    </template>
  </PosSheet>
</template>

<style scoped>
.pos-dirty__actions {
  flex-wrap: wrap;
}
</style>
