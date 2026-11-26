<script setup lang="ts">
// Tips → My tips (TIP-F14; WORKBOOK «Pantallas · Mis propinas»): the caller's own tips of today and of the week, from
// Monday, live (`tip.report.mine`), each as its figures in all, by card, in cash and other ways. Nothing of managing the
// tips is here: whoever only records tips opens this screen alone.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import ListNotices, { blockingError } from '../../../sale/frontend/components/backoffice/ListNotices.vue';
import { useLocale, useT } from '../../../sale/frontend/composables/useT';
import { formatDay } from '../../../sale/frontend/lib/format';
import { useAppTabs } from '../../../../base/frontend/lib/app-tabs';
import TipFigures from '../components/TipFigures.vue';

/** The refusal of a user with no record of the team: nothing to retry until a manager links one. */
const UNLINKED = 'tip.member_not_linked';

const tabs = useAppTabs('tip');
const t = useT();
const locale = useLocale();
const { data, status, error, refresh } = useLive('tip.report.mine', {});

const blocked = computed(() => blockingError(error.value));
const unlinked = computed(() => error.value?.code === UNLINKED);
const failed = computed(() => status.value === 'error' && !blocked.value);
const empty = computed(() => data.value?.week.count === 0);
const weekHeading = computed(() =>
  data.value ? t('tip.mine.week', { day: formatDay(data.value.week_from, locale.value) }) : t('tip.mine.thisWeek'),
);
</script>

<template>
  <AppPage
    :title="$t('tip.title')"
    :tabs="tabs"
    :tabs-label="$t('tip.tabs.label')"
  >
    <ListNotices
      testid="tip-mine"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="unlinked"
      tone="warning"
      data-testid="tip-mine-unlinked"
      :heading="error?.message"
    />
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      data-testid="tip-mine-error"
      :heading="$t('tip.mine.loadError')"
    >
      {{ error?.message }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="tip-mine-retry"
          @click="refresh()"
        >
          {{ $t('tip.mine.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <EmptyState
      v-else-if="empty"
      data-testid="tip-mine-empty"
      icon="wallet-outline"
      :heading="$t('tip.mine.empty')"
      :message="$t('tip.mine.emptyMessage')"
    />
    <template v-else-if="!blocked">
      <h2
        class="ion-no-margin ion-margin-bottom"
        data-testid="tip-mine-day-heading"
      >
        {{ $t('tip.mine.today') }}
      </h2>
      <TipFigures
        class="ion-margin-bottom"
        testid="tip-mine-day"
        :figures="data?.day"
      />
      <h2
        class="ion-no-margin ion-margin-bottom"
        data-testid="tip-mine-week-heading"
      >
        {{ weekHeading }}
      </h2>
      <TipFigures
        testid="tip-mine-week"
        :figures="data?.week"
      />
    </template>
  </AppPage>
</template>
