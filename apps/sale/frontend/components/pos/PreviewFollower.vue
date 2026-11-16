<script setup lang="ts">
// The live preview of the check on screen: `sale.checkout.preview` of all of it, the total the cart
// paints and the FAB carries. Renderless. Mounted only while the check has lines (`useLive` has no
// «skip»). An error — or being let go — hands `undefined` up: the total is unknown, never guessed;
// the server's refusal goes up too, so the foot can say why instead of leaving an unexplained dash.
import { useLive } from '@erplora/ui/sdk';
import { onBeforeUnmount, watch } from 'vue';

import type { PreviewOut } from '../../operations';

const props = defineProps<{ orderId: string }>();
const emit = defineEmits<{
  preview: [preview: PreviewOut | undefined];
  previewError: [message: string | null];
}>();

const { data, error } = useLive('sale.checkout.preview', () => ({ order_id: props.orderId }));

watch(
  [data, error],
  ([valued, failed]) => {
    if (failed) {
      emit('preview', undefined);
      emit('previewError', failed.message);
    } else if (valued) {
      emit('preview', valued);
      emit('previewError', null);
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  emit('preview', undefined);
  emit('previewError', null);
});
</script>

<template>
  <slot />
</template>
