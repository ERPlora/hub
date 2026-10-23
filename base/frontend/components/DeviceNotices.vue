<script setup lang="ts">
// The device's notices (APPOINTMENT-F28; the old hub's HUB_SHELL-F66): `base.notice.list`, live — the rows the
// modules on tell this person, with their texts filled in on the server — handed to the shell, which tells each new
// one once with the installed app's system notice and opens its screen on a tap. Mounted once beside the pane while
// a person is signed in (`chrome.background`); it paints nothing. Only inside the installed app: a browser has the
// bell, so it does not even follow the query. Where the person hears some notice (`sources`), the shell asks
// Android once to let the app notify, with our sentence first.
import { useLive } from '@erplora/ui/sdk';
import { useDeviceNotices, useSurface } from '@erplora/ui/shell';
import { computed, defineComponent } from 'vue';

const { surface } = useSurface();
const inTheApp = computed(() => surface.value === 'desktop' || surface.value === 'mobile');

const Listening = defineComponent({
  name: 'DeviceNoticesListening',
  setup() {
    const { data } = useLive('base.notice.list', {});
    useDeviceNotices(
      computed(() => data.value?.notices),
      { ask: computed(() => (data.value?.sources.length ?? 0) > 0) },
    );
    return () => null;
  },
});
</script>

<template>
  <span
    hidden
    data-testid="device-notices"
  >
    <Listening v-if="inTheApp" />
  </span>
</template>
