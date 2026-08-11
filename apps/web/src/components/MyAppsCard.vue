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

    <ul class="apps-grid">
      <li v-for="app in ordered" :key="app.path" class="apps-grid-cell">
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
            <span class="apps-tile-label">{{ app.label }}</span>
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
            <span class="apps-tile-label">{{ t('dashboard.appsAdd') }}</span>
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
import { IonButton } from '@ionic/vue';

import HubIcon from './HubIcon.vue';
import { orderAppsByUsage, recordAppLaunch } from '../lib/app-usage';
import { listDisplay, type ListLoadState } from '../lib/list-load-state';
import type { ModuleNavItem } from '../lib/nav';

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

/* Auto-fill grid: 4-5 tiles per row on a desktop, 3 on a phone, without a media query per breakpoint
   (the tiles are square-ish and the label wraps to two lines at most). */
.apps-grid {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(5.5rem, 1fr));
  gap: 0.5rem;
}
.apps-grid-cell {
  display: flex;
}
.apps-tile {
  /* ion-button in `clear` fill, re-shaped as a tile: full cell, stacked icon over label, and the
     Ionic uppercase/letter-spacing undone (an app's name is a name, not a shout). */
  flex: 1;
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
  word-break: break-word;
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
</style>
