<script setup lang="ts">
// The gallery (WORKBOOK FLOW-F04, F05, F08; the old module's `erp-flows-gallery`): ready-made
// automations by sector, below the list, always. A card opens (one at a time) to say in words what it
// will do, what the owner decides and what it will ask permission to do, and why. «Use this one»
// creates it paused and with no permission (`flow.flow.create`) and hands it to the editor. A card the
// business already has says how it is («Active», «Paused», «Unfinished») and offers «See it»; one whose
// event another automation already starts on warns. A card whose apps are not in this business is
// hidden and the apps are named below. A link (`?template=<id>`) opens a card and brings it into view.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, nextTick, ref, shallowRef, watch } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import { wording } from '../lib/refusal';
import { toPayload } from '../lib/document';
import { actionLabel, statePill } from '../lib/phrasing';
import {
  alreadyFires,
  buildDocument,
  cardGrants,
  cardName,
  existingFor,
  type FlowTemplate,
  missingApps,
  runnable,
  type Sector,
  templatesOf,
} from '../lib/templates';
import type { CatalogOut, FlowOut } from '../operations';

const props = defineProps<{ catalog: CatalogOut | null; flows: readonly FlowOut[]; openCard: string | null }>();
const emit = defineEmits<{ created: [flow: FlowOut]; openFlow: [flow: FlowOut]; guide: [] }>();
const phrasing = usePhrasing();
const create = useCommand('flow.flow.create');

const SECTORS: readonly Sector[] = ['any', 'beauty', 'food'];
const open = ref<string | null>(null);
const errors = shallowRef<Record<string, ApiError>>({});

const sectors = computed(() =>
  SECTORS.map((sector) => ({ sector, cards: props.catalog ? templatesOf(sector).filter((card) => runnable(card, props.catalog!)) : [] })).filter(
    (group) => group.cards.length,
  ),
);

const hidden = computed(() => {
  if (!props.catalog) return '';
  const apps = missingApps([...SECTORS.flatMap((sector) => templatesOf(sector))], props.catalog);
  if (!apps.length) return '';
  const names = apps.map((app) => (phrasing.value.te(`flow.gallery.apps.${app}`) ? phrasing.value.t(`flow.gallery.apps.${app}`) : app));
  return phrasing.value.t('flow.gallery.hidden', { apps: new Intl.ListFormat(phrasing.value.locale, { type: 'conjunction' }).format(names) });
});

watch(
  () => [props.openCard, props.catalog] as const,
  async ([id]) => {
    if (!id || !sectors.value.some((group) => group.cards.some((card) => card.id === id))) return;
    open.value = id;
    await nextTick();
    document.querySelector(`[data-testid="flow-card-${id}"]`)?.scrollIntoView?.({ block: 'center' });
  },
  { immediate: true },
);

function toggle(card: FlowTemplate): void {
  open.value = open.value === card.id ? null : card.id;
}

async function use(card: FlowTemplate): Promise<void> {
  errors.value = { ...errors.value, [card.id]: undefined as unknown as ApiError };
  try {
    const flow = await create.run(toPayload(buildDocument(card, phrasing.value)));
    emit('created', flow);
  } catch (failure) {
    errors.value = { ...errors.value, [card.id]: failure as ApiError };
  }
}

function reason(operation: string): string {
  const key = `flow.gallery.reasons.${operation.replaceAll('.', '__')}`;
  return phrasing.value.te(key) ? phrasing.value.t(key) : '';
}

const T = (card: FlowTemplate, key: string): string => phrasing.value.t(`flow.gallery.cards.${card.id}.${key}`);
</script>

