<script setup lang="ts">
// One service of Services followed live (`service.service.get`) and handed up on every answer: the till's notice of a
// refused tap goes the moment the service has its tax category (SALE-F38, hub#719), wherever it was tapped (the grid
// or the search). Renderless. Mounted only while that notice is up (`useLive` has no «skip»). An error hands nothing
// up: the notice keeps what the till last knew.
import { useLive } from '@erplora/ui/sdk';
import { watch } from 'vue';

import type { ServiceOut } from '../../../../service/frontend/operations';

const props = defineProps<{ serviceId: string }>();
const emit = defineEmits<{ service: [service: ServiceOut] }>();

const { data } = useLive('service.service.get', () => ({ id: props.serviceId }));

watch(
  data,
  (service) => {
    if (service) emit('service', service);
  },
  { immediate: true },
);
</script>

<template>
  <slot />
</template>
