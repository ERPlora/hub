<script setup lang="ts">
// «Automations» (WORKBOOK «Pantallas · Automatizaciones»; FLOW-F01 to F08): «New automation» on top;
// «Proposed by the assistant» when there are drafts; «Your automations» only when there is one; and
// the gallery, always, below — a link (`?template=<id>`) opens one of its cards. What automations can
// use here (the catalog) that could not be read is said, with «Retry». A card used opens the
// new automation on its Permissions (it does nothing without them); a row opens it on its steps. The
// app turned off, or no permission, replace everything with their notice.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import DraftTray from '../components/DraftTray.vue';
import FlowList from '../components/FlowList.vue';
import FlowGallery from '../components/FlowGallery.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useCatalog } from '../composables/useCatalog';
import { wording } from '../lib/refusal';
import type { FlowOut } from '../operations';

const route = useRoute();
const router = useRouter();
const { catalog, loading, error: catalogError, reload: reloadCatalog } = useCatalog();
// Every automation of the business, for the gallery's marks and the list's count (a business has far
// fewer than the 100 a page holds).
const all = useLive('flow.flow.list', { limit: 100 });
const flows = computed(() => all.data.value?.rows ?? []);
const total = computed(() => all.data.value?.total ?? 0);
const blocked = computed(() => blockingError(all.error.value));
const openCard = computed(() => (typeof route.query.template === 'string' ? route.query.template : null));

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
        @click="router.push('/flow/automations/new')"
      >
        <HubIcon name="ion:add-outline" />{{ $t('flow.list.new') }}
      </IonButton>
    </template>
    <PageNotices
      testid="flow-page"
      :status="all.status.value"
      :error="all.error.value"
    />
    <div
      v-if="!blocked"
      class="flow-page"
    >
      <DraftTray />
      <FlowList
        v-if="total > 0"
        :catalog="catalog"
        :all-total="total"
        @open="openFlow($event)"
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
