<script setup lang="ts">
// The Home's board (BASE-G166, BASE-G167; the old hub's `ok-widget-board`): the panels of the apps on that
// this person may see (`base.widget.list`, live: turning an app on or off brings or takes its panels), the
// catalogue's defaults until this browser chooses, and «Customize panel» (⋮): «Recommended» (back to the
// defaults), the active ones to drag or remove, the available ones to add. The choice lives in this browser
// (`dashboard-hub`): every person of this device shares it, and it does not travel to another one.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import {
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonItem,
  IonLabel,
  IonList,
  IonListHeader,
  IonModal,
  IonReorder,
  IonReorderGroup,
  IonSpinner,
  IonTitle,
  IonToolbar,
} from '@ionic/vue';
import { computed, ref } from 'vue';

import type { WidgetDef } from '../operations';
import { activeWidgetKeys, BOARD_STORAGE_KEY, readJsonBlock } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import WidgetPanel from './WidgetPanel.vue';

const { t } = useBaseI18n();
const { data, status, refresh } = useLive('base.widget.list', {});

function readChoice(): string[] | null {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(BOARD_STORAGE_KEY) ?? 'null');
    return Array.isArray(parsed) ? parsed.filter((key): key is string => typeof key === 'string') : null;
  } catch {
    return null;
  }
}

const choice = ref<string[] | null>(readChoice());
const picking = ref(false);

/** The catalogue the shell embedded when the page loaded (`widget-list`, base/spa.py): the panels mount with the board,
 *  so their data goes in the same live stream as the list instead of reopening it. The live answer wins. */
const embedded = readJsonBlock<{ widgets: WidgetDef[] }>('widget-list')?.widgets ?? null;
const catalogue = computed<WidgetDef[]>(() => data.value?.widgets ?? embedded ?? []);
const byKey = computed(() => new Map(catalogue.value.map((widget) => [widget.key, widget])));
const active = computed(() =>
  activeWidgetKeys(choice.value, catalogue.value).map((key) => byKey.value.get(key) as WidgetDef),
);
const available = computed(() => catalogue.value.filter((widget) => !active.value.includes(widget)));
const loading = computed(() => data.value === undefined && embedded === null && status.value !== 'error');
const failed = computed(() => data.value === undefined && embedded === null && status.value === 'error');

/** Keeps the choice; a browser that refuses to store (private mode, full) keeps it until the page closes. */
function choose(keys: string[]): void {
  choice.value = keys;
  try {
    localStorage.setItem(BOARD_STORAGE_KEY, JSON.stringify(keys));
  } catch (error) {
    console.warn('base: could not keep the board in this browser', error);
  }
}

const keys = () => active.value.map((widget) => widget.key);
const add = (key: string) => choose([...keys(), key]);
const remove = (key: string) => choose(keys().filter((other) => other !== key));
const recommended = () => choose(catalogue.value.filter((widget) => widget.default).map((widget) => widget.key));

function onReorder(event: CustomEvent<{ from: number; to: number; complete: (data?: boolean) => unknown }>): void {
  const { from, to } = event.detail;
  // Ionic puts the row back; the board paints the order kept.
  event.detail.complete(false);
  if (from === to) return;
  const next = keys();
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  choose(next);
}
</script>

