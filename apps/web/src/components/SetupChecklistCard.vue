<template>
  <!-- No document, or a document with nothing in it, paints NO card: an empty answer is silence,
       and a card that celebrates silence is the false «done» this subsystem exists to avoid. -->
  <section v-if="!view.empty" class="setup-card" data-testid="setup-card">
    <header class="setup-card-head">
      <div class="setup-card-heading">
        <h2 class="setup-card-title">
          {{ view.complete ? t('setup.completeTitle') : t('setup.title') }}
        </h2>
        <!-- The counters are the QUERY's, never a count of the rows that fit on screen. -->
        <p class="setup-card-progress" data-testid="setup-progress">
          {{ t('setup.progress', { done: view.done, total: view.total }) }}
        </p>
      </div>
      <ion-progress-bar
        class="setup-card-meter"
        :value="fraction"
        :color="view.complete ? 'success' : 'primary'"
        data-testid="setup-meter"
      />
    </header>

    <p v-if="view.complete" class="setup-card-complete" data-testid="setup-complete">
      {{ t('setup.completeBody') }}
    </p>

    <ul v-if="view.rows.length" class="setup-rows">
      <li
        v-for="item in view.rows"
        :key="item.key"
        class="setup-row"
        :class="`setup-row--${item.state}`"
        :data-testid="`setup-item-${item.key}`"
        :data-state="item.state"
        :data-level="item.level"
      >
        <HubIcon class="setup-row-icon" :name="rowIcon(item)" />
        <div class="setup-row-text">
          <p class="setup-row-title">{{ titleOf(item) }}</p>
          <p v-if="descriptionOf(item)" class="setup-row-desc">{{ descriptionOf(item) }}</p>
          <!-- A row with no button says WHY out loud. One that offers nothing and explains nothing
               reads as a broken product instead of as a job that belongs to somebody else. -->
          <p v-if="noteOf(item)" class="setup-row-note" :data-testid="`setup-note-${item.key}`">
            {{ noteOf(item) }}
          </p>
        </div>
        <ok-status-pill class="setup-row-pill" :tone="pillTone(item)" :label="pillLabel(item)" dot />
        <!-- ONLY a pending item THIS session can do gets a way in. The screen of an `unavailable`
             hands them our breakdown as a chore they cannot finish; the screen of a wall that is
             not theirs (hub#435) refuses them on arrival. -->
        <ion-button
          v-if="isActionable(item)"
          class="setup-row-cta"
          size="small"
          fill="outline"
          :router-link="item.route"
          router-direction="forward"
          :data-testid="`setup-action-${item.key}`"
        >
          {{ t('setup.configure') }}
        </ion-button>
      </li>
    </ul>

    <footer class="setup-card-foot">
      <ion-button
        v-if="view.hidden > 0 || expanded"
        fill="clear"
        size="small"
        class="setup-card-toggle"
        data-testid="setup-toggle"
        @click="expanded = !expanded"
      >
        {{ expanded ? t('setup.viewLess') : t('setup.viewAll') }}
      </ion-button>
      <ion-button size="small" class="setup-card-review" data-testid="setup-review" @click="emit('review')">
        <HubIcon slot="start" name="sparkles-outline" />
        {{ t('setup.review') }}
      </ion-button>
    </footer>
  </section>
</template>

<script setup lang="ts">
// The configuration card of the panel (hub#372) — the first of the three surfaces of
// `hub.setup.status` (ADR-0224/0227; `architecture/hub/setup-status.md`).
//
// The card **paints**: it does not sort, does not filter and evaluates nothing. The list arrives
// already ordered and already filtered by country and by permission; deciding again here is the
// divergence hub#369 closed. All this layer decides is the SHAPE of saying each state, and one
// rule is hard: an `unavailable` must not look like a pending (that would send the user to a
// screen where nothing can be done) nor like a done (the hub still cannot sell).
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonProgressBar } from '@ionic/vue';

import HubIcon from './HubIcon.vue';
import {
  LEVEL_LEGAL,
  LEVEL_RECOMMENDED,
  STATE_DONE,
  STATE_PENDING,
  STATE_UNAVAILABLE,
  checklistView,
  isActionable,
  isInherited,
  type SetupItem,
  type SetupStatus,
} from '../lib/setup-status';

const props = withDefaults(
  defineProps<{
    /** The document `hub.setup.status` answered. `null` until there is an answer. */
    status: SetupStatus | null;
    /**
     * Keys ANOTHER card on the same screen already offers (decision 1 of the plan: in the panel the
     * checklist starts at item 2 while the apps card is visible). It does not filter the list: the
     * item still counts and `/setup` still shows it.
     */
    alreadyOnScreen?: readonly string[];
    /** Starts expanded (used by `/setup`, where there is nothing else to look at). */
    expandedByDefault?: boolean;
  }>(),
  { alreadyOnScreen: () => [], expandedByDefault: false },
);

const emit = defineEmits<{ (e: 'review'): void }>();

const { t, te } = useI18n();

const expanded = ref<boolean>(props.expandedByDefault);

const view = computed(() =>
  checklistView(props.status, { expanded: expanded.value, alreadyOnScreen: props.alreadyOnScreen }),
);

