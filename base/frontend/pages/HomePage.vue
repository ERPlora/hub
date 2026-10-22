<script setup lang="ts">
// The Home (BASE-G127; the old hub's dashboard, PLAN-HUB round 2026-10-21): headed by the business's name (the
// SaaS's, `hub-home`), or a greeting by the hour while it has none, and today's date. «Summary»: «My apps» (it
// goes first and works with no data), «Finish setting up your business» and the board of the apps' panels;
// each zone reads its own data and fails on its own. «Activity»: the last sales. The tab lives in the address
// (`/#actividad`), so it can be linked and Back leaves the Home instead of walking its tabs.
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import HomeActivity from '../components/HomeActivity.vue';
import HomeMyApps from '../components/HomeMyApps.vue';
import SetupChecklist from '../components/SetupChecklist.vue';
import WidgetBoard from '../components/WidgetBoard.vue';
import { heading, type HubHome, readJsonBlock } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import '../home.css';

type Tab = 'summary' | 'activity';

/** The hash of «Activity» (the old hub's address, kept for its links). */
const ACTIVITY_HASH = '#actividad';

const { t, locale } = useBaseI18n();
const route = useRoute();
const router = useRouter();

const business = readJsonBlock<HubHome>('hub-home')?.name;
const now = new Date();
const title = computed(() => {
  const head = heading(business, now.getHours());
  return head.kind === 'business' ? head.name : t(`base.home.greeting.${head.slot}`);
});
const today = computed(() =>
  t('base.home.today', {
    date: new Intl.DateTimeFormat(locale.value, { weekday: 'long', day: 'numeric', month: 'long' }).format(now),
  }),
);

const tabs = computed<ShellTab[]>(() => [
  { id: 'summary', label: t('base.home.tabs.summary'), icon: 'ion:speedometer-outline' },
  { id: 'activity', label: t('base.home.tabs.activity'), icon: 'ion:time-outline' },
]);
const tab = computed<Tab>({
  get: () => (route.hash === ACTIVITY_HASH ? 'activity' : 'summary'),
  set: (next) => void router.replace({ path: route.path, hash: next === 'activity' ? ACTIVITY_HASH : '' }),
});
</script>

<template>
  <AppPage
    v-model:tab="tab"
    :title="t('base.home.title')"
    :tabs="tabs"
    :tabs-label="t('base.home.tabs.label')"
    :content-layout="tab === 'activity' ? 'fill' : 'fluid'"
    :heading-on-screen="tab === 'summary'"
  >
    <template v-if="tab === 'summary'">
      <header class="home-hero">
        <h1 class="home-hero-title">
          {{ title }}
        </h1>
        <p
          class="home-hero-date"
          data-testid="home-date"
        >
          {{ today }}
        </p>
      </header>
      <HomeMyApps />
      <SetupChecklist />
      <WidgetBoard />
    </template>
    <HomeActivity v-else />
  </AppPage>
</template>

<style scoped>
.home-hero {
  margin: 4px 0 16px;
}

.home-hero-title {
  margin: 0;
  font-size: 1.625rem;
  font-weight: 700;
  line-height: 1.2;
}

.home-hero-date {
  margin: 4px 0 0;
  color: var(--ion-color-medium);
}
</style>
