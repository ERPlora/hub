<script setup lang="ts">
// base's piece at the end of the topbar (`createShell({ chrome: { topbar } })`): the assistant's sparkles, then the
// bell, as in the old hub (BASE-G110, BASE-G137). On a phone (under 768 px) both fold into one «More options» that
// carries the bell's count, as the old hub's bar did: the shell keeps the title centred with two buttons a side, and a
// third one would push it. Its rows open the panel and the bell's list; the apps' grid stays outside (the shell's).
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonItem, IonLabel, IonList, IonPopover } from '@ionic/vue';
import { computed, onBeforeUnmount, ref, useTemplateRef } from 'vue';

import { useAssistant } from '../lib/assistant';
import { useBaseI18n } from '../lib/i18n';
import AssistantButton from './assistant/AssistantButton.vue';
import HubBell from './HubBell.vue';

const COMPACT = '(max-width: 767px)';

const { t } = useBaseI18n();
const session = useSession();
const assistant = useAssistant();
const bell = useTemplateRef<InstanceType<typeof HubBell>>('bell');

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
const count = computed(() => bell.value?.total ?? 0);
const open = ref(false);
const anchor = ref<Event | undefined>();

function openMore(event: Event): void {
  anchor.value = event;
  open.value = true;
}

function openAssistant(): void {
  open.value = false;
  assistant.setOpen(true);
}

function openBell(): void {
  const event = anchor.value;
  open.value = false;
  if (event) bell.value?.show(event);
}
</script>

<template>
  <template v-if="!compact">
    <AssistantButton />
    <HubBell />
  </template>
  <template v-else>
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
      <!-- The badge travels with the menu: folding the bell never hides that there is something. -->
      <ion-badge
        v-if="count > 0"
        color="danger"
        class="topbar-chrome-more-badge"
        data-testid="topbar-chrome-more-badge"
      >
        {{ count }}
      </ion-badge>
    </ion-button>
    <ion-popover
      :is-open="open"
      :event="anchor"
      :aria-label="t('base.assistant.more')"
      @did-dismiss="open = false"
    >
      <ion-list lines="full">
        <ion-item
          v-if="assistantAllowed"
          button
          :detail="false"
          data-testid="topbar-chrome-more-assistant"
          @click="openAssistant"
        >
          <HubIcon
            slot="start"
            name="ion:sparkles-outline"
          />
          <ion-label>{{ t('base.assistant.open') }}</ion-label>
        </ion-item>
        <ion-item
          button
          :detail="false"
          data-testid="topbar-chrome-more-bell"
          @click="openBell"
        >
          <HubIcon
            slot="start"
            name="ion:notifications-outline"
          />
          <ion-label>{{ t('base.bell.title') }}</ion-label>
          <ion-badge
            v-if="count > 0"
            slot="end"
            color="danger"
          >
            {{ count }}
          </ion-badge>
        </ion-item>
      </ion-list>
    </ion-popover>
    <HubBell
      ref="bell"
      folded
    />
  </template>
</template>

<style scoped>
.topbar-chrome-more {
  position: relative;
}

.topbar-chrome-more-badge {
  position: absolute;
  top: 2px;
  inset-inline-end: 0;
  min-width: 16px;
  padding: 2px 4px;
  font-size: 10px;
}
</style>
