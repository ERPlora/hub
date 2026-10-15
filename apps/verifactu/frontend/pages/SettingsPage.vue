<script setup lang="ts">
// VeriFactu → Settings (VERIFACTU-F04, F08–F12; the old `erp-verifactu-settings`; «Enable VeriFactu» is gone:
// turning the app on is enabling it). «Sending»: «Use my own certificate» (owner and admin; ERPlora files for you when
// off), with its explanation and «Open Configuration»; «AEAT environment» with its pill and «Go live» (asks first;
// closed while the server keeps it closed or while something is missing, listed above it: the approved signed
// authorisation, the own certificate, the live option of the plan, an active account) or, in production, why records
// wait (e.g. the live option left the plan) and «Back to testing» (asks first; only until the first production
// record). «Live test»: «Test the connection» (whoever may send), which presents nothing to the AEAT, and «Create test
// invoice» (owner and admin, in testing), with the last result. «Responsible declaration»: «Read the signed
// declaration», its version and the identifying data every record carries (VERIFACTU-F12).
import { formatDateTime, InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { environmentTone } from '../lib/record';
import { refusal } from '../lib/refusal';
import type { DiagnosticOut } from '../operations';
import { verifactuTabs } from '../tabs';

const session = useSession();
const canConfigure = computed(() => session.can('verifactu.configure'));
const canSend = computed(() => session.can('verifactu.transmit_record'));
const t = useT();
const locale = useLocale();
const { confirm } = useConfirm();

const { data: config, status, error } = useLive('verifactu.config.get', () => ({}));
const { data: last } = useLive('verifactu.diagnostic.last', () => ({}));
const update = useCommand('verifactu.config.update');
const goLive = useCommand('verifactu.config.go_live');
const back = useCommand('verifactu.config.back_to_testing');
const diagnose = useCommand('verifactu.diagnostic.run');
const testInvoice = useCommand('verifactu.test_invoice.create');
const refused = shallowRef<string | null>(null);
const fresh = shallowRef<DiagnosticOut | null>(null);

const result = computed(() => fresh.value ?? last.value?.result ?? null);
const busy = computed(() => update.pending.value || goLive.pending.value || back.pending.value || diagnose.pending.value || testInvoice.pending.value);

const identity = computed(() => {
  const p = config.value?.producer;
  if (!p) return [];
  return [
    { label: t('verifactu.settings.producerName'), element: 'NombreRazon', value: p.name },
    { label: t('verifactu.settings.producerNif'), element: 'NIF', value: p.nif },
    { label: t('verifactu.settings.systemName'), element: 'NombreSistemaInformatico', value: p.system_name },
    { label: t('verifactu.settings.systemId'), element: 'IdSistemaInformatico', value: p.system_id },
    { label: t('verifactu.settings.version'), element: 'Version', value: p.version },
    { label: t('verifactu.settings.installation'), element: 'NumeroInstalacion', value: p.installation },
    { label: t('verifactu.settings.onlyVerifactu'), element: 'TipoUsoPosibleSoloVerifactu', value: p.only_verifactu },
    { label: t('verifactu.settings.multiOt'), element: 'TipoUsoPosibleMultiOT', value: p.multi_ot },
    { label: t('verifactu.settings.multipleOt'), element: 'IndicadorMultiplesOT', value: p.multiple_ot },
  ];
});

function failed(command: { error: { value: unknown } }): void {
  refused.value = refusal(command.error.value, t('verifactu.settings.failed'))?.message ?? t('verifactu.settings.failed');
}

async function setRoute(event: CustomEvent<{ checked?: boolean; value?: unknown }>): Promise<void> {
  const toggle = event.target as (EventTarget & { checked?: boolean }) | null;
  const own = Boolean(event.detail.checked ?? event.detail.value);
  const route = own ? 'own' : 'erplora';
  if (!config.value || config.value.route === route || update.pending.value) return;
  refused.value = null;
  try {
    await update.run({ route });
  } catch {
    // The toggle turned itself; `:checked` did not change, so Vue would not put it back.
    if (toggle) toggle.checked = config.value?.route === 'own';
    failed(update);
    return;
  }
  void toastSuccess(own ? t('verifactu.settings.routeOwn') : t('verifactu.settings.routeErplora'));
}

async function goingLive(): Promise<void> {
  refused.value = null;
  const yes = await confirm({
    title: t('verifactu.settings.goLiveTitle'),
    message: t('verifactu.settings.goLiveMessage'),
    confirmLabel: t('verifactu.settings.goLive'),
    cancelLabel: t('verifactu.cancel'),
    tone: 'danger',
  });
  if (!yes) return;
  try {
    await goLive.run({});
  } catch {
    failed(goLive);
    return;
  }
  void toastSuccess(t('verifactu.settings.wentLive'));
}

async function backToTesting(): Promise<void> {
  refused.value = null;
  const yes = await confirm({
    title: t('verifactu.settings.backTitle'),
    message: t('verifactu.settings.backMessage'),
    confirmLabel: t('verifactu.settings.backToTesting'),
    cancelLabel: t('verifactu.cancel'),
    tone: 'primary',
  });
  if (!yes) return;
  try {
    await back.run({});
  } catch {
    failed(back);
    return;
  }
  void toastSuccess(t('verifactu.settings.backDone'));
}

async function testConnection(): Promise<void> {
  refused.value = null;
  try {
    fresh.value = await diagnose.run({});
  } catch {
    failed(diagnose);
  }
}

async function createTestInvoice(): Promise<void> {
  refused.value = null;
  let answer;
  try {
    answer = await testInvoice.run({});
  } catch {
    failed(testInvoice);
    return;
  }
  void toastSuccess(t('verifactu.settings.testCreated', { number: answer.number }));
}

const yesNo = (value: boolean | null) => (value === null ? t('verifactu.settings.notConfigured') : value ? t('verifactu.settings.ready') : t('verifactu.settings.notReady'));
</script>

<template>
  <AppPage
    :title="$t('verifactu.settings.title')"
    :tabs="verifactuTabs($t)"
    :tabs-label="$t('verifactu.tabs.label')"
    content-layout="detail"
  >
    <PageNotices
      testid="verifactu-settings"
      :status="status"
      :error="error"
    />
    <div
      v-if="!config && status === 'loading'"
      class="ion-text-center ion-padding"
    >
      <ion-spinner />
    </div>
    <InlineFeedback
      v-if="refused"
      tone="danger"
      data-testid="verifactu-settings-error"
    >
      {{ refused }}
    </InlineFeedback>
    <template v-if="config">
      <section class="verifactu-settings__card">
        <h3>{{ $t('verifactu.settings.sending') }}</h3>
        <ion-toggle
          v-if="canConfigure"
          data-testid="verifactu-settings-own"
          :checked="config.route === 'own'"
          :disabled="busy"
          @ion-change="setRoute"
        >
          {{ $t('verifactu.settings.ownCertificate') }}
        </ion-toggle>
        <p
          class="verifactu-settings__hint"
          data-testid="verifactu-settings-route-hint"
        >
          {{ config.route === 'own' ? $t('verifactu.settings.ownOn') : $t('verifactu.settings.ownOff') }}
          <router-link to="/verifactu/config">
            {{ $t('verifactu.settings.openConfig') }}
          </router-link>
        </p>

        <div
          class="verifactu-settings__environment"
          data-testid="verifactu-settings-environment"
        >
          <span>{{ $t('verifactu.settings.environment') }}</span>
          <StatusPill
            :tone="environmentTone(config.environment)"
            :label="$t(`verifactu.env.${config.environment}`)"
          />
        </div>
        <template v-if="config.environment === 'testing'">
          <p class="verifactu-settings__hint">
            {{ $t('verifactu.settings.goLiveHint') }}
          </p>
          <p
            v-if="!config.production_open"
            class="verifactu-settings__hint"
            data-testid="verifactu-settings-closed"
          >
            {{ $t('verifactu.settings.productionClosed') }}
          </p>
          <InlineFeedback
            v-if="config.live_blockers.length"
            tone="warning"
            data-testid="verifactu-settings-live-blockers"
          >
            {{ $t('verifactu.settings.cannotGoLive') }}
            <ul class="verifactu-settings__reasons">
              <li
                v-for="reason in config.live_blockers"
                :key="reason.code"
              >
                {{ reason.message }}
              </li>
            </ul>
          </InlineFeedback>
          <ion-button
            v-if="canConfigure"
            color="danger"
            data-testid="verifactu-settings-go-live"
            :disabled="busy || !config.production_open || config.live_blockers.length > 0"
            @click="goingLive"
          >
            {{ $t('verifactu.settings.goLive') }}
          </ion-button>
        </template>
        <template v-else>
          <InlineFeedback
            v-if="config.issue_blocker"
            tone="danger"
            data-testid="verifactu-settings-issue-blocked"
          >
            {{ $t('verifactu.settings.issueBlocked') }}
            <ul class="verifactu-settings__reasons">
              <li>{{ config.issue_blocker.message }}</li>
            </ul>
          </InlineFeedback>
          <InlineFeedback
            v-if="config.reasons.length"
            tone="warning"
            data-testid="verifactu-settings-waiting"
          >
            {{ $t('verifactu.settings.waiting') }}
            <ul class="verifactu-settings__reasons">
              <li
                v-for="reason in config.reasons"
                :key="reason.code"
              >
                {{ reason.message }}
              </li>
            </ul>
          </InlineFeedback>
          <template v-if="config.can_go_back">
            <p class="verifactu-settings__hint">
              {{ $t('verifactu.settings.backHint') }}
            </p>
            <ion-button
              v-if="canConfigure"
              fill="outline"
              data-testid="verifactu-settings-back"
              :disabled="busy"
              @click="backToTesting"
            >
              {{ $t('verifactu.settings.backToTesting') }}
            </ion-button>
          </template>
          <p
            v-else
            class="verifactu-settings__hint"
            data-testid="verifactu-settings-one-way"
          >
            {{ $t('verifactu.settings.oneWay') }}
          </p>
        </template>
      </section>

      <section class="verifactu-settings__card">
        <h3>{{ $t('verifactu.settings.test') }}</h3>
        <p class="verifactu-settings__hint">
          {{ $t('verifactu.settings.testHint') }}
        </p>
        <div class="verifactu-settings__buttons">
          <ion-button
            v-if="canSend"
            data-testid="verifactu-settings-test"
            :disabled="busy"
            @click="testConnection"
          >
            {{ $t('verifactu.settings.testRun') }}
          </ion-button>
          <ion-button
            v-if="canConfigure && config.environment === 'testing'"
            fill="outline"
            data-testid="verifactu-settings-test-invoice"
            :disabled="busy"
            @click="createTestInvoice"
          >
            {{ $t('verifactu.settings.testCreate') }}
          </ion-button>
        </div>
        <div
          v-if="result"
          class="verifactu-settings__result"
          data-testid="verifactu-settings-result"
        >
          <dl class="verifactu-settings__fields">
            <dt>{{ $t('verifactu.settings.ranAt') }}</dt>
            <dd>{{ formatDateTime(result.ran_at, locale) }}</dd>
            <dt>{{ $t('verifactu.settings.route') }}</dt>
            <dd>{{ result.route === 'own' ? $t('verifactu.config.own') : $t('verifactu.config.erplora') }}</dd>
            <dt>{{ $t('verifactu.filters.environment') }}</dt>
            <dd>{{ $t(`verifactu.env.${result.environment}`) }}</dd>
            <dt>{{ $t('verifactu.settings.gateway') }}</dt>
            <dd>{{ result.gateway_configured ? yesNo(result.gateway_ready) : $t('verifactu.settings.notConfigured') }}</dd>
            <dt>{{ $t('verifactu.settings.issuer') }}</dt>
            <dd>{{ yesNo(result.issuer_ready) }}</dd>
            <dt>{{ $t('verifactu.settings.routeReady') }}</dt>
            <dd>{{ yesNo(result.route_ready) }}</dd>
          </dl>
          <InlineFeedback :tone="result.can_send ? 'success' : 'warning'">
            <template v-if="result.can_send">
              {{ $t('verifactu.settings.canSend') }}
            </template>
            <template v-else>
              {{ $t('verifactu.settings.cannotSend') }}
              <ul class="verifactu-settings__reasons">
                <li
                  v-for="reason in result.reasons"
                  :key="reason.code"
                >
                  {{ reason.message }}
                </li>
              </ul>
            </template>
          </InlineFeedback>
        </div>
        <p
          v-else
          class="verifactu-settings__hint"
        >
          {{ $t('verifactu.settings.noTest') }}
        </p>
      </section>

      <section class="verifactu-settings__card">
        <h3>{{ $t('verifactu.settings.declaration') }}</h3>
        <p class="verifactu-settings__hint">
          {{ $t('verifactu.settings.declarationDesc') }}
        </p>
        <a
          :href="config.declaration_url"
          target="_blank"
          rel="noopener"
          data-testid="verifactu-settings-declaration"
        >{{ $t('verifactu.settings.declarationRead') }} ↗</a>
        <dl
          class="verifactu-settings__fields"
          data-testid="verifactu-settings-identity"
        >
          <dt>{{ $t('verifactu.settings.declarationVersion') }}</dt>
          <dd>{{ config.declaration_version }}</dd>
          <template
            v-for="row in identity"
            :key="row.element"
          >
            <dt>{{ row.label }} <code>{{ row.element }}</code></dt>
            <dd>{{ row.value }}</dd>
          </template>
        </dl>
      </section>
    </template>
  </AppPage>
</template>

<style scoped>
.verifactu-settings__card {
  margin-bottom: 1.25rem;
  padding: 1rem;
  border: 1px solid var(--ion-color-light-shade, #e4e1d8);
  border-radius: 12px;
}
.verifactu-settings__card h3 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}
.verifactu-settings__hint {
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.875rem;
}
.verifactu-settings__environment {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.75rem 0 0.25rem;
}
.verifactu-settings__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.verifactu-settings__fields {
  display: grid;
  grid-template-columns: minmax(10rem, max-content) 1fr;
  gap: 0.25rem 1rem;
  margin: 0.75rem 0;
}
.verifactu-settings__fields dt {
  color: var(--ion-color-medium, #8a8577);
}
.verifactu-settings__fields dd {
  margin: 0;
}
.verifactu-settings__fields code {
  font-size: 0.75rem;
}
.verifactu-settings__reasons {
  margin: 0.25rem 0 0;
  padding-inline-start: 1.1rem;
}
@media (max-width: 575px) {
  .verifactu-settings__fields {
    grid-template-columns: 1fr;
  }
}
</style>
