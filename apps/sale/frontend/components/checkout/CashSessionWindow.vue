<script setup lang="ts">
// Cash register's «Open cash session» window (CASH_REGISTER-F03) over the charge sheet: cash refused with the drawer
// closed (SALE-F08) opens the session here, and the charge goes on where it was. Sales does not require Cash register
// (Cash register requires Sales), so the window is found by its name, as Sales calls Cash register's operations by
// theirs, and its code loads only once it is asked for. When that code does not arrive, `unavailable` lets the sheet
// send the person to Cash register instead.
import { type Component, defineAsyncComponent, shallowRef, watch } from 'vue';

import { appComponent } from '../../../../../base/frontend/lib/app-components';

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ opened: []; unavailable: [] }>();

/** Mounted from the first time it is asked for, so it can slide away when it closes. */
const asked = shallowRef(false);
const failed = shallowRef(false);

function unavailable(): void {
  open.value = false;
  emit('unavailable');
}

const loader = appComponent('cash_register', 'OpenSessionModal');
const cashWindow: Component | null = loader
  ? defineAsyncComponent({
      loader: () => loader().then((module) => module.default),
      onError(error, _retry, fail) {
        console.warn('sale: the window to open a cash session could not load', error);
        failed.value = true;
        fail();
        unavailable();
      },
    })
  : null;

watch(open, (now) => {
  if (!now) return;
  if (!cashWindow || failed.value) unavailable();
  else asked.value = true;
});
</script>

<template>
  <component
    :is="cashWindow"
    v-if="cashWindow && asked && !failed"
    v-model:open="open"
    @opened="emit('opened')"
  />
</template>
