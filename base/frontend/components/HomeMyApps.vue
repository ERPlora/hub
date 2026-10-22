<script setup lang="ts">
// «My apps» on the Home (BASE-G165, hub#367): the launcher goes first and is the only card that works with
// no data. Same list as the topbar's «My apps» (`useMyApps`, from `base.session.me`), the most opened in this
// browser first. «Add apps» goes last, to Apps, once the router has that screen (an entry that leads to the
// 404 is worse than none). On a phone with six apps or more: the first four and «View all apps».
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { HubIcon, useMyApps, useSession } from '@erplora/ui/shell';
import { IonBadge, IonSkeletonText } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { orderByUse, readUsage, recordUse } from '../lib/home';
import { usePhone } from '../lib/phone';
import '../home.css';

/** On a phone, from this many apps the card folds to `PHONE_TILES`. */
const PHONE_FOLD_FROM = 6;
const PHONE_TILES = 4;
const SKELETON_TILES = 6;

const router = useRouter();
const session = useSession();
const apps = useMyApps();
const phone = usePhone();
const usage = ref(readUsage(localStorage));
const expanded = ref(false);

const ordered = computed(() => orderByUse(apps.value, usage.value));
const folded = computed(() => phone.value && !expanded.value && ordered.value.length >= PHONE_FOLD_FROM);
const shown = computed(() => (folded.value ? ordered.value.slice(0, PHONE_TILES) : ordered.value));
const loading = computed(() => session.me.value === undefined && session.status.value !== 'error');
const failed = computed(() => session.me.value === undefined && session.status.value === 'error');
const addApps = computed(() => router.resolve('/apps').name !== 'not-found');

/** Counts the opening; a browser that refuses to store (private mode, full) only loses the order. */
function opened(id: string): void {
  try {
    usage.value = recordUse(id, localStorage);
  } catch (error) {
    console.warn('base: could not count the opening of an app', error);
  }
}
</script>

<template>
  <section
    class="home-card my-apps"
    data-testid="home-my-apps"
    :aria-busy="loading"
  >
    <h2 class="home-card-title">
      {{ $t('base.apps.title') }}
    </h2>

    <template v-if="loading">
      <p
        role="status"
        class="visually-hidden"
      >
        {{ $t('base.apps.loading') }}
      </p>
      <ul
        class="my-apps-grid"
        aria-hidden="true"
      >
        <li
          v-for="n in SKELETON_TILES"
          :key="n"
          class="my-app"
          data-testid="home-my-apps-skeleton"
        >
          <ion-skeleton-text
            animated
            class="my-app-skeleton-icon"
          />
          <ion-skeleton-text
            animated
            class="my-app-skeleton-name"
          />
        </li>
      </ul>
    </template>

    <InlineFeedback
      v-else-if="failed"
      tone="warning"
      data-testid="home-my-apps-error"
    >
      {{ $t('base.apps.loadError') }}
    </InlineFeedback>

    <template v-else>
      <EmptyState
        v-if="ordered.length === 0"
        icon="apps-outline"
        :message="$t('base.apps.empty')"
        data-testid="home-my-apps-empty"
      />
      <ul class="my-apps-grid">
        <li
          v-for="app in shown"
          :key="app.id"
        >
          <router-link
            v-if="app.path"
            :to="app.path"
            class="my-app"
            :title="app.name"
            data-testid="home-my-app"
            @click="opened(app.id)"
          >
            <HubIcon
              class="my-app-icon"
              :name="app.icon"
            />
            <span class="my-app-name">{{ app.name }}</span>
          </router-link>
          <span
            v-else
            class="my-app my-app--waiting"
            :title="app.name"
            data-testid="home-my-app"
          >
            <HubIcon
              class="my-app-icon"
              :name="app.icon"
            />
            <span class="my-app-name">{{ app.name }}</span>
            <ion-badge color="medium">{{ $t(`base.apps.state.${app.state}`) }}</ion-badge>
          </span>
        </li>
        <li v-if="folded">
          <button
            type="button"
            class="my-app my-app--all"
            data-testid="home-my-apps-all"
            @click="expanded = true"
          >
            <HubIcon
              class="my-app-icon"
              name="ion:grid-outline"
            />
            <span class="my-app-name">{{ $t('base.apps.viewAll') }}</span>
          </button>
        </li>
        <li v-if="addApps">
          <router-link
            to="/apps"
            class="my-app my-app--add"
            data-testid="home-my-apps-add"
          >
            <HubIcon
              class="my-app-icon"
              name="ion:add-outline"
            />
            <span class="my-app-name">{{ $t('base.apps.add') }}</span>
          </router-link>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
/* The old hub's launcher: flat tiles, icon over name, as many per row as fit (three on a phone). */
.my-apps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.my-app {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 76px;
  width: 100%;
  padding: 10px 6px;
  border: 0;
  border-radius: var(--ep-radius, 12px);
  background: none;
  color: var(--ion-text-color);
  font: inherit;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
}

.my-app:hover,
.my-app:focus-visible {
  background: color-mix(in oklab, var(--ion-color-primary) 8%, transparent);
}

.my-app--waiting {
  cursor: default;
}

.my-app--all {
  background: color-mix(in oklab, var(--ion-color-primary) 10%, transparent);
  color: var(--ion-color-primary);
}

.my-app--add {
  border: 1px dashed var(--ion-color-step-250, #d0d5dd);
  color: var(--ion-color-medium);
}

.my-app-icon {
  font-size: 24px;
  color: var(--ion-color-primary);
}

.my-app--add .my-app-icon {
  color: var(--ion-color-medium);
}

.my-app-name {
  display: -webkit-box;
  overflow: hidden;
  font-size: 13px;
  line-height: 1.25;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.my-app-skeleton-icon {
  width: 28px;
  height: 28px;
}

.my-app-skeleton-name {
  width: 60%;
  height: 12px;
}

@media (max-width: 767px) {
  .my-apps-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
