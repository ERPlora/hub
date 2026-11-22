<script setup lang="ts">
import { YouTubeEmbed } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { computed, shallowRef } from 'vue';

import type { AppHelp, HelpScreen } from '../operations-help';
import { useBaseI18n } from '../lib/i18n';
import HelpFlowList from './HelpFlowList.vue';
import HelpMarkdown from './HelpMarkdown.vue';

const props = defineProps<{ help: AppHelp; current?: HelpScreen; icon: string }>();
const emit = defineEmits<{ expand: [title: string]; go: [path: string] }>();
const { t } = useBaseI18n();
const openScreen = shallowRef('');
const otherScreens = computed(() => props.help.screens.filter((screen) => screen.id !== props.current?.id));
</script>

<template>
  <div
    class="help-content"
    data-testid="help-content"
    :lang="help.language"
  >
    <section
      v-if="help.video"
      class="help-section"
      data-help-section="video"
    >
      <YouTubeEmbed
        :video-id="help.video"
        :title="t('base.help.videoTitle', { app: help.name })"
        :icon="icon"
        :language="help.language"
      />
    </section>
    <section
      class="help-section"
      data-help-section="purpose"
    >
      <h3 class="help-section__title">
        {{ t('base.help.purpose') }}
      </h3>
      <HelpMarkdown
        class="ep-text-muted"
        :text="help.purpose"
        @go="emit('go', $event)"
      />
    </section>
    <section
      v-if="current"
      class="help-section"
      data-help-section="current"
    >
      <div
        class="help-current"
        data-testid="help-current-screen"
      >
        <div class="help-current__heading">
          <h3 class="help-section__title">
            {{ t('base.help.current') }} · {{ current.title }}
          </h3>
          <span class="help-here">
            <HubIcon name="ion:location-outline" />
            {{ t('base.help.here') }}
          </span>
        </div>
        <HelpMarkdown
          class="ep-text-muted"
          :text="current.text"
          @go="emit('go', $event)"
        />
      </div>
    </section>
    <section
      v-if="help.flows.length"
      class="help-section"
      data-help-section="flows"
    >
      <h3 class="help-section__title">
        {{ t('base.help.how') }}
      </h3>
      <HelpFlowList
        :help="help"
        :current="current"
        :icon="icon"
        @expand="emit('expand', $event)"
        @go="emit('go', $event)"
      />
    </section>
    <section
      v-if="otherScreens.length"
      class="help-section"
      data-help-section="screens"
    >
      <h3 class="help-section__title">
        {{ t('base.help.others') }}
      </h3>
      <div class="help-other-screens">
        <div
          v-for="screen in otherScreens"
          :key="screen.id"
          class="help-other-screen"
        >
          <h4 class="help-other-screen__heading">
            <button
              type="button"
              class="help-other-screen__button"
              :data-testid="`help-other-screen-${screen.id}`"
              :aria-expanded="openScreen === screen.id"
              :aria-controls="`help-screen-${screen.id}`"
              @click="openScreen = openScreen === screen.id ? '' : screen.id"
            >
              <span>{{ screen.title }}</span>
              <HubIcon name="ion:chevron-down-outline" />
            </button>
          </h4>
          <div
            v-if="openScreen === screen.id"
            :id="`help-screen-${screen.id}`"
            class="help-other-screen__content"
            :data-testid="`help-other-screen-content-${screen.id}`"
          >
            <HelpMarkdown
              class="ep-text-muted"
              :text="screen.text"
              @go="emit('go', $event)"
            />
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.help-section + .help-section {
  margin-top: 24px;
}
.help-section__title {
  margin: 0 0 10px;
  font-size: 0.9375rem;
  letter-spacing: -0.015em;
}
.help-content :deep(.assistant-md) {
  font-size: 0.875rem;
  line-height: 1.6;
}
.help-current {
  padding: 16px;
  border: 1px solid color-mix(in srgb, var(--ion-color-primary) 22%, var(--ion-border-color));
  border-radius: var(--ep-radius-lg, 16px);
  background: color-mix(in srgb, var(--ion-color-primary) 6%, transparent);
}
.help-current__heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.help-current__heading .help-section__title {
  margin: 0;
}
.help-here {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ep-primary-text);
  font-size: 0.75rem;
  font-weight: 700;
}
.help-other-screens {
  overflow: hidden;
  border: 1px solid var(--ion-border-color);
  border-radius: var(--ep-radius, 14px);
}
.help-other-screen + .help-other-screen {
  border-top: 1px solid var(--ion-border-color);
}
.help-other-screen__heading {
  margin: 0;
}
.help-other-screen__button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 48px;
  padding: 12px 14px;
  border: 0;
  color: var(--ion-text-color);
  background: var(--ion-card-background);
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 600;
  text-align: start;
  cursor: pointer;
}
.help-other-screen__button:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: -3px;
}
.help-other-screen__content {
  padding: 2px 16px 16px;
  background: var(--ion-card-background);
}
@media (max-width: 639.98px) {
  .help-section + .help-section {
    margin-top: 20px;
  }
  .help-current {
    padding: 14px;
  }
}
</style>