/** Progress 0-1. A hub with no items does not divide by zero: there is no meter to fill. */
const fraction = computed<number>(() => (view.value.total > 0 ? view.value.done / view.value.total : 0));

/**
 * The item's title. A CORE item's key is also its i18n key; the English `title` travelling in the
 * answer is the fallback — and it is all there is for a module item, whose `title` the runtime does
 * not localize yet (`setup-status.md` §7). A raw key is never painted.
 */
function titleOf(item: SetupItem): string {
  return translated(`setup.items.${item.key}.title`) || item.title || item.key;
}

function descriptionOf(item: SetupItem): string {
  return translated(`setup.items.${item.key}.description`) || item.description;
}

function translated(key: string): string {
  return te(key) ? t(key) : '';
}

/** The icon says the state before you read a word; the item's own is used only when there is work. */
function rowIcon(item: SetupItem): string {
  if (item.state === STATE_DONE) return 'checkmark-circle-outline';
  if (item.state === STATE_UNAVAILABLE) return 'cloud-offline-outline';
  return item.icon || 'settings-outline';
}

/**
 * The pill's tone. Four different answers for four different situations: done (green), broken (a
 * notice blue, not a task colour), ⛔ (red: the runtime rejects it) and 🔴/🟡.
 */
function pillTone(item: SetupItem): string {
  if (item.state === STATE_DONE) return 'success';
  if (item.state === STATE_UNAVAILABLE) return 'info';
  if (item.level === LEVEL_LEGAL) return 'danger';
  if (item.level === LEVEL_RECOMMENDED) return 'neutral';
  return 'warning';
}

/**
 * Why this row has no button — empty when it does have one.
 *
 * A row without a call to action and without a sentence is the worst of the three: the user reads
 * «pending» and finds nothing to press. The two reasons are different and must not be said alike —
 * `unavailable` is **ours** to fix and nothing is expected of anybody in the hub; a wall that is not
 * theirs (hub#435) is somebody else's to type, and saying WHO turns a dead end into an errand.
 */
function noteOf(item: SetupItem): string {
  if (item.state === STATE_UNAVAILABLE) return t('setup.unavailableHint');
  if (item.state === STATE_PENDING && !isActionable(item)) return t('setup.delegatedHint');
  // Done, but by a template (hub#536): true, and worth a second look — a bar has its own room and
  // its own prices. It is an invitation, never a pending task: the counters do not move.
  if (isInherited(item)) return t('setup.inheritedHint');
  return '';
}

function pillLabel(item: SetupItem): string {
  if (item.state === STATE_DONE) return t('setup.doneLabel');
  if (item.state === STATE_UNAVAILABLE) return t('setup.unavailableLabel');
  if (item.level === LEVEL_LEGAL) return t('setup.levelLegal');
  if (item.level === LEVEL_RECOMMENDED) return t('setup.levelRecommended');
  return t('setup.levelFunctional');
}
</script>

<style scoped>
/* The configuration card: the way into `/setup` and a progress meter at once. Neutral tone with
   the brand accent — this is not an error nor an alarm, it is work still to do. */
.setup-card {
  margin: 0.25rem 0 1rem;
  padding: 1rem 1.1rem;
  border-radius: var(--ok-radius, 12px);
  background: var(--ion-card-background, #fff);
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
}
.setup-card-head {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.setup-card-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.setup-card-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--ion-text-color);
}
.setup-card-progress {
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--ion-color-medium);
}
.setup-card-meter {
  --border-radius: 999px;
  height: 6px;
}
.setup-card-complete {
  margin: 0.75rem 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}

.setup-rows {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.setup-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0;
  border-top: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.06));
  flex-wrap: wrap;
}
.setup-row:first-child {
  border-top: none;
}
/* Each state carries its own visual weight: what is done fades, what is broken reads apart from a
   task (it cannot be attempted) and what is pending keeps full contrast. */
.setup-row--done {
  opacity: 0.62;
}
.setup-row--unavailable {
  background: color-mix(in srgb, var(--ion-color-medium, #92949c) 6%, transparent);
  border-radius: var(--ok-radius-sm, 8px);
  padding-inline: 0.5rem;
}
.setup-row-icon {
  font-size: 1.35rem;
  flex: none;
  color: var(--ion-color-medium);
}
.setup-row--done .setup-row-icon {
  color: var(--ion-color-success, #2dd55b);
}
.setup-row-text {
  flex: 1;
  min-width: 12rem;
}
.setup-row-title {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.setup-row--done .setup-row-title {
  font-weight: 500;
}
.setup-row-desc,
.setup-row-note {
  margin: 0.1rem 0 0;
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
}
.setup-row-note {
  font-style: italic;
}
.setup-row-pill {
  flex: none;
  font-size: 0.75rem;
}
.setup-row-cta {
  flex: none;
  white-space: nowrap;
}

.setup-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
.setup-card-toggle {
  --color: var(--ion-color-medium, #92949c);
  text-transform: none;
  font-weight: 600;
}
.setup-card-review {
  text-transform: none;
}
@media (max-width: 540px) {
  .setup-card-review {
    width: 100%;
  }
}
</style>
