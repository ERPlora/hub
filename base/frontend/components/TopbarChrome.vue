<script setup lang="ts">
// base's piece at the end of the topbar (`createShell({ chrome: { topbar } })`): «erplora.com», the assistant's
// sparkles, then the bell, as in the old hub (BASE-F11, BASE-G110, BASE-G137). On a phone (under 768 px) they fold into
// one «More options» that carries the bell's count, as the old hub's bar did: the shell keeps the title centred with two
// buttons a side, and a third one would push it. Its rows open erplora.com, the panel and the bell's list; the apps'
// grid stays outside (the shell's).
// «erplora.com» (gh:hub#364, gh:hub#1400) opens this business on erplora.com's panel: a link in a new tab, the system
// browser in the installed app (`openExternalLink`). It shows only where `base/spa.py` embeds its address (whoever may
// open the panel, with their account: never a PIN session) and never in the Google Play copy (`managementOffered`). The
// word on the bar is the brand; its name, the whole sentence (WCAG 2.5.3: the name contains what is written).
import { AssistantButton, useAssistant } from '@erplora/ui/components';
import { HubIcon, openExternalLink, useSession } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonItem, IonLabel, IonList, IonPopover } from '@ionic/vue';
import { computed, onBeforeUnmount, ref, useTemplateRef } from 'vue';

import { type HubHome, readJsonBlock } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import { managementOffered } from '../lib/management';
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
const manageUrl = readJsonBlock<HubHome>('hub-home')?.manage_url ?? '';
const offered = managementOffered();
const manageShown = computed(() => manageUrl !== '' && offered.value);
const count = computed(() => bell.value?.total ?? 0);
const open = ref(false);
const anchor = ref<Event | undefined>();

function openMore(event: Event): void {
  anchor.value = event;
  open.value = true;
}

function openManagement(event: Event): void {
  open.value = false;
  openExternalLink(manageUrl, event);
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
    <ion-button
      v-if="manageShown"
      class="topbar-manage"
      data-testid="topbar-manage"
      fill="clear"
      :href="manageUrl"
      target="_blank"
      rel="noopener"
      :aria-label="t('base.plan.manage')"
      :title="t('base.plan.manage')"
      @click="openExternalLink(manageUrl, $event)"
    >
      <HubIcon
        slot="start"
        name="ion:cloud-outline"
      />
      <ion-label>{{ t('base.plan.manageShort') }}</ion-label>
    </ion-button>
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
          v-if="manageShown"
          button
          :detail="false"
          data-testid="topbar-chrome-more-manage"
          :href="manageUrl"
          target="_blank"
          rel="noopener"
          @click="openManagement"
        >
          <HubIcon
            slot="start"
            name="ion:cloud-outline"
          />
          <ion-label>{{ t('base.plan.manage') }}</ion-label>
        </ion-item>
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
