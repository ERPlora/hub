<script setup lang="ts">
// base's piece at the end of the topbar (`createShell({ chrome: { topbar } })`). On a phone (under 768 px) the
// assistant and the bell fold into one «More options» that carries the bell's count: the shell keeps the title centred
// with two buttons a side, and a third one would push it. The assistant's panel opens only once the menu has closed,
// so what is typed at once goes to its box.
import { AssistantButton, useAssistant } from '@erplora/ui/components';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonItem, IonLabel, IonList, IonPopover } from '@ionic/vue';
import { computed, onBeforeUnmount, ref, useTemplateRef } from 'vue';

import { useBaseI18n } from '../lib/i18n';
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

/** «Assistant» was picked: the panel opens once Ionic has dismissed the menu. While the menu plays its way out its
 *  focus trap pulls the keyboard back into it, so a box opened then lost the focus to a row and the Enter written in
 *  it opened the bell (hub#1121). */
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
      @did-dismiss="onDismissed"
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
          <ion-label>{{ t('assistant.open') }}</ion-label>
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
