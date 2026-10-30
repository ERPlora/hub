<script setup lang="ts">
// Printing's piece beside the pane (a background route of routes.ts, mounted by the shell on every screen while a person
// is signed in; PRINTING-F18): inside the installed app, the device set up to print here drains the queue of the active
// printers of its registration — «This device» of Printing → Devices, followed live, so setting it up, changing its
// printers or retiring it from any device takes effect at once — through the shell's print host (`/ws/print` and the
// app's commands). A drawer that does not open after the paper says so on screen, naming its printer (PRINTING-F13,
// hub#2724). In a browser it reads nothing: no printer is reachable from it. It paints nothing.
import { useLive } from '@erplora/ui/sdk';
import { nativeBridge, toastError, usePrintHost } from '@erplora/ui/shell';
import { computed, defineComponent } from 'vue';

import { useT } from '../composables/useT';

const inTheApp = nativeBridge() !== null;

const Printing = defineComponent({
  name: 'PrintHostPrinting',
  setup() {
    const t = useT();
    // The page of the devices list that Printing → Devices reads (a business has a handful).
    const { data } = useLive('printing.device.list', { limit: 100 });
    const mine = computed(() => data.value?.rows.find((row) => row.this_device) ?? null);
    const printers = computed(() => mine.value?.printers.filter((printer) => printer.is_active).map((printer) => printer.id) ?? null);
    usePrintHost(printers, {
      onDrawerFailed(job) {
        const name = mine.value?.printers.find((printer) => printer.id === job.printerId)?.name;
        void toastError(name ? t('printing.host.drawerFailed', { printer: name }) : t('printing.host.drawerFailedUnnamed'));
      },
    });
    return () => null;
  },
});
</script>

<template>
  <span
    hidden
    data-testid="printing-print-host"
  >
    <Printing v-if="inTheApp" />
  </span>
</template>
