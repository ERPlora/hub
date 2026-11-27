<script setup lang="ts">
import { EmptyState, FormModal, useAssistant } from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonSkeletonText } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import type { AppHelp } from '../operations-help';
import {
  assistantQuestion,
  createHelpStore,
  PLATFORM,
  resolvePlatformScreen,
  resolveScreen,
  writeAssistantQuestion,
} from '../lib/help';
import { useBaseI18n } from '../lib/i18n';
import HelpContent from './HelpContent.vue';

const props = defineProps<{ app: string; appName: string; icon: string }>();
const open = defineModel<boolean>('open', { default: false });
const { t, locale } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const session = useSession();
const assistant = useAssistant();
const store = createHelpStore(useLiveClient());
const help = shallowRef<AppHelp>();
const loading = shallowRef(false);
const failed = shallowRef(false);
const lastFlow = shallowRef<string>();
const titleElement = shallowRef<HTMLElement | null>(null);
const assistantAllowed = computed(() => session.can('base.view_home'));
const current = computed(() => {
  const screens = help.value?.screens ?? [];
  return props.app === PLATFORM
    ? resolvePlatformScreen(screens, route.matched.at(-1)?.path ?? '', route.hash)
    : resolveScreen(screens, route.path);
});
const title = computed(() => t('base.help.title', { app: help.value?.name ?? props.appName }));
let generation = 0;
let askAfterDismiss = false;

async function load(app: string, language: string): Promise<void> {
  const mine = ++generation;
  loading.value = true;
  failed.value = false;
  help.value = undefined;
  try {
    const answer = await store.read(app, language);
    if (mine === generation) help.value = answer;
  } catch {
    if (mine === generation) failed.value = true;
  } finally {
    if (mine === generation) loading.value = false;
  }
}

watch(
  [open, () => props.app, locale],
  ([shown, app, language]) => {
    if (!shown) {
      generation += 1;
      return;
    }
    lastFlow.value = undefined;
    void load(app, language);
  },
  { immediate: true },
);

function retry(): void {
  void load(props.app, locale.value);
}

function ask(): void {
  if (!help.value) return;
  askAfterDismiss = true;
  open.value = false;
}

function onDismissed(): void {
  titleElement.value = null;
  if (!askAfterDismiss) return;
  askAfterDismiss = false;
  if (!help.value) return;
  const screen = current.value?.title ?? help.value.screens[0]?.title ?? '';
  const question = assistantQuestion(
    { flow: lastFlow.value, app: help.value.name, screen },
    { flow: t('base.help.flowQuestion', { title: '{title}' }), screen: t('base.help.screenQuestion', { app: '{app}', screen: '{screen}' }) },
  );
  assistant.state.draft = writeAssistantQuestion(assistant.state.draft, question);
  assistant.setOpen(true);
}

function onPresented(event?: Event): void {
  const target = event?.target as HTMLElement | null | undefined;
  const modal = target ?? [...document.querySelectorAll<HTMLElement>('[data-testid="help-window"]')].at(-1);
  titleElement.value = modal?.querySelector<HTMLElement>('.ep-form-modal__title') ?? null;
  const body = modal?.querySelector<HTMLElement>('.ep-form-modal__body');
  if (body) body.scrollTop = 0;
  const close = modal?.querySelector<HTMLElement>('.ep-form-modal__close');
  (close?.shadowRoot?.querySelector<HTMLElement>('[part~="native"]') ?? close)?.focus();
}

