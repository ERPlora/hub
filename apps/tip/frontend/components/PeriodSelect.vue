<script setup lang="ts">
// The period of a tips screen as the select of its toolbar: Today, 7 days or 30 days.
import { IonSelect, IonSelectOption } from '@ionic/vue';

import { PERIODS, type Period } from '../composables/usePeriod';

defineProps<{ value: Period; testid: string }>();
const emit = defineEmits<{ pick: [value: unknown] }>();
</script>

<template>
  <ion-select
    :data-testid="testid"
    interface="popover"
    :value="value"
    :aria-label="$t('tip.list.period.label')"
    @ion-change="emit('pick', $event.detail.value)"
  >
    <ion-select-option
      v-for="option in PERIODS"
      :key="option"
      :value="option"
    >
      {{ $t(`tip.list.period.${option}`) }}
    </ion-select-option>
  </ion-select>
</template>
