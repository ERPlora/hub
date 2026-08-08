<template>
  <section v-if="visible" class="hero-card" data-testid="hero-card">
    <!-- ── The offer ── kept on screen while the import runs, so the owner can see WHICH template
         they picked instead of a bare spinner. It only leaves when there is a result to read. -->
    <template v-if="run?.phase !== 'finished'">
      <h2 class="hero-title" data-testid="hero-title">{{ t('setup.hero.title') }}</h2>
      <!-- The honest half of «one click = configured», and it is said BEFORE the click: a template
           brings the trade, never the details of THIS business. -->
      <p class="hero-body" data-testid="hero-body">{{ t('setup.hero.body') }}</p>
      <!-- …and the other half nobody was saying (hub#535): it also brings SAMPLE data. Barbería and
           peluquería carry 25-28 appointments with their history and invented customers — on
           purpose, they show how the agenda works — but they are born «today into the future» the
           day the template is generated, so whoever imports it later opens onto an agenda from
           July that is not theirs. Said before the click, and again after with the way out. -->
      <p class="hero-body hero-sample" data-testid="hero-sample">{{ t('setup.hero.sampleData') }}</p>

      <ul class="hero-offers">
        <li v-for="blueprint in offers" :key="blueprint.slug" class="hero-offer" data-testid="hero-offer">
          <div class="hero-offer-text">
            <p class="hero-offer-name">{{ blueprint.name || blueprint.slug }}</p>
            <p v-if="blueprint.description" class="hero-offer-desc">{{ blueprint.description }}</p>
          </div>
          <ion-button
            class="hero-offer-cta"
            size="small"
            :disabled="working"
            :data-slug="blueprint.slug"
            data-testid="hero-use"
            @click="use(blueprint)"
          >
            {{ t('setup.hero.use') }}
          </ion-button>
        </li>
      </ul>

      <div v-if="working" class="hero-working" data-testid="hero-working">
        <ion-spinner name="crescent" />
        <span>{{ t('setup.hero.working', { name: runningName }) }}</span>
      </div>

      <!-- The rest of the catalogue, with its search and its own honest empty-state. The card shows
           four; it is not the catalogue and must not grow into one. -->
      <ion-button
        v-else
        class="hero-more"
        fill="clear"
        size="small"
        router-link="/settings?tab=data"
        router-direction="forward"
        data-testid="hero-more"
      >
        {{ t('setup.hero.more') }}
      </ion-button>
    </template>

    <!-- ── The result ── best-effort engine: it can get most of the way. Each shape says something
         genuinely different about the business, so none of them borrows another one's words. -->
    <div v-else class="hero-outcome" data-testid="hero-outcome">
      <h2 class="hero-title" data-testid="hero-outcome-title">{{ outcomeTitle }}</h2>

      <p v-if="outcome?.kind === 'ready'" class="hero-body" data-testid="hero-done">
        {{ t('setup.hero.readyBody') }}
      </p>
      <!-- Where the sample data is removed (hub#535). It points at the door that ALREADY exists —
           undoing an import, Settings › Data (ADR-0170), which the reset panel itself calls «the
           preferred path, because it is surgical» — instead of promising a button of its own. That
           is also why no relative-date engine was written for the sample bookings. -->
      <p v-if="outcome?.kind === 'ready'" class="hero-body hero-sample" data-testid="hero-sample-undo">
        {{ t('setup.hero.sampleDataUndo') }}
      </p>

      <p v-if="blockedApps.length" class="hero-body hero-blocked" data-testid="hero-blocked">
        {{ t('setup.hero.blocked', { apps: blockedApps.join(', ') }) }}
      </p>
      <p v-if="somethingBroke" class="hero-body hero-failed" data-testid="hero-failed">
        {{ t('setup.hero.failed') }}
      </p>

      <p v-if="outcome?.kind === 'not_started'" class="hero-body" data-testid="hero-not-started">
        {{ t('setup.hero.notStartedBody') }}
      </p>
      <p v-if="outcome?.kind === 'interrupted'" class="hero-body" data-testid="hero-interrupted">
        {{ t('setup.hero.interruptedBody') }}
      </p>
      <!-- The engine's own words, never ours: a reason we paraphrase is a reason nobody can act on. -->
      <p v-if="reason" class="hero-reason" data-testid="hero-reason">{{ reason }}</p>

      <div class="hero-outcome-actions">
        <ion-button size="small" data-testid="hero-continue" @click="dismissed = true">
          {{ t('setup.hero.continue') }}
        </ion-button>
        <!-- Only offered when NOTHING was applied. After an interrupted import, pressing again on
             top of a half-applied business is the wrong next move, and the sentence says so. -->
        <ion-button
          v-if="outcome?.kind === 'not_started'"
          size="small"
          fill="outline"
          data-testid="hero-retry"
          @click="run = null"
        >
          {{ t('setup.hero.retry') }}
        </ion-button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// The hero card of a business with no apps yet (hub#368, PLAN step 10).
//
// A brand new hub is empty by construction, and the way out of that cannot be «install apps one by
// one»: it is starting from the template of a trade, which brings the apps, seeds their catalogue
// and pre-activates the role set of the vertical (hub#354). This card is that door.
//
// **It paints; `lib/blueprint-hero.ts` decides.** When the business counts as empty, which templates
// get offered, what one click asks the engine for and what the result means all live there, pure and
// argued with in a test rather than in a browser.
//
// Three things worth knowing before touching it:
//
// * **It is not the catalogue.** Four templates and a way to the full list. Settings › Data already
//   has the table, the search and the «upload a file» path.
// * **It never claims the business is configured.** A template deliberately travels without the
//   identity of the business it came from, so after the click «your business details» is still
//   pending. The card says that before the click and hands the rest to the checklist below.
// * **It degrades in silence.** A hub with no cloud credential (local, dev) or a catalogue that
//   cannot be reached gets no card and no error banner — the other doors are all still there.
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonSpinner } from '@ionic/vue';

import {
  heroOffers,
  heroSelection,
  heroVisible,
  hubIsEmpty,
  importOutcome,
  mayAdminister,
  type HeroOutcome,
  type HeroRun,
} from '../lib/blueprint-hero';
import { hubSettings } from '../lib/hub-settings';
import { refreshModuleNav } from '../lib/nav';
import {
  downloadBlueprint,
  fetchBlueprintCatalog,
  importBlueprint,
  inspectBlueprint,
  type CatalogBlueprint,
} from '../lib/runtime';
import { user } from '../lib/session';
import type { SetupStatus } from '../lib/setup-status';

const props = defineProps<{
  /** The `hub.setup.status` document the panel read. `null` while there is no answer. */
  status: SetupStatus | null;
}>();

const { t } = useI18n();

const catalog = ref<CatalogBlueprint[]>([]);
const requested = ref<boolean>(false);
const run = ref<HeroRun | null>(null);
const dismissed = ref<boolean>(false);

const canAdminister = computed<boolean>(() => mayAdminister(user.value?.permissions));

const offers = computed<CatalogBlueprint[]>(() =>
  heroOffers(catalog.value, {
    country: hubSettings.value?.country_code,
    language: hubSettings.value?.language,
  }),
);

const visible = computed<boolean>(() =>
  heroVisible({
    canAdminister: canAdminister.value,
    status: props.status,
    offers: offers.value,
    run: run.value,
    dismissed: dismissed.value,
  }),
);

/**
 * The catalogue is asked for ONCE, and only when this session could act on the answer.
 *
 * The panel is loaded on every visit, so a card that fetched on mount would put the SaaS on the
 * critical path of a screen with nothing to ask it. The document arrives asynchronously, hence the
 * watch rather than an `onMounted`: at mount we do not yet know whether the business is empty.
 */
const mayOffer = computed<boolean>(() => canAdminister.value && hubIsEmpty(props.status));
watch(
  mayOffer,
  (yes) => {
    if (yes && !requested.value) void loadOffers();
  },
  { immediate: true },
);

async function loadOffers(): Promise<void> {
  requested.value = true;
  try {
    catalog.value = await fetchBlueprintCatalog();
  } catch {
    // Best-effort, exactly like the catalogue of Settings › Data: a hub with no cloud credential or
    // a network that is down gets no card. A banner here would put OUR breakdown on the first
    // screen of a business that has other ways in.
    catalog.value = [];
  }
}

const working = computed<boolean>(() => run.value?.phase === 'working');
const runningName = computed<string>(() => (run.value?.phase === 'working' ? run.value.name : ''));
const outcome = computed<HeroOutcome | null>(() =>
  run.value?.phase === 'finished' ? run.value.outcome : null,
);

const outcomeTitle = computed<string>(() => {
  const kind = outcome.value?.kind;
  if (kind === 'ready') return t('setup.hero.readyTitle');
  if (kind === 'not_started') return t('setup.hero.notStartedTitle');
  if (kind === 'interrupted') return t('setup.hero.interruptedTitle');
  return t('setup.hero.partialTitle');
});

const blockedApps = computed<string[]>(() =>
  outcome.value?.kind === 'partial' ? outcome.value.blockedApps : [],
);

/** Something actually broke — as opposed to an app that merely has to be added to the plan. */
const somethingBroke = computed<boolean>(
  () =>
    outcome.value?.kind === 'partial' &&
    (outcome.value.failedApps.length > 0 || outcome.value.failedParts > 0),
);

const reason = computed<string>(() =>
  outcome.value?.kind === 'not_started' || outcome.value?.kind === 'interrupted'
    ? outcome.value.reason
    : '',
);

/**
 * The one click.
 *
 * Download → inspect → import, with no screen in between. The two failure paths are kept apart on
 * purpose, because they say different things about the business: everything before the import ran
 * changed nothing at all, and after it we cannot honestly claim that.
 */
async function use(blueprint: CatalogBlueprint): Promise<void> {
  if (working.value) return; // a second press is not a second import
  run.value = { phase: 'working', name: blueprint.name || blueprint.slug };

  let uploadId: string;
  let selection: ReturnType<typeof heroSelection>;
  try {
    // The runtime verifies the sha256 the SaaS announced before handing us a byte (ADR-0015), and
    // the server re-validates the manifest on inspect: a bad bundle is refused WITHOUT effects.
    const inspection = await inspectBlueprint(await downloadBlueprint(blueprint.slug));
    uploadId = inspection.upload_id;
    selection = heroSelection(inspection.manifest);
  } catch (err) {
    run.value = { phase: 'finished', outcome: { kind: 'not_started', reason: messageOf(err) } };
    return; // nothing ran, so nothing changed and nothing needs refreshing
  }

  try {
    run.value = { phase: 'finished', outcome: importOutcome(await importBlueprint(uploadId, selection)) };
  } catch (err) {
    run.value = { phase: 'finished', outcome: { kind: 'interrupted', reason: messageOf(err) } };
  }

  // Both branches refresh: a best-effort import that installed two apps out of three still changed
  // the shell, and an interrupted one may have changed it too. The panel re-reads the checklist off
  // this event, which is how the item this card was born for gets ticked.
  await refreshModuleNav();
  window.dispatchEvent(new CustomEvent('erp:modules-changed'));
}

/** The engine's own words. Ours would be a paraphrase nobody can act on. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
</script>

<style scoped>
/* The hero: the same surface as its siblings on the panel (the launcher and the checklist card),
   with the brand accent doing the «start here» rather than a colour that reads as an alarm. */
.hero-card {
  margin: 0.25rem 0 1rem;
  padding: 1rem 1.1rem;
  border-radius: var(--ok-radius, 12px);
  background: var(--ion-card-background, #fff);
  border: 1px solid var(--ion-color-primary, #0091ce);
}
.hero-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--ion-text-color);
}
.hero-body {
  margin: 0.35rem 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
.hero-blocked {
  color: var(--ion-color-warning-shade, var(--ion-color-warning));
}
.hero-failed {
  color: var(--ion-color-danger-shade, var(--ion-color-danger));
}
.hero-reason {
  margin: 0.35rem 0 0;
  font-size: 0.8125rem;
  font-style: italic;
  color: var(--ion-color-medium);
}

.hero-offers {
  list-style: none;
  margin: 0.85rem 0 0;
  padding: 0;
  display: grid;
  /* Two columns on a desktop, one on a phone: four tiles must never need a scroll to be compared. */
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 0.5rem;
}
.hero-offer {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
  border-radius: var(--ok-radius-sm, 10px);
}
.hero-offer-text {
  flex: 1;
  min-width: 0;
}
.hero-offer-name {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--ion-text-color);
}
.hero-offer-desc {
  margin: 0.1rem 0 0;
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
  /* Two lines at most: a long description must not make one tile twice the height of its sibling. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.hero-offer-cta {
  flex: none;
  white-space: nowrap;
}
.hero-working {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
.hero-more {
  margin-top: 0.5rem;
  --color: var(--ion-color-medium, #92949c);
  text-transform: none;
  font-weight: 600;
}
.hero-outcome-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.85rem;
  flex-wrap: wrap;
}
</style>
