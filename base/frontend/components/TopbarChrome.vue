<script setup lang="ts">
// Base's piece at the end of the topbar. On a phone (under 640 px) only the assistant folds into «More options»: help
// and the bell stay visible. The assistant's panel opens once the menu has closed, so its focus trap cannot take the
// keyboard back from the composer.
import { AssistantButton, useAssistant } from '@erplora/ui/components';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonPopover } from '@ionic/vue';
import { computed, onBeforeUnmount, ref } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import HelpEntry from './HelpEntry.vue';
import HubBell from './HubBell.vue';

const COMPACT = '(max-width: 639px)';
const { t } = useBaseI18n();
const session = useSession();
const assistant = useAssistant();

function media(query: string): MediaQueryList | undefined {
  try {
    return globalThis.matchMedia?.(query);
  } catch {
    return undefined;
  }
}

const compactQuery = media(COMPACT);
const compact = ref(compactQuery?.matches ?? false);
const onCompact = (event: MediaQueryListEvent) => {
  compact.value = event.matches;
};
compactQuery?.addEventListener?.('change', onCompact);
onBeforeUnmount(() => compactQuery?.removeEventListener?.('change', onCompact));

const assistantAllowed = computed(() => session.can('base.view_home'));
const open = ref(false);
const anchor = ref<Event | undefined>();

function openMore(event: Event): void {
  anchor.value = event;
  open.value = true;
}

let assistantOnClose = false;

function openAssistant(): void {
  assistantOnClose = true;
  open.value = false;
}

function onDismissed(): void {
  open.value = false;
  if (!assistantOnClose) return;
  assistantOnClose = false;
  assistant.setOpen(true);
}
</script>

<template>
  <AssistantButton v-if="!compact" />
  <HelpEntry />
  <template v-if="compact && assistantAllowed">
    <ion-button
      class="topbar-chrome-more"
      data-testid="topbar-chrome-more"
      aria-haspopup="true"
      :aria-expanded="String(open)"
      :aria-label="t('base.assistant.more')"
      :title="t('base.assistant.more')"
      @click="openMore"
    >
      <HubIcon
        slot="icon-only"
        name="ion:ellipsis-vertical"
      />
    </ion-button>
    <ion-popover
      :is-open="open"
      :event="anchor"
      :aria-label="t('base.assistant.more')"
      @did-dismiss="onDismissed"
    >
      <ion-list lines="full">
        <ion-item
          button
          :detail="false"
          data-testid="topbar-chrome-more-assistant"
          @click="openAssistant"
        >
          <HubIcon
            slot="start"
            name="ion:sparkles-outline"
          />
          <ion-label>{{ t('assistant.open') }}</ion-label>
        </ion-item>
      </ion-list>
    </ion-popover>
  </template>
  <HubBell />
</template>
