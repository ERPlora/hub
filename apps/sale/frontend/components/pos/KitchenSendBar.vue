<script setup lang="ts">
// The send bar of «Current order» (SALE-F20; Kitchen's KITCHEN-F18): «Send order (N)» and, beside it, the rush
// flame. Armed, the button says «Send RUSH (N)» and the round goes urgent; a send disarms it. The page sends
// (`send`, with whether it is a rush) through Kitchen.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { shallowRef } from 'vue';

defineProps<{ pending: number; busy: boolean }>();
const emit = defineEmits<{ send: [rush: boolean] }>();

const rush = shallowRef(false);

function send(): void {
  emit('send', rush.value);
  rush.value = false;
}
</script>

<template>
  <div class="pos-kitchen-bar">
    <button
      type="button"
      class="pos-kitchen-bar__rush"
      :class="{ 'pos-kitchen-bar__rush--on': rush }"
      :aria-pressed="rush ? 'true' : 'false'"
      :aria-label="$t('sale.pos.kitchen.rush')"
      :title="$t('sale.pos.kitchen.rush')"
      data-testid="pos-kitchen-rush"
      @click="rush = !rush"
    >
      <HubIcon :name="rush ? 'ion:alert-circle' : 'ion:alert-circle-outline'" />
    </button>
    <ion-button
      class="pos-kitchen-bar__send"
      :color="rush ? 'danger' : 'primary'"
      :disabled="busy"
      data-testid="pos-kitchen-send"
      @click="send"
    >
      <HubIcon
        slot="start"
        name="lucide:send"
      />
      {{ rush ? $t('sale.pos.kitchen.sendRush', { count: pending }) : $t('sale.pos.kitchen.send', { count: pending }) }}
    </ion-button>
  </div>
</template>

<style scoped>
.pos-kitchen-bar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  border-top: 1px solid var(--ion-border-color, #e6e3db);
}
.pos-kitchen-bar__rush {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  font-size: 1.35rem;
  color: var(--ion-color-medium, #8b897f);
  background: transparent;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
  cursor: pointer;
}
.pos-kitchen-bar__rush--on {
  color: var(--ion-color-danger, #c5000f);
  border-color: var(--ion-color-danger, #c5000f);
}
.pos-kitchen-bar__send {
  flex: 1;
  min-width: 0;
  margin: 0;
}
</style>
