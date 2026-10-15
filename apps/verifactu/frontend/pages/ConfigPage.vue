<script setup lang="ts">
// VeriFactu → Configuration (VERIFACTU-F02–F06, F34; the old `erp-verifactu-config`): «VeriFactu configuration» with
// the two routes as tabs. «ERPlora files for you» (opens by default): «Representation authorisation» and its state
// (not signed, under review, approved, returned with the review's note, revoked). «My certificate»: «Loaded» / «Not
// loaded», holder, uploaded and expiry dates and the warning 30 days before it expires (or that it expired). Both are
// managed in the ERPlora account («Manage in your ERPlora account»): the certificate and its password never reach the
// Hub (PLAN §16.5). What the account has not sent yet is said so.
import { formatDateTime, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonLabel, IonSegment, IonSegmentButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { verifactuTabs } from '../tabs';

const EXPIRY_WARNING_DAYS = 30;

const t = useT();
const locale = useLocale();
const tab = shallowRef<'erplora' | 'own'>('erplora');

const { data: config, status, error } = useLive('verifactu.config.get', () => ({}));

const date = (value: string | null | undefined) => (value ? formatDateTime(value, locale.value) : '—');

const grant = computed(() => {
  const r = config.value?.representation;
  if (!r) return '';
  return t(`verifactu.config.grant.${r.status}`, { date: date(r.updated_at) });
});
const expiry = computed(() => {
  const cert = config.value?.own_certificate;
  if (!cert?.loaded || cert.expires_in_days === null) return null;
  if (cert.expires_in_days < 0) return { tone: 'danger' as const, text: t('verifactu.config.expired') };
  if (cert.expires_in_days <= EXPIRY_WARNING_DAYS) return { tone: 'warning' as const, text: t('verifactu.config.expiresSoon', { n: cert.expires_in_days }) };
  return null;
});
</script>

<template>
  <AppPage
    :title="$t('verifactu.config.title')"
    :tabs="verifactuTabs($t)"
    :tabs-label="$t('verifactu.tabs.label')"
    content-layout="detail"
  >
    <PageNotices
      testid="verifactu-config"
      :status="status"
      :error="error"
    />
    <div
      v-if="!config && status === 'loading'"
      class="ion-text-center ion-padding"
    >
      <ion-spinner />
    </div>
    <template v-if="config">
      <ion-segment
        :value="tab"
        mode="md"
        @ion-change="tab = $event.detail.value as 'erplora' | 'own'"
      >
        <ion-segment-button
          value="erplora"
          data-testid="verifactu-config-tab-erplora"
          @click="tab = 'erplora'"
        >
          <ion-label>{{ $t('verifactu.config.erplora') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button
          value="own"
          data-testid="verifactu-config-tab-own"
          @click="tab = 'own'"
        >
          <ion-label>{{ $t('verifactu.config.own') }}</ion-label>
        </ion-segment-button>
      </ion-segment>

      <InlineFeedback
        v-if="!config.synced_at"
        tone="info"
        data-testid="verifactu-config-not-synced"
      >
        {{ $t('verifactu.config.notSynced') }}
      </InlineFeedback>

      <section
        v-if="tab === 'erplora'"
        class="verifactu-config__panel"
        data-testid="verifactu-config-erplora"
      >
        <h3>{{ $t('verifactu.config.grantTitle') }}</h3>
        <p data-testid="verifactu-config-grant">
          {{ grant }}
        </p>
        <p
          v-if="config.representation.reason"
          data-testid="verifactu-config-grant-reason"
        >
          {{ $t('verifactu.config.reviewNote') }}: {{ config.representation.reason }}
        </p>
      </section>

      <section
        v-else
        class="verifactu-config__panel"
        data-testid="verifactu-config-own"
      >
        <h3>{{ $t('verifactu.config.certTitle') }}</h3>
        <div data-testid="verifactu-config-cert">
          <StatusPill
            :tone="config.own_certificate.loaded ? 'success' : 'neutral'"
            :label="config.own_certificate.loaded ? $t('verifactu.config.loaded') : $t('verifactu.config.notLoaded')"
          />
          <dl
            v-if="config.own_certificate.loaded"
            class="verifactu-config__fields"
          >
            <dt>{{ $t('verifactu.config.holder') }}</dt>
            <dd>{{ config.own_certificate.holder || '—' }}</dd>
            <dt>{{ $t('verifactu.config.uploaded') }}</dt>
            <dd>{{ date(config.own_certificate.uploaded_at) }}</dd>
            <dt>{{ $t('verifactu.config.expires') }}</dt>
            <dd>{{ date(config.own_certificate.expires_at) }}</dd>
          </dl>
        </div>
        <InlineFeedback
          v-if="expiry"
          :tone="expiry.tone"
          data-testid="verifactu-config-expiry"
        >
          {{ expiry.text }}
        </InlineFeedback>
        <p
          class="verifactu-config__note"
          data-testid="verifactu-config-keys"
        >
          {{ $t('verifactu.config.keysNote') }}
        </p>
      </section>

      <a
        class="verifactu-config__manage"
        :href="config.account_url"
        target="_blank"
        rel="noopener"
        data-testid="verifactu-config-manage"
      >{{ $t('verifactu.config.manage') }} ↗</a>
    </template>
  </AppPage>
</template>

<style scoped>
.verifactu-config__panel {
  margin: 1rem 0;
}
.verifactu-config__panel h3 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
}
.verifactu-config__fields {
  display: grid;
  grid-template-columns: minmax(8rem, max-content) 1fr;
  gap: 0.25rem 1rem;
  margin: 0.75rem 0 0;
}
.verifactu-config__fields dt {
  color: var(--ion-color-medium, #8a8577);
}
.verifactu-config__fields dd {
  margin: 0;
}
.verifactu-config__manage {
  display: inline-block;
  padding: 0.55rem 0.9rem;
  border: 1px solid var(--ion-color-primary, #3f6f5f);
  border-radius: 10px;
  color: var(--ion-color-primary, #3f6f5f);
  text-decoration: none;
}
.verifactu-config__note {
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.85rem;
}
</style>
