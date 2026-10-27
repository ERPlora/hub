<script setup lang="ts">
// «Start with a business like yours» on the Home (BASE-G131, BASE-F02; PLAN-HUB round 2026-10-21, the old hub's
// BlueprintHeroCard): to who administers the hub, while the business has nothing a template brings (`empty` of
// `base.blueprint.list`, live; a business is born with every app off, round 2026-10-27, and with nothing on it is
// empty), up to four templates, one per kind of business, in the catalogue's order with «Use this one», «See all
// templates» (Settings › Data) and «Not now», remembered on this device. «Use this one» turns on the template's apps
// and loads it in one go (`base.blueprint.import`, never people nor fiscal data) and tells how it went in the card:
// ready, not all of it (what, also an app it could not turn on; «See the report»), not started (why, «Try again») or
// cut halfway (no retry: part may be in). Once seen, it stays until «Continue» or «Not now», though the business is no
// longer empty.
import { InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useLive, useLiveClient } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { sessionChanged } from '../lib/access';
import { cardOutcome, cardTemplates } from '../lib/data';
import { useBaseI18n } from '../lib/i18n';
import type { Template } from '../operations';
import '../home.css';

/** «Not now» on this device (the old hub forgot it on reload: a defect of HUB_SHELL-F26). */
const DISMISSED_KEY = 'hub-blueprint-card-dismissed';
const DATA_PAGE = '/settings#data';

type Outcome =
  | { kind: 'ready' | 'partial' | 'failed'; missing: string[] }
  | { kind: 'not-started'; reason: string; template: Template }
  | { kind: 'cut' };

const { t } = useBaseI18n();
const router = useRouter();
const session = useSession();
const admin = session.can('base.administer_hub');
const client = useLiveClient();
const list = admin ? useLive('base.blueprint.list', {}) : undefined;

const dismissed = ref(localStorage.getItem(DISMISSED_KEY) === '1');
/** Seen once, it stays until closed: importing makes the business non-empty, and the card has to say how it went. */
const seen = ref(false);
const busy = ref<Template | null>(null);
const outcome = ref<Outcome | null>(null);

const offered = computed(() => cardTemplates(list?.data.value?.templates ?? []));
const failed = computed(() => list?.data.value === undefined && list?.status.value === 'error');
watch(
  () => list?.data.value,
  (data) => {
    if (data?.empty && data.templates.length) seen.value = true;
  },
  { immediate: true },
);
const shown = computed(() => admin && !dismissed.value && (seen.value || failed.value));

function close(): void {
  localStorage.setItem(DISMISSED_KEY, '1');
  dismissed.value = true;
}

