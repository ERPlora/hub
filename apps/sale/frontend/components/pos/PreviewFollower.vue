<script setup lang="ts">
// The live preview of the check on screen: `sale.checkout.preview` of all of it, the total the cart
// paints and the FAB carries. Renderless. Mounted only while the check has lines (`useLive` has no
// «skip»). An error — or being let go — hands `undefined` up: the total is unknown, never guessed.
import { useLive } from '@erplora/ui/sdk';
import { onBeforeUnmount, watch } from 'vue';

import type { PreviewOut } from '../../operations';

const props = defineProps<{ orderId: string }>();
const emit = defineEmits<{ preview: [preview: PreviewOut | undefined] }>();

const { data, error } = useLive('sale.checkout.preview', () => ({ order_id: props.orderId }));

watch(
  [data, error],
  ([valued, failed]) => {
    if (failed) emit('preview', undefined);
    else if (valued) emit('preview', valued);
  },
  { immediate: true },
);
onBeforeUnmount(() => emit('preview', undefined));
</script>

<template>
  <slot />
</template>
