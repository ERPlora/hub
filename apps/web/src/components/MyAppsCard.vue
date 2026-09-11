<template>
  <section class="apps-card" data-testid="apps-card">
    <header class="apps-card-head">
      <h2 class="apps-card-title">{{ t('topbar.apps') }}</h2>
    </header>

    <!-- A hub with no apps is not a hub with an empty grid: the ＋ tile below is the way out, and
         this line says what the grid will hold. It never names a «module» — that word asks a bar
         owner to understand our architecture before serving a coffee.

         Only when the runtime has ANSWERED and said so (hub#770). While the list is on its way, and
         when the request failed, this line would be a claim about the hub that nobody checked: a
         restaurant with twelve apps was told it had none for the three seconds of a cold load, and
         again whenever a second device displaced its session. Silence is the honest state there —
         the ＋ tile below is still true. -->
    <p v-if="display === 'empty'" class="apps-card-empty" data-testid="apps-empty">
      {{ t('dashboard.appsEmpty') }}
    </p>

    <!-- …and when there is nothing to show because the ASKING failed, that has to be said OUT LOUD
         (hub#894). hub#770 stopped the card from lying here; what it left was silence, and next to a
         grid whose only tile is «＋ Add apps», silence still reads as «this hub is empty». A real hub
         with twelve modules registered went two surfaces deep like that and its owner's only
         available move was to go install what they already had. A failure nobody can see is also a
         failure nobody reports: that hub's 401 sat in the runtime log the whole time.

         Only when there is nothing on screen — rows beat this message like they beat every other
         one (hub#770, «data wins»). -->
    <p v-else-if="display === 'error'" class="apps-card-error" data-testid="apps-error" role="alert">
      {{ t('dashboard.appsLoadError') }}
    </p>

    <!-- hub#1722 — and SILENCE was not enough either.
         hub#770 stopped the card from lying while it asked; what it left behind is a grid whose
         only tile is «＋ Add apps», which is pixel for pixel the empty hub. On a hub in PRE with
         twenty-one apps installed that state held for FIFTEEN seconds, and the only thing anyone
         looking at the panel could read was «this business has nothing installed». Not saying the
         wrong sentence is not the same as saying the right one.
         So while there is nothing to show yet the grid holds the SHAPE of what is coming — the
         pattern of every launcher, and the one this shell already uses one surface away for a
         module screen (hub#1169, `ModuleView.vue`). The tiles are decorative (`aria-hidden`); the
         sentence rides on the grid itself with `role="status"` + `aria-busy`, for whoever is not
         looking at the screen. -->
    <ul
      class="apps-grid"
      :data-testid="display === 'loading' ? 'apps-skeleton' : undefined"
      :role="display === 'loading' ? 'status' : undefined"
      :aria-busy="display === 'loading' ? 'true' : undefined"
      :aria-label="display === 'loading' ? t('dashboard.appsLoading') : undefined"
    >
      <li
        v-for="cell in display === 'loading' ? SKELETON_TILE_COUNT : 0"
        :key="`skeleton-${cell}`"
        class="apps-grid-cell"
      >
        <!-- `:animated="true"` and not a bare `animated`: written bare, Vue hands the wrapper the
             empty string rather than a boolean, so «is this skeleton moving?» could only be asked
             of a rendered Ionic element and never of the component itself. A STILL skeleton reads
             as broken, not as loading, so that has to be assertable. -->
        <ion-skeleton-text
          :animated="true"
          class="apps-tile-skeleton"
          data-testid="apps-skeleton-tile"
          aria-hidden="true"
        />
      </li>
      <li v-for="app in gridView.tiles" :key="app.path" class="apps-grid-cell">
        <ion-button
          class="apps-tile"
          fill="clear"
          :router-link="app.path"
          router-direction="forward"
          data-testid="apps-tile"
          :data-path="app.path"
          @click="remember(app.path)"
        >
          <span class="apps-tile-body">
            <HubIcon class="apps-tile-icon" :name="app.icon" />
            <!-- `title`: a name that does not fit the tile is TRUNCATED (hub#1268), so the full one
                 has to stay reachable — the native tooltip is what every launcher uses for this. -->
            <span class="apps-tile-label" :title="app.label">{{ app.label }}</span>
          </span>
        </ion-button>
      </li>
      <!-- The fold on a phone (hub#1197): the grid stopped growing to fit every installed app —
           what does not fit behind the row budget (`lib/apps-grid.ts`) gets one tile, not a taller
           card, same door the ＋ tile below already opens (`/apps`). Never present off the phone:
           there the grid still shows everything, as it always has. -->
      <li v-if="gridView.hidden > 0" class="apps-grid-cell">
        <ion-button
          class="apps-tile apps-tile--view-all"
          fill="clear"
          router-link="/apps"
          router-direction="forward"
          data-testid="apps-view-all"
        >
          <span class="apps-tile-body">
            <HubIcon class="apps-tile-icon" name="apps-outline" />
            <span class="apps-tile-label">{{ t('dashboard.appsViewAll') }}</span>
          </span>
        </ion-button>
      </li>
      <!-- ＋ Add apps: ALWAYS last and always present. It offers more, it does not compete with
           what is installed, and it is the only tile an empty hub has. -->
      <li class="apps-grid-cell">
        <ion-button
          class="apps-tile apps-tile--add"
          fill="clear"
          router-link="/apps"
          router-direction="forward"
          data-testid="apps-add"
        >
          <span class="apps-tile-body">
            <HubIcon class="apps-tile-icon" name="add-outline" />
            <span class="apps-tile-label" :title="t('dashboard.appsAdd')">{{
              t('dashboard.appsAdd')
            }}</span>
          </span>
        </ion-button>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
// «My apps» — the launcher of the panel (hub#367, PLAN step 10).
//
// ERPlora is an ERP, not a till: what the owner has in front are THEIR apps. The rest of the panel
// is a report, and a report needs a history the hub does not have on day one — which is why this
// card goes FIRST and cannot be removed. It is the only widget that works with zero data.
//
// The card only PAINTS: the list of installed apps arrives from the runtime (`moduleNav`, the same
// source the topbar launcher reads) and the order is `orderAppsByUsage` — the user's own history,
// never a ranking of ours.
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonSkeletonText } from '@ionic/vue';

import HubIcon from './HubIcon.vue';
import { orderAppsByUsage, recordAppLaunch } from '../lib/app-usage';
import { appsGridView, SKELETON_TILE_COUNT } from '../lib/apps-grid';
import { listDisplay, type ListLoadState } from '../lib/list-load-state';
import type { ModuleNavItem } from '../lib/nav';
import { isPhoneViewport } from '../lib/viewport';

const props = withDefaults(
  defineProps<{
    /** Installed apps, as the runtime reported them (`/api/navigation` → `moduleNav`). */
    apps?: readonly ModuleNavItem[];
    /**
     * What the caller KNOWS about that list (hub#770) — `moduleNavState`.
     *
     * `ready` by default: a caller that hands over a list and says nothing else is saying «this is
     * the list». The panel passes the real state, because there the first paint happens before any
     * request has finished.
     */
    state?: ListLoadState;
  }>(),
  { apps: () => [], state: 'ready' },
);

const { t } = useI18n();

// Ordered once per render of the card: re-sorting while a finger is on its way to a tile would move
// the target out from under it.
const ordered = computed<ModuleNavItem[]>(() => orderAppsByUsage(props.apps));

/** Which of «apps / still asking / it failed / genuinely none» this card is looking at (hub#770). */
const display = computed(() => listDisplay(props.state, ordered.value.length));

/**
 * What the grid actually paints (hub#1197): on a phone, a long list folds behind «View all apps»
 * instead of growing the card to fit every installed app — see `lib/apps-grid.ts` for the cap.
 */
const gridView = computed(() => appsGridView(ordered.value, isPhoneViewport.value));

/** Opening an app is what counts it — the catalogue tile is not an app and never enters the rank. */
function remember(path: string): void {
  recordAppLaunch(path);
}
</script>

<style scoped>
/* The launcher card: same surface as the configuration card (they are siblings on the panel), with
   the grid doing the talking instead of a header full of chrome. */
.apps-card {
  margin: 0.25rem 0 1rem;
  padding: 1rem 1.1rem;
  border-radius: var(--ok-radius, 12px);
  background: var(--ion-card-background, #fff);
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
}
.apps-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.apps-card-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--ion-text-color);
}
.apps-card-empty {
  margin: 0.4rem 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
/* Same line, said in the danger tone: this one is about US failing, not about the hub being new. */
.apps-card-error {
  margin: 0.4rem 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-danger);
}

/* Auto-fill grid: 4-5 tiles per row on a desktop, 3 on a phone (measured in Chromium — that already
   holds with no media query at 390px, hub#1268). */
.apps-grid {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(5.5rem, 1fr));
  gap: 0.5rem;
}
/* hub#1197 — pinned to a FIXED column count on a phone, where `auto-fill` alone did not hold: at
   390px it already gives 3, but nothing stopped it drifting to 4-5 as the viewport approaches
   540px. `lib/apps-grid.ts` folds the list to a CELL BUDGET (`PHONE_GRID_COLUMNS ×
   PHONE_VISIBLE_ROWS`, reserving a cell each for the ＋ Add apps tile and the folding «view all»
   tile) so the whole card never exceeds 2 rows — a budget only holds if the column count it was
   computed for is the one that actually renders. The threshold matches `isPhoneViewport`
   (`lib/viewport.ts`) and the setup card's own breakpoint, so both cards fold at the same width. */
@media (max-width: 540px) {
  .apps-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
.apps-grid-cell {
  display: flex;
  /* `min-width: 0` on the cell and on the tile (hub#1268): a grid/flex item refuses by default to
     shrink below its `min-content`, so a long name widened the tile past its own column instead of
     being clipped, and the ellipsis never got the chance to appear. */
  min-width: 0;
}
.apps-tile {
  /* ion-button in `clear` fill, re-shaped as a tile: full cell, stacked icon over label, and the
     Ionic uppercase/letter-spacing undone (an app's name is a name, not a shout). */
  flex: 1;
  min-width: 0;
  height: auto;
  --padding-top: 0.7rem;
  --padding-bottom: 0.7rem;
  --padding-start: 0.35rem;
  --padding-end: 0.35rem;
  --border-radius: var(--ok-radius-sm, 10px);
  --color: var(--ion-text-color);
  text-transform: none;
  letter-spacing: normal;
  font-weight: 500;
}
.apps-tile-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
}
.apps-tile-icon {
  font-size: 1.6rem;
  color: var(--ion-color-primary, #0091ce);
}
.apps-tile-label {
  font-size: 0.75rem;
  line-height: 1.2;
  text-align: center;
  /* Two lines at most: a long module name must not push the row's height around. */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  /* Never mid-word (hub#1268). `word-break: break-word` split «Automatizaciones» into
     «Automatizacio» / «nes», which reads as a typo and not as a name. Neither does
     `overflow-wrap: anywhere` help: measured in Chromium over this very card, the name is 104px
     wide and the label 84-90px, so ANY setting that authorises breaking inside a word produces the
     same cut. What every launcher does instead —macOS Launchpad, the Windows Start menu, the
     Android/iOS home screens, Google's app grid— is refuse to break the word and TRUNCATE it; the
     whole name stays one hover away in the tile's `title`.
     Guard: MyAppsCard.test.ts → `the_tile_label_does_not_split_words_hub1268`. */
  word-break: normal;
  overflow-wrap: normal;
  text-overflow: ellipsis;
  max-width: 100%;
}
/* hub#1722 — a placeholder has to occupy the TILE, not a line of text. `ion-skeleton-text` ships as
   a thin bar sized to a sentence; left at its default the loading grid reads as a few grey dashes
   above the ＋ tile, which is not the shape of what is coming. Height is pinned to what a real tile
   measures (icon 1.6rem + gap 0.35rem + two label lines at 0.75rem/1.2 + the tile's 0.7rem padding
   top and bottom ≈ 5rem) so nothing jumps when the apps land in their place. */
.apps-tile-skeleton {
  width: 100%;
  height: 5rem;
  margin: 0;
  border-radius: var(--ok-radius-sm, 10px);
}
/* The catalogue tile reads as an offer, not as one more installed app: dashed outline, muted ink. */
.apps-tile--add {
  --border-width: 1px;
  --border-style: dashed;
  --border-color: var(--ion-border-color, rgba(0, 0, 0, 0.16));
  --color: var(--ion-color-medium, #92949c);
}
.apps-tile--add .apps-tile-icon {
  color: var(--ion-color-medium, #92949c);
}
/* hub#1197 — the fold's own tile: a tint instead of the ＋ tile's dashed outline, so «there is more
   of what you already have» does not read as «add something new» (the ＋ tile's own job). */
.apps-tile--view-all {
  --background: color-mix(in srgb, var(--ion-color-primary, #0091ce) 8%, transparent);
  --color: var(--ion-color-primary, #0091ce);
}
.apps-tile--view-all .apps-tile-icon {
  color: var(--ion-color-primary, #0091ce);
}
</style>