<template>
  <section
    class="widget-board"
    data-testid="widget-board"
    :aria-busy="loading"
  >
    <header class="widget-board-head">
      <ion-button
        fill="clear"
        size="small"
        class="widget-board-customize"
        data-testid="widgets-customize"
        :aria-label="t('base.widgets.customize')"
        :title="t('base.widgets.customize')"
        :disabled="loading"
        @click="picking = true"
      >
        <HubIcon
          slot="icon-only"
          name="ion:ellipsis-vertical"
        />
      </ion-button>
    </header>

    <ion-list
      v-if="loading"
      inset
      data-testid="widgets-loading"
    >
      <ion-item lines="none">
        <ion-spinner
          slot="start"
          name="crescent"
        />
        <ion-label>{{ $t('base.widgets.loading') }}</ion-label>
      </ion-item>
    </ion-list>

    <InlineFeedback
      v-else-if="failed"
      tone="warning"
      data-testid="widgets-error"
      :heading="$t('base.widgets.loadError')"
    >
      {{ $t('base.widgets.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="widgets-retry"
          @click="refresh"
        >
          {{ $t('base.widgets.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <p
      v-else-if="active.length === 0"
      class="widget-board-empty"
      data-testid="widgets-empty"
    >
      {{ $t('base.widgets.empty') }}
    </p>

    <div
      v-else
      class="widget-board-grid"
    >
      <WidgetPanel
        v-for="widget in active"
        :key="widget.key"
        :widget="widget"
      />
    </div>

    <ion-modal
      :is-open="picking"
      data-testid="widgets-picker"
      :aria-label="t('base.widgets.customize')"
      @did-dismiss="picking = false"
    >
      <ion-header>
        <ion-toolbar>
          <ion-title>{{ $t('base.widgets.customize') }}</ion-title>
          <ion-buttons slot="end">
            <ion-button
              data-testid="widgets-close"
              @click="picking = false"
            >
              {{ $t('base.widgets.close') }}
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
      </ion-header>
      <ion-content class="ion-padding">
        <p
          v-if="catalogue.length === 0"
          class="widget-board-empty"
          data-testid="widgets-none"
        >
          {{ $t('base.widgets.none') }}
        </p>
        <template v-else>
          <ion-list-header>{{ $t('base.widgets.presets') }}</ion-list-header>
          <ion-button
            size="small"
            fill="outline"
            data-testid="widgets-recommended"
            @click="recommended"
          >
            {{ $t('base.widgets.recommended') }}
          </ion-button>

          <ion-list-header>{{ $t('base.widgets.active') }}</ion-list-header>
          <ion-list>
            <ion-reorder-group
              :disabled="false"
              data-testid="widgets-active"
              @ion-item-reorder="onReorder"
            >
              <ion-item
                v-for="widget in active"
                :key="widget.key"
                data-testid="widgets-active-item"
                :data-key="widget.key"
              >
                <ion-label>{{ widget.title }}</ion-label>
                <ion-button
                  slot="end"
                  fill="clear"
                  color="medium"
                  :aria-label="t('base.widgets.remove', { widget: widget.title })"
                  :data-testid="`widgets-remove-${widget.key}`"
                  @click="remove(widget.key)"
                >
                  <HubIcon
                    slot="icon-only"
                    name="ion:close-outline"
                  />
                </ion-button>
                <ion-reorder slot="end" />
              </ion-item>
            </ion-reorder-group>
          </ion-list>

          <ion-list-header v-if="available.length">
            {{ $t('base.widgets.available') }}
          </ion-list-header>
          <ion-list v-if="available.length">
            <ion-item
              v-for="widget in available"
              :key="widget.key"
              data-testid="widgets-available-item"
              :data-key="widget.key"
            >
              <ion-label>
                {{ widget.title }}
                <p>{{ widget.category }}</p>
              </ion-label>
              <ion-button
                slot="end"
                fill="clear"
                :aria-label="t('base.widgets.add', { widget: widget.title })"
                :data-testid="`widgets-add-${widget.key}`"
                @click="add(widget.key)"
              >
                <HubIcon
                  slot="icon-only"
                  name="ion:add-outline"
                />
              </ion-button>
            </ion-item>
          </ion-list>
        </template>
      </ion-content>
    </ion-modal>
  </section>
</template>

<style scoped>
.widget-board-head {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 4px;
}

.widget-board-empty {
  margin: 8px 0 16px;
  color: var(--ion-color-medium);
  text-align: center;
}

/* Four columns on a desk (a small panel takes one, a medium two, a large the row), two on a tablet, one on a phone. */
.widget-board-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.widget-board-grid > :deep(.widget--md) {
  grid-column: span 2;
}

.widget-board-grid > :deep(.widget--lg) {
  grid-column: 1 / -1;
}

@media (max-width: 1099px) {
  .widget-board-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .widget-board-grid > :deep(.widget--md) {
    grid-column: 1 / -1;
  }
}

@media (max-width: 575px) {
  .widget-board-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