function go(path: string): void {
  void router.push(path);
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    class="help-window"
    testid="help-window"
    :title="title"
    size="lg"
    readonly
    phone-layout="sheet"
    @will-present="onPresented"
    @did-present="onPresented"
    @did-dismiss="onDismissed"
  >
    <Teleport
      v-if="titleElement"
      :to="titleElement"
    >
      <span
        class="help-window__title-content"
        aria-hidden="true"
      >
        <HubIcon
          class="help-window__app-icon ep-icon-tile"
          :name="icon"
        />
        <span class="help-window__title-text">{{ title }}</span>
      </span>
    </Teleport>
    <div
      v-if="loading"
      class="help-loading"
      data-testid="help-loading"
      aria-busy="true"
      role="status"
    >
      <span class="visually-hidden">{{ t('base.help.loading') }}</span>
      <ion-skeleton-text
        animated
        class="help-loading__lead"
      />
      <ion-skeleton-text
        animated
        class="help-loading__heading"
      />
      <ion-skeleton-text animated />
      <ion-skeleton-text
        animated
        style="width: 88%"
      />
      <ion-skeleton-text
        animated
        class="help-loading__heading"
      />
      <ion-skeleton-text
        animated
        class="help-loading__panel"
      />
      <ion-skeleton-text
        animated
        class="help-loading__heading"
      />
      <ion-skeleton-text
        animated
        class="help-loading__row"
      />
    </div>
    <EmptyState
      v-else-if="failed"
      class="help-error"
      data-testid="help-error"
      role="alert"
      icon="alert-circle-outline"
      :heading="t('base.help.loadError')"
    >
      <template #action>
        <ion-button
          fill="outline"
          data-testid="help-retry"
          @click="retry"
        >
          {{ t('base.help.retry') }}
        </ion-button>
      </template>
    </EmptyState>
    <HelpContent
      v-else-if="help"
      :key="`${help.app}:${help.language}`"
      :help="help"
      :current="current"
      :icon="icon"
      @expand="lastFlow = $event"
      @go="go"
    />
    <template #footer="{ cancel }">
      <ion-button
        v-if="assistantAllowed"
        class="help-ask"
        fill="clear"
        data-testid="help-ask-assistant"
        :aria-label="t('base.help.ask')"
        :title="t('base.help.ask')"
        :disabled="!help"
        @click="ask"
      >
        <HubIcon
          slot="icon-only"
          name="ion:sparkles-outline"
        />
      </ion-button>
      <ion-button
        class="help-close"
        fill="clear"
        data-testid="help-close"
        @click="cancel"
      >
        {{ t('base.help.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style>
ion-modal.help-window .ep-form-modal__title {
  display: block;
  font-size: 0;
  text-align: start;
}
.help-window__title-content {
  display: flex;
  align-items: center;
  gap: 10px;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  color: var(--ion-text-color);
  font-size: 1rem;
  line-height: 1.25;
}
.help-window__title-text {
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
ion-modal.help-window .ep-form-modal__body {
  overscroll-behavior: contain;
}
ion-modal.help-window .ep-form-modal__footer {
  flex-wrap: nowrap;
  justify-content: space-between;
  border-top: 1px solid var(--ion-border-color);
  background: var(--ion-card-background);
}
ion-modal.help-window .help-ask {
  --color: var(--ep-primary-text);
  font-weight: 650;
}
ion-modal.help-window .help-close {
  margin-inline-start: auto;
  --color: var(--ion-text-color);
}
.help-loading {
  display: grid;
  gap: 14px;
}
.help-loading ion-skeleton-text {
  margin: 0;
  border-radius: 8px;
}
.help-loading__lead {
  height: 120px;
  margin-bottom: 10px !important;
}
.help-loading__heading {
  width: 38%;
  margin-top: 8px !important;
}
.help-loading__panel {
  height: 80px;
}
.help-loading__row {
  height: 48px;
}
.help-error {
  --icon-size: 36px;
  --icon-color: var(--ion-color-danger);
  --padding: 24px;
  display: grid;
  place-content: center;
  min-height: 280px;
}
@media (max-width: 639.98px) {
  ion-modal.help-window .ep-form-modal__footer ion-button {
    font-size: 0.75rem;
  }
}
@media (prefers-reduced-motion: reduce) {
  ion-modal.help-window ion-skeleton-text {
    animation: none;
  }
}
</style>
