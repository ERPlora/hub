<script setup lang="ts">
// «Finish setting up your business» (BASE-G22, BASE-G130, BASE-G164; hub#372, ADR-0063): ONE live read of
// `base.setup.status` — the platform's steps and the modules', already ordered and filtered by country,
// vertical and permission on the server — painted as it comes. «Set up» only where the step's screen exists
// and the person can do it; a ⛔ only an administrator can do says who can. Folded: ⛔ and 🔴 in sight, at
// most 5 rows (2 on a phone); «Your apps» is the «My apps» card's, so the fold does not repeat it. While something is
// left, «Ask the assistant» opens its panel on the setup (BASE-G121).
import { InlineFeedback, StatusPill, type StatusPillTone } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonProgressBar, IonSkeletonText } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useRouter } from 'vue-router';

import type { SetupItem } from '../operations';
import { useAssistant } from '../lib/assistant';
import { checklistView, MAX_VISIBLE_ROWS, PHONE_MAX_VISIBLE_ROWS } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import { usePhone } from '../lib/phone';
import '../home.css';

/** What the «My apps» card above already offers. */
const ALREADY_ON_SCREEN = ['base.apps'];

const { t } = useBaseI18n();
const router = useRouter();
const phone = usePhone();
const expanded = ref(false);
const assistant = useAssistant();
const { data, status, refresh } = useLive('base.setup.status', {});

const view = computed(() =>
  checklistView(data.value, {
    expanded: expanded.value,
    maxRows: phone.value ? PHONE_MAX_VISIBLE_ROWS : MAX_VISIBLE_ROWS,
    alreadyOnScreen: ALREADY_ON_SCREEN,
  }),
);
const loading = computed(() => data.value === undefined && status.value !== 'error');
const failed = computed(() => data.value === undefined && status.value === 'error');

/** A route the router has: one that falls on the 404 offers nothing. */
const reachable = (route: string) => route !== '' && router.resolve(route).name !== 'not-found';
const canConfigure = (item: SetupItem) => item.state === 'pending' && item.actionable && reachable(item.route);

function pill(item: SetupItem): { tone: StatusPillTone; label: string } {
  if (item.state === 'done') return { tone: 'success', label: t('base.setup.done') };
  if (item.state === 'unavailable') return { tone: 'neutral', label: t('base.setup.unavailable') };
  if (item.level === 'legal') return { tone: 'danger', label: t('base.setup.level.legal') };
  if (item.level === 'recommended') return { tone: 'info', label: t('base.setup.level.recommended') };
  return { tone: 'warning', label: t('base.setup.level.functional') };
}

function note(item: SetupItem): string {
  if (item.state === 'unavailable') return t('base.setup.unavailableHint');
  if (item.state === 'pending' && !item.actionable) return t('base.setup.delegatedHint');
  return '';
}
</script>

