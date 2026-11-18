<script setup lang="ts">
import { IonButton, IonInput } from '@ionic/vue';
import { computed, shallowRef, useId } from 'vue';

import { HubIcon } from '@erplora/ui/shell';

import type { AppHelp, HelpScreen } from '../operations-help';
import { useBaseI18n } from '../lib/i18n';
import { organizeFlows } from '../lib/help';
import HelpMarkdown from './HelpMarkdown.vue';

const props = defineProps<{ help: AppHelp; current?: HelpScreen }>();
const emit = defineEmits<{ expand: [title: string]; go: [path: string] }>();
const { t } = useBaseI18n();
const prefix = useId();
const query = shallowRef('');
const expanded = shallowRef('');
const groups = computed(() => organizeFlows(props.help, props.current?.id, query.value));

function toggle(key: string, title: string): void {
  if (expanded.value === key) {
    expanded.value = '';
    return;
  }
  expanded.value = key;
  emit('expand', title);
}
</script>

<template>
  <div class="help-flows">
    <ion-input
      v-if="help.flows.length > 8"
      class="help-flow-search"
      data-testid="help-flow-search"
      mode="md"
      fill="outline"
      type="search"
      :value="query"
      :aria-label="t('base.help.search')"
      :placeholder="t('base.help.search')"
      @ion-input="query = $event.detail.value ?? ''"
    />
    <div
      v-if="query.trim() && groups.length === 0"
      class="help-flow-empty"
      data-testid="help-flow-empty"
      role="status"
    >
      <p>{{ t('base.help.empty') }}</p>
      <ion-button
        fill="outline"
        data-testid="help-flow-clear"
        @click="query = ''"
      >
        {{ t('base.help.clear') }}
      </ion-button>
    </div>
    <section
      v-for="group in groups"
      v-else
      :key="group.screen.id"
      class="help-flow-group"
    >
      <h4
        v-if="group.screen.title && (group.screen.id !== 'unlisted' || groups.length > 1)"
        class="help-flow-group__title"
      >
        {{ group.screen.title }}
      </h4>
      <div class="help-accordion">
        <div
          v-for="flow in group.flows"
          :key="flow.id"
          class="help-flow-item"
        >
          <h5 class="help-flow-heading">
            <button
              type="button"
              class="help-flow-header"
              :data-testid="`help-flow-${group.screen.id}-${flow.id}`"
              :aria-expanded="expanded === `${group.screen.id}:${flow.id}`"
              :aria-controls="`${prefix}-${group.screen.id}-${flow.id}`"
              @click="toggle(`${group.screen.id}:${flow.id}`, flow.title)"
            >
              <span>{{ flow.title }}</span>
              <HubIcon
                class="help-flow-chevron"
                :class="{ 'help-flow-chevron--open': expanded === `${group.screen.id}:${flow.id}` }"
                name="ion:chevron-down-outline"
              />
            </button>
          </h5>
          <div
            v-if="expanded === `${group.screen.id}:${flow.id}`"
            :id="`${prefix}-${group.screen.id}-${flow.id}`"
            class="help-flow-content"
            :data-testid="`help-flow-content-${group.screen.id}-${flow.id}`"
          >
            <HelpMarkdown
              :text="flow.steps"
              @go="emit('go', $event)"
            />
            <aside
              v-if="flow.failure"
              class="help-failure"
            >
              <strong>{{ t('base.help.failure') }}</strong>
              <HelpMarkdown
                :text="flow.failure"
                @go="emit('go', $event)"
              />
            </aside>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.help-flow-search {
  margin-bottom: 14px;
}
.help-flow-group + .help-flow-group {
  margin-top: 18px;
}
.help-flow-group__title {
  margin: 0 0 8px;
  color: var(--ep-text-muted);
  font-size: 0.75rem;
  font-weight: 650;
}
.help-accordion {
  overflow: hidden;
  border: 1px solid var(--ion-border-color);
  border-radius: var(--ep-radius, 14px);
  background: var(--ion-card-background);
}
.help-flow-item + .help-flow-item {
  border-top: 1px solid var(--ion-border-color);
}
.help-flow-heading {
  margin: 0;
}
.help-flow-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  box-sizing: border-box;
  width: 100%;
  min-height: 48px;
  padding: 12px 14px;
  border: 0;
  color: var(--ion-text-color);
  background: transparent;
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 600;
  text-align: start;
  cursor: pointer;
}
.help-flow-header:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: -3px;
}
.help-flow-chevron {
  flex: none;
  transition: transform 150ms ease;
}
.help-flow-chevron--open {
  transform: rotate(180deg);
}
.help-flow-content {
  padding: 2px 16px 16px;
  color: var(--ep-text-muted);
  font-size: 0.8125rem;
}
.help-failure {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--ep-radius-sm, 10px);
  background: color-mix(in srgb, var(--ion-color-warning) 10%, var(--ion-card-background));
  color: var(--ion-text-color);
  font-size: 0.75rem;
}
.help-failure > strong {
  display: block;
  margin-bottom: 4px;
}
.help-flow-empty {
  padding: 24px 12px;
  color: var(--ep-text-muted);
  text-align: center;
}
@media (prefers-reduced-motion: reduce) {
  .help-flow-chevron {
    transition: none;
  }
}
</style>
