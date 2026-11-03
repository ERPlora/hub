<script setup lang="ts">
// «Automations» (WORKBOOK «Pantallas · Automatizaciones»; FLOW-F01 to F08): «New automation» on top;
// «Proposed by the assistant» when there are drafts; «Your automations» only when there is one; and
// the gallery, always, below — a link (`?template=<id>`) opens one of its cards. What automations can
// use here (the catalog) that could not be read is said, with «Retry». A card used opens the
// new automation on its Permissions (it does nothing without them); a row opens it on its steps. The
// app turned off, or no permission, replace everything with their notice. «Waiting for your answer» (FLOW-F29) sits
// on top; a manager or an employee, who may only answer what automations ask, sees only it (and nothing
// else of the app is asked for them: no list, no catalog). Above the list, the ready-made automations set up
// with a fault their app already fixed, with «Update it» (FLOW-F36).
// On a phone «New automation» is its «+» alone, named by `aria-label`: with its words it took the bar and
// left the title as «A…» (FIX-HUB-FLOW-AUTOMATIONS-TITLE-CUT-ON-PHONE; Material's top app bar, iOS's navigation
// bars). From a tablet on, its icon and its words.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import DraftTray from '../components/DraftTray.vue';
import FlowList from '../components/FlowList.vue';
import FlowGallery from '../components/FlowGallery.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import QuestionInbox from '../components/QuestionInbox.vue';
import { useCatalog } from '../composables/useCatalog';
import { wording } from '../lib/refusal';
import type { FlowOut } from '../operations';

const route = useRoute();
const router = useRouter();
const session = useSession();
const onlyAnswers = !session.can('flow.view') && session.can('flow.answer');
const shelf = onlyAnswers ? null : useCatalog();
const catalog = computed(() => shelf?.catalog.value ?? null);
const loading = computed(() => shelf?.loading.value ?? false);
const catalogError = computed(() => shelf?.error.value ?? null);
const reloadCatalog = (): void => void shelf?.reload();
// Every automation of the business, for the gallery's marks and the list's count (a business has far
// fewer than the 100 a page holds).
const all = onlyAnswers ? null : useLive('flow.flow.list', { limit: 100 });
const flows = computed(() => all?.data.value?.rows ?? []);
const total = computed(() => all?.data.value?.total ?? 0);
const blocked = computed(() => !all || blockingError(all.error.value));
// A link's card opens once what is above the gallery has its first answer — the drafts, and the list
// when there is one —: opened earlier, the list would push it out of view (FLOW-F05).
const draftsReady = ref(false);
const listReady = ref(false);
const aboveReady = computed(
  () => draftsReady.value && !!(all?.data.value || all?.error.value) && (total.value === 0 || listReady.value),
);
const openCard = computed(() =>
  aboveReady.value && typeof route.query.template === 'string' ? route.query.template : null,
);

/** The width at or below which the bar is a phone's: the shell's own (`AppTopbar`, hub#111). */
const PHONE_QUERY = '(max-width: 767px)';
const phoneQuery = typeof window.matchMedia === 'function' ? window.matchMedia(PHONE_QUERY) : null;
const phone = ref(!!phoneQuery?.matches);
const onPhoneChange = (event: { matches: boolean }): void => {
  phone.value = event.matches;
};
phoneQuery?.addEventListener('change', onPhoneChange);
onBeforeUnmount(() => phoneQuery?.removeEventListener('change', onPhoneChange));

function openFlow(flow: FlowOut, tab?: string): void {
  void router.push(tab ? `/flow/automations/${flow.id}?tab=${tab}` : `/flow/automations/${flow.id}`);
}
</script>

<template>
  <AppPage :title="$t('flow.title')">
    <template #actions>
      <IonButton
        v-if="!blocked"
        size="small"
        fill="outline"
        mode="md"
        data-testid="flow-new"
        :aria-label="$t('flow.list.new')"
        :title="phone ? $t('flow.list.new') : undefined"
        @click="router.push('/flow/automations/new')"
      >
        <HubIcon
          v-if="phone"
          slot="icon-only"
          name="ion:add-outline"
          data-testid="flow-new-icon"
        />
        <template v-else>
          <HubIcon
            slot="start"
            name="ion:add-outline"
            data-testid="flow-new-icon"
          />{{ $t('flow.list.new') }}
        </template>
      </IonButton>
    </template>
    <QuestionInbox
      v-if="onlyAnswers"
      alone
    />
    <PageNotices
      v-if="all"
      testid="flow-page"
      :status="all.status.value"
      :error="all.error.value"
    />
    <div
      v-if="!blocked"
      class="flow-page"
    >
      <QuestionInbox :alone="false" />
      <DraftTray @ready="draftsReady = true" />
      <!-- Mounted with the page and only hidden while there is none: its subscription goes on the page's one stream,
           instead of arriving with the count and reopening it. -->
      <FlowList
        v-show="total > 0"
        :catalog="catalog"
        :all-total="total"
        @open="openFlow($event)"
        @ready="listReady = true"
      />
      <InlineFeedback
        v-if="catalogError"
        tone="danger"
        data-testid="flow-catalog-error"
      >
        {{ $t('flow.catalogError') }} {{ wording(catalogError, '') }}
        <IonButton
          size="small"
          fill="clear"
          data-testid="flow-catalog-retry"
          @click="reloadCatalog()"
        >
          {{ $t('flow.live.retry') }}
        </IonButton>
      </InlineFeedback>
      <div
        v-if="loading"
        class="flow-page__loading"
      >
        <IonSpinner name="dots" /> {{ $t('flow.loading') }}
      </div>
      <FlowGallery
        :catalog="catalog"
        :flows="flows"
        :open-card="openCard"
        @created="openFlow($event, 'permissions')"
        @open-flow="openFlow($event, $event.missing_grants.length ? 'permissions' : undefined)"
        @guide="router.push('/flow/guide')"
      />
    </div>
  </AppPage>
</template>

<style scoped>
.flow-page {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.flow-page__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
</style>