<template>
  <section
    v-if="loading"
    class="home-card setup-card"
    data-testid="setup-card"
    aria-busy="true"
  >
    <h2 class="home-card-title">
      {{ $t('base.setup.title') }}
    </h2>
    <ion-skeleton-text
      v-for="n in 3"
      :key="n"
      animated
      class="setup-skeleton"
    />
  </section>

  <InlineFeedback
    v-else-if="failed"
    class="home-card"
    tone="warning"
    data-testid="setup-error"
    :heading="$t('base.setup.loadError')"
  >
    {{ $t('base.setup.loadErrorBody') }}
    <template #actions>
      <ion-button
        size="small"
        fill="outline"
        data-testid="setup-retry"
        @click="refresh"
      >
        {{ $t('base.setup.retry') }}
      </ion-button>
    </template>
  </InlineFeedback>

  <section
    v-else-if="!view.empty"
    class="home-card setup-card"
    data-testid="setup-card"
    aria-busy="false"
  >
    <header class="setup-head">
      <h2 class="home-card-title">
        {{ view.complete ? $t('base.setup.completeTitle') : $t('base.setup.title') }}
      </h2>
      <span
        class="setup-progress"
        data-testid="setup-progress"
      >{{ $t('base.setup.progress', { done: view.done, total: view.total }) }}</span>
    </header>
    <ion-progress-bar
      class="setup-bar"
      :value="view.total > 0 ? view.done / view.total : 0"
    />
    <p
      v-if="view.complete"
      class="setup-complete"
      data-testid="setup-complete"
    >
      {{ $t('base.setup.completeBody') }}
    </p>

    <ul
      v-if="view.rows.length"
      class="setup-rows"
    >
      <li
        v-for="item in view.rows"
        :key="item.key"
        class="setup-row"
        data-testid="setup-row"
        :data-key="item.key"
      >
        <HubIcon
          class="setup-row-icon"
          :name="item.icon"
        />
        <div class="setup-row-body">
          <p class="setup-row-title">
            {{ item.title }}
          </p>
          <p
            v-if="item.description"
            class="setup-row-desc"
          >
            {{ item.description }}
          </p>
          <p
            v-if="note(item)"
            class="setup-row-note"
            :data-testid="`setup-note-${item.key}`"
          >
            {{ note(item) }}
          </p>
        </div>
        <div class="setup-row-end">
          <StatusPill
            v-bind="pill(item)"
            data-testid="setup-pill"
          />
          <ion-button
            v-if="canConfigure(item)"
            size="small"
            fill="outline"
            :data-testid="`setup-configure-${item.key}`"
            @click="router.push(item.route)"
          >
            {{ $t('base.setup.configure') }}
          </ion-button>
        </div>
      </li>
    </ul>

    <footer
      v-if="view.hidden > 0 || expanded || !view.complete"
      class="setup-foot"
    >
      <ion-button
        v-if="view.hidden > 0 || expanded"
        size="small"
        fill="clear"
        class="setup-toggle"
        data-testid="setup-toggle"
        @click="expanded = !expanded"
      >
        {{ expanded ? $t('base.setup.viewLess') : $t('base.setup.viewAll') }}
      </ion-button>
      <!-- BASE-G121 (gh:hub#373): the setup with the assistant; each step keeps its own «Set up» if it is down. -->
      <ion-button
        v-if="!view.complete"
        size="small"
        class="setup-review"
        data-testid="setup-review"
        @click="assistant.openForSetup()"
      >
        <HubIcon
          slot="start"
          name="ion:sparkles-outline"
        />
        {{ $t('base.assistant.setup.ask') }}
      </ion-button>
    </footer>
  </section>
</template>

<style scoped>
.setup-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}

.setup-review {
  margin-inline-start: auto;
}

.setup-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 12px;
}

.setup-progress {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--ion-color-medium);
}

.setup-bar {
  height: 6px;
  margin: 4px 0 8px;
  border-radius: 3px;
}

.setup-complete {
  margin: 8px 0 0;
  color: var(--ion-color-medium);
}

.setup-rows {
  margin: 0;
  padding: 0;
  list-style: none;
}

.setup-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--ion-color-step-100, #eaecf0);
}

.setup-row:last-child {
  border-bottom: 0;
}

.setup-row-icon {
  font-size: 20px;
  color: var(--ion-color-medium);
}

.setup-row-title {
  margin: 0;
  font-weight: 600;
}

.setup-row-desc,
.setup-row-note {
  margin: 2px 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}

.setup-row-note {
  font-style: italic;
}

.setup-row-end {
  display: flex;
  align-items: center;
  gap: 8px;
}

.setup-skeleton {
  height: 40px;
  margin: 8px 0;
}

/* On a phone the pill and the button go under the text, as the old hub's. */
@media (max-width: 767px) {
  .setup-row {
    grid-template-columns: auto minmax(0, 1fr);
    align-items: start;
  }

  .setup-row-end {
    grid-column: 2;
    flex-wrap: wrap;
  }
}
</style>