<template>
  <section
    class="flow-gallery"
    data-testid="flow-gallery"
  >
    <div class="flow-gallery__head">
      <p class="flow-gallery__intro">
        {{ $t('flow.gallery.intro') }}
      </p>
      <IonButton
        size="small"
        fill="clear"
        mode="md"
        data-testid="flow-gallery-guide"
        @click="emit('guide')"
      >
        <HubIcon name="ion:help-circle-outline" />{{ $t('flow.gallery.guide') }}
      </IonButton>
    </div>
    <div
      v-for="group in sectors"
      :key="group.sector"
      class="flow-gallery__sector"
      :data-testid="`flow-gallery-sector-${group.sector}`"
    >
      <h3 class="flow-gallery__title">
        {{ $t(`flow.gallery.sectors.${group.sector}`) }}
      </h3>
      <div class="flow-gallery__grid">
        <article
          v-for="card in group.cards"
          :key="card.id"
          class="flow-gallery__card"
          :class="{ 'flow-gallery__card--open': open === card.id }"
          :data-testid="`flow-card-${card.id}`"
        >
          <button
            type="button"
            class="flow-gallery__open"
            :aria-expanded="open === card.id ? 'true' : 'false'"
            :data-testid="`flow-card-open-${card.id}`"
            @click="toggle(card)"
          >
            <HubIcon
              class="flow-gallery__icon"
              :name="card.icon"
            />
            <span class="flow-gallery__text">
              <strong>{{ cardName(card, phrasing) }}</strong>
              <span class="flow-gallery__summary">{{ T(card, 'summary') }}</span>
            </span>
            <StatusPill
              v-if="existingFor(card, flows, phrasing)"
              v-bind="statePill(existingFor(card, flows, phrasing)!, phrasing)"
            />
          </button>
          <div
            v-if="open === card.id"
            class="flow-gallery__panel"
            :data-testid="`flow-card-panel-${card.id}`"
          >
            <p>{{ T(card, 'plain') }}</p>
            <h4>{{ $t('flow.gallery.decide') }}</h4>
            <p v-if="card.blank">
              <strong>{{ T(card, 'blank') }}</strong> — {{ T(card, 'blankHint') }}
            </p>
            <p v-else>
              {{ $t('flow.gallery.nothingToDecide') }}
            </p>
            <h4>{{ $t('flow.gallery.asks') }}</h4>
            <ul>
              <li
                v-for="operation in cardGrants(card)"
                :key="operation"
              >
                <strong>{{ actionLabel(operation, catalog, phrasing) }}</strong>
                <template v-if="reason(operation)">
                  — {{ reason(operation) }}
                </template>
              </li>
            </ul>
            <InlineFeedback
              v-if="alreadyFires(card, flows)"
              tone="warning"
            >
              {{ $t('flow.gallery.alreadyFires', { name: alreadyFires(card, flows)!.name }) }}
            </InlineFeedback>
            <InlineFeedback
              v-if="errors[card.id]"
              tone="danger"
              :data-testid="`flow-card-error-${card.id}`"
            >
              {{ wording(errors[card.id], $t('flow.errors.action')) }}
            </InlineFeedback>
            <div class="flow-gallery__actions">
              <IonButton
                v-if="existingFor(card, flows, phrasing)"
                mode="md"
                :data-testid="`flow-card-see-${card.id}`"
                @click="emit('openFlow', existingFor(card, flows, phrasing)!)"
              >
                {{ $t('flow.gallery.see') }}
              </IonButton>
              <IonButton
                mode="md"
                :fill="existingFor(card, flows, phrasing) ? 'outline' : 'solid'"
                :disabled="create.pending.value"
                :data-testid="`flow-card-use-${card.id}`"
                @click="use(card)"
              >
                {{ $t('flow.gallery.use') }}
              </IonButton>
              <span class="flow-gallery__hint">{{ $t('flow.gallery.useHint') }}</span>
            </div>
          </div>
        </article>
      </div>
    </div>
    <p
      v-if="hidden"
      class="flow-gallery__hint"
      data-testid="flow-gallery-hidden"
    >
      {{ hidden }}
    </p>
  </section>
</template>

<style scoped>
.flow-gallery {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.flow-gallery__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.flow-gallery__intro {
  margin: 0;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-gallery__title {
  margin: 0.25rem 0 0.4rem;
  font-size: 0.95rem;
  font-weight: 600;
}
.flow-gallery__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 18rem), 1fr));
  gap: 0.6rem;
  align-items: start;
}
.flow-gallery__card {
  border: 1px solid var(--ep-border, #d7d5cc);
  border-radius: 14px;
  background: var(--ep-surface, var(--ion-card-background, #fff));
  overflow: hidden;
}
.flow-gallery__card--open {
  grid-column: 1 / -1;
}
.flow-gallery__open {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  width: 100%;
  min-height: 3rem;
  padding: 0.7rem;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.flow-gallery__icon {
  flex: 0 0 auto;
  font-size: 1.4rem;
  color: var(--ion-color-primary);
}
.flow-gallery__text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  flex: 1 1 auto;
  min-width: 0;
}
.flow-gallery__summary,
.flow-gallery__hint {
  font-size: 0.85rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-gallery__panel {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0 0.9rem 0.9rem;
}
.flow-gallery__panel p,
.flow-gallery__panel h4,
.flow-gallery__panel ul {
  margin: 0;
}
.flow-gallery__panel h4 {
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-gallery__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
</style>