async function use(template: Template): Promise<void> {
  busy.value = template;
  outcome.value = null;
  try {
    const done = await client.api.call('base.blueprint.import', { template: template.key });
    outcome.value = cardOutcome(done);
    // It turned the template's apps on: the menu and «My apps» are the session's, read it again.
    sessionChanged();
  } catch (error) {
    const failure = error as ApiError;
    outcome.value =
      failure.status > 0 ? { kind: 'not-started', reason: failure.message, template } : { kind: 'cut' };
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <section
    v-if="shown"
    class="home-card blueprint-card"
    data-testid="blueprint-card"
  >
    <h2 class="home-card-title">
      {{ t('base.blueprintCard.title') }}
    </h2>

    <template v-if="failed">
      <InlineFeedback tone="warning">
        {{ t('base.blueprintCard.loadError') }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="blueprint-card-retry"
            @click="list?.refresh()"
          >
            {{ t('base.data.retry.label') }}
          </ion-button>
          <ion-button
            size="small"
            fill="clear"
            @click="close"
          >
            {{ t('base.blueprintCard.later') }}
          </ion-button>
        </template>
      </InlineFeedback>
    </template>

    <div
      v-else-if="outcome"
      data-testid="blueprint-card-outcome"
    >
      <template v-if="outcome.kind === 'ready'">
        <h3 class="blueprint-card-heading">
          {{ t('base.blueprintCard.readyTitle') }}
        </h3>
        <p class="blueprint-card-text">
          {{ t('base.blueprintCard.readyHint') }}
        </p>
      </template>
      <template v-else-if="outcome.kind === 'partial' || outcome.kind === 'failed'">
        <h3 class="blueprint-card-heading">
          {{ outcome.kind === 'partial' ? t('base.blueprintCard.partialTitle') : t('base.blueprintCard.failedTitle') }}
        </h3>
        <p class="blueprint-card-text">
          {{
            outcome.missing.length
              ? t('base.blueprintCard.partialApps', { apps: outcome.missing.join(', ') })
              : t('base.blueprintCard.partialOther')
          }}
        </p>
      </template>
      <template v-else-if="outcome.kind === 'not-started'">
        <h3 class="blueprint-card-heading">
          {{ t('base.blueprintCard.notStartedTitle') }}
        </h3>
        <p class="blueprint-card-text">
          {{ t('base.blueprintCard.notStartedHint', { reason: outcome.reason }) }}
        </p>
      </template>
      <template v-else>
        <h3 class="blueprint-card-heading">
          {{ t('base.blueprintCard.cutTitle') }}
        </h3>
        <p class="blueprint-card-text">
          {{ t('base.blueprintCard.cutHint') }}
        </p>
      </template>
      <div class="blueprint-card-actions">
        <ion-button
          v-if="outcome.kind === 'not-started'"
          data-testid="blueprint-card-again"
          @click="use(outcome.template)"
        >
          {{ t('base.blueprintCard.tryAgain') }}
        </ion-button>
        <ion-button
          v-if="outcome.kind !== 'ready' && outcome.kind !== 'not-started'"
          fill="outline"
          data-testid="blueprint-card-report"
          @click="router.push(DATA_PAGE)"
        >
          {{ t('base.blueprintCard.report') }}
        </ion-button>
        <ion-button
          :fill="outcome.kind === 'ready' ? 'solid' : 'clear'"
          data-testid="blueprint-card-continue"
          @click="close"
        >
          {{ t('base.blueprintCard.continue') }}
        </ion-button>
      </div>
    </div>

    <p
      v-else-if="busy"
      class="blueprint-card-busy"
      data-testid="blueprint-card-busy"
      aria-live="polite"
    >
      <ion-spinner name="crescent" />
      <span>{{ t('base.blueprintCard.preparing', { name: busy.name }) }}</span>
    </p>

    <template v-else>
      <p class="blueprint-card-text">
        {{ t('base.blueprintCard.hint') }}
      </p>
      <ul class="blueprint-card-list">
        <li
          v-for="item in offered"
          :key="item.key"
          class="blueprint-card-template"
          data-testid="blueprint-card-template"
          :data-id="item.key"
        >
          <div class="blueprint-card-template-text">
            <strong>{{ item.name }}</strong>
            <span>{{ item.description }}</span>
          </div>
          <ion-button
            size="small"
            :data-testid="`blueprint-card-use-${item.key}`"
            @click="use(item)"
          >
            {{ t('base.blueprintCard.use') }}
          </ion-button>
        </li>
      </ul>
      <div class="blueprint-card-actions">
        <ion-button
          fill="outline"
          data-testid="blueprint-card-all"
          @click="router.push(DATA_PAGE)"
        >
          {{ t('base.blueprintCard.all') }}
        </ion-button>
        <ion-button
          fill="clear"
          data-testid="blueprint-card-later"
          @click="close"
        >
          {{ t('base.blueprintCard.later') }}
        </ion-button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.blueprint-card-heading {
  margin: 0 0 4px;
  font-size: 1rem;
  font-weight: 600;
}

.blueprint-card-text {
  margin: 0 0 12px;
  color: var(--ion-color-medium);
}

.blueprint-card-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.blueprint-card-template {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--ion-color-step-150, #e4e7ec);
  border-radius: var(--ep-radius-md, 12px);
}

.blueprint-card-template-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.blueprint-card-template-text span {
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}

.blueprint-card-template ion-button {
  align-self: flex-start;
}

.blueprint-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.blueprint-card-busy {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
</style>
