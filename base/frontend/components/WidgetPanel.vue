<script setup lang="ts">
// One panel of the Home's board (BASE-G166, BASE-G168; the old hub's `ok-widget-board` cards). A declarative
// panel paints its operation's result by `kind` (lib/home.ts `widgetView`): followed live when the operation
// is a live query — a write anywhere in the business re-runs it on the server and the new result arrives —,
// asked once when it is not. A failed read says «Unavailable», never the figure it had. A panel with its own
// `component` mounts that component of its app (`apps/<app>/frontend/components/<component>.vue`).
import { type OpName, useLive, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonSkeletonText } from '@ionic/vue';
import { type Component, computed, defineAsyncComponent, onMounted, ref, type Ref, shallowRef } from 'vue';

import type { WidgetDef } from '../operations';
import { widgetView } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';

const props = defineProps<{ widget: WidgetDef }>();

/** Every app's components, loaded on demand: a panel names one by its file name. */
const COMPONENTS = import.meta.glob<{ default: Component }>('../../../apps/*/frontend/components/*.vue');

const { locale } = useBaseI18n();
const client = useLiveClient();

interface Source {
  data: Readonly<Ref<unknown>>;
  failed: Readonly<Ref<boolean>>;
  loading: Readonly<Ref<boolean>>;
}

function followed(op: OpName): Source {
  const live = useLive(op, (() => props.widget.params) as never);
  return {
    data: live.data,
    failed: computed(() => live.status.value === 'error'),
    loading: computed(() => live.data.value === undefined && live.status.value !== 'error'),
  };
}

function askedOnce(op: OpName): Source {
  const data = shallowRef<unknown>(undefined);
  const failed = ref(false);
  const loading = ref(true);
  onMounted(async () => {
    try {
      data.value = await client.api.call(op, props.widget.params as never);
    } catch (error) {
      console.warn(`base: the panel ${props.widget.key} could not read ${op}`, error);
      failed.value = true;
    } finally {
      loading.value = false;
    }
  });
  return { data, failed, loading };
}

const componentFailed = ref(false);
const loader = props.widget.component
  ? COMPONENTS[`../../../apps/${props.widget.app}/frontend/components/${props.widget.component}.vue`]
  : undefined;
const custom = loader
  ? defineAsyncComponent({
      loader,
      onError(error, _retry, fail) {
        console.warn(`base: the panel ${props.widget.key} could not load its component`, error);
        componentFailed.value = true;
        fail();
      },
    })
  : undefined;

const op = props.widget.operation as OpName | null;
const source: Source | undefined = !props.widget.component && op ? (props.widget.live ? followed(op) : askedOnce(op)) : undefined;

const unavailable = computed(
  () => (props.widget.component ? !custom || componentFailed.value : !source || source.failed.value),
);
const loading = computed(() => !unavailable.value && (source?.loading.value ?? false));
const view = computed(() => (source ? widgetView(props.widget, source.data.value, locale.value) : { kind: 'empty' as const }));

/** The sparkline's points in a 100×40 box, lowest value at the bottom. */
const points = computed(() => {
  const current = view.value;
  if (current.kind !== 'sparkline') return '';
  const { series } = current;
  const min = Math.min(...series);
  const span = Math.max(...series) - min;
  const y = (v: number) => (span > 0 ? Math.round((40 - ((v - min) / span) * 40) * 100) / 100 : 20);
  if (series.length === 1) return `0,${y(series[0])} 100,${y(series[0])}`;
  return series.map((v, i) => `${Math.round((i / (series.length - 1)) * 10000) / 100},${y(v)}`).join(' ');
});

const percent = (share: number) => `${Math.round(share * 1000) / 10}%`;
</script>

