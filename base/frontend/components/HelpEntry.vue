<script setup lang="ts">
import { HubIcon, useMyApps, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, nextTick, onMounted, shallowRef, watch } from 'vue';
import { useRoute } from 'vue-router';

import { PLATFORM, PLATFORM_NAME } from '../lib/help';
import { readJsonBlock, type HubHome } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';

import HelpWindow from './HelpWindow.vue';

const { t } = useBaseI18n();
const route = useRoute();
const apps = useMyApps();
const session = useSession();
const open = shallowRef(false);
const ready = readJsonBlock<HubHome & { help_apps?: string[] }>('hub-home')?.help_apps ?? [];
const app = computed(() => route.meta.app ?? (route.meta.help ? PLATFORM : undefined));
const available = computed(() => !!app.value && ready.includes(app.value) && session.can('base.view_home'));
const current = computed(() => apps.value.find((candidate) => candidate.id === app.value));
const icon = computed(() => current.value?.icon ?? 'ion:help-circle-outline');
const appName = computed(() => current.value?.name ?? (app.value === PLATFORM ? PLATFORM_NAME : (app.value ?? '')));
const triggerTarget = shallowRef<HTMLElement | null>(null);

// Mounted beside the pane, the entry paints into the visible page's topbar instead of the shell's folded project piece.
function placeTrigger(): void {
  const headers = [...document.querySelectorAll<HTMLElement>('.app-topbar')].filter(
    (header) => !header.closest('.ion-page-hidden'),
  );
  triggerTarget.value = headers.at(-1)?.querySelector<HTMLElement>('[slot="end"]') ?? null;
}

watch(() => route.fullPath, () => void nextTick(placeTrigger));
onMounted(placeTrigger);

watch(app, () => {
  open.value = false;
});
</script>

<template>
  <template v-if="available && app">
    <Teleport
      v-if="triggerTarget"
      :to="triggerTarget"
    >
      <ion-button
        class="help-entry"
        data-testid="help-button"
        aria-haspopup="dialog"
        :aria-expanded="String(open)"
        :aria-label="t('base.help.open')"
        :title="t('base.help.open')"
        @click="open = true"
      >
        <HubIcon
          slot="icon-only"
          name="ion:help-circle-outline"
        />
      </ion-button>
    </Teleport>
    <HelpWindow
      v-model:open="open"
      :app="app"
      :app-name="appName"
      :icon="icon"
    />
  </template>
</template>

<style>
ion-header.app-topbar .help-entry {
  order: 1;
}
ion-header.app-topbar ion-buttons[slot='end']:has(.help-entry) .action-bell-wrap {
  order: 2;
}
</style>