<template>
  <article
    class="widget"
    :class="`widget--${widget.size}`"
    :data-key="widget.key"
    data-testid="widget"
    :aria-busy="loading"
  >
    <header class="widget-head">
      <HubIcon
        v-if="widget.icon"
        class="widget-icon"
        :name="widget.icon"
      />
      <h3
        class="widget-title"
        data-testid="widget-title"
      >
        {{ widget.title }}
      </h3>
      <slot name="actions" />
    </header>

    <p
      v-if="unavailable"
      class="widget-muted"
      data-testid="widget-error"
    >
      {{ $t('base.widgets.error') }}
    </p>
    <component
      :is="custom"
      v-else-if="custom"
    />
    <ion-skeleton-text
      v-else-if="loading"
      animated
      class="widget-skeleton"
    />
    <p
      v-else-if="view.kind === 'empty'"
      class="widget-muted"
      data-testid="widget-empty"
    >
      {{ $t('base.widgets.noData') }}
    </p>
    <p
      v-else-if="view.kind === 'kpi'"
      class="widget-value"
      data-testid="widget-value"
    >
      {{ view.value }}
    </p>
    <div
      v-else-if="view.kind === 'stat'"
      class="widget-stat"
      :data-severity="view.severity"
    >
      <p
        class="widget-value"
        data-testid="widget-value"
      >
        {{ view.value }}
      </p>
      <p
        v-if="view.label"
        class="widget-muted"
      >
        {{ view.label }}
      </p>
    </div>
    <div
      v-else-if="view.kind === 'sparkline'"
      class="widget-sparkline"
      data-testid="widget-sparkline"
    >
      <p
        v-if="view.value !== undefined"
        class="widget-value"
        data-testid="widget-value"
      >
        {{ view.value }}
      </p>
      <svg
        viewBox="-2 -2 104 44"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <polyline
          :points="points"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          vector-effect="non-scaling-stroke"
        />
      </svg>
    </div>
    <ul
      v-else-if="view.kind === 'bar-list'"
      class="widget-bars"
    >
      <li
        v-for="bar in view.bars"
        :key="bar.label"
        class="widget-bar"
        data-testid="widget-bar"
      >
        <span class="widget-bar-label">{{ bar.label }}</span><span class="widget-bar-text">{{ bar.text }}</span>
        <span
          class="widget-bar-track"
          aria-hidden="true"
        ><span
          class="widget-bar-fill"
          :style="{ width: percent(bar.share) }"
        /></span>
      </li>
    </ul>
    <ol
      v-else-if="view.kind === 'timeline'"
      class="widget-timeline"
    >
      <li
        v-for="(entry, index) in view.entries"
        :key="index"
        data-testid="widget-entry"
      >
        <span
          v-if="entry.time"
          class="widget-muted"
        >{{ entry.time }}</span>
        <strong>{{ entry.title }}</strong>
        <span
          v-if="entry.description"
          class="widget-muted"
        >{{ entry.description }}</span>
      </li>
    </ol>
    <div
      v-else-if="view.kind === 'chart'"
      class="widget-chart"
      role="img"
      :aria-label="view.bars.map((bar) => `${bar.label}: ${bar.text}`).join(', ')"
    >
      <div
        v-for="bar in view.bars"
        :key="bar.label"
        class="widget-chart-col"
      >
        <span
          class="widget-chart-bar"
          :style="{ height: percent(bar.share) }"
        />
        <span class="widget-chart-label">{{ bar.label }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.widget {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--ion-color-step-150, #e4e7ec);
  border-radius: var(--ep-radius-lg, 16px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}

.widget-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.widget-icon {
  font-size: 18px;
  color: var(--ion-color-primary);
}

.widget-title {
  flex: 1;
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
}

.widget-value {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.1;
}

.widget-muted {
  margin: 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}

.widget-stat[data-severity='danger'] .widget-value {
  color: var(--ion-color-danger);
}

.widget-stat[data-severity='warning'] .widget-value {
  color: var(--ion-color-warning-shade);
}

.widget-stat[data-severity='success'] .widget-value {
  color: var(--ion-color-success);
}

.widget-skeleton {
  height: 32px;
}

.widget-sparkline svg {
  width: 100%;
  height: 48px;
  color: var(--ion-color-primary);
}

.widget-bars,
.widget-timeline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.widget-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 8px;
  font-size: 0.875rem;
}

.widget-bar-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-bar-track {
  grid-column: 1 / -1;
  height: 6px;
  border-radius: 3px;
  background: var(--ion-color-step-100, #eaecf0);
}

.widget-bar-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--ion-color-primary);
}

.widget-timeline li {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
  font-size: 0.875rem;
}

.widget-chart {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 120px;
}

.widget-chart-col {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  gap: 4px;
  height: 100%;
  min-width: 0;
}

.widget-chart-bar {
  width: 100%;
  min-height: 2px;
  border-radius: 4px 4px 0 0;
  background: var(--ion-color-primary);
}

.widget-chart-label {
  max-width: 100%;
  overflow: hidden;
  font-size: 0.75rem;
  color: var(--ion-color-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
