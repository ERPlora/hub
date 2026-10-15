<script setup lang="ts">
// VeriFactu → Configuration (VERIFACTU-F02–F06, F34; the old `erp-verifactu-config`): «VeriFactu configuration» with
// the two routes as tabs. «ERPlora files for you» (opens by default): «Representation authorisation» and its state
// (not signed, under review, approved, returned with the review's note, revoked), managed in the ERPlora account
// («Manage in your ERPlora account»); what the account has not sent yet is said so. «My certificate»: «Loaded» /
// «Not loaded», holder, its tax ID, kind, uploaded and expiry dates and the warning 30 days before it expires (or that
// it expired); who configures VeriFactu uploads the .p12/.pfx here with its password («Upload the certificate») or
// removes it («Remove», asking first in a card). It is kept encrypted in the hub's database and never shown again.
import { formatDateTime, InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonLabel, IonSegment, IonSegmentButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, useTemplateRef } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import { verifactuTabs } from '../tabs';

const EXPIRY_WARNING_DAYS = 30;
/** A business certificate weighs a few KB; anything over 1 MB is not one (the old module's limit). */
const MAX_CERTIFICATE_BYTES = 1024 * 1024;

const t = useT();
const locale = useLocale();
const session = useSession();
const canConfigure = computed(() => session.can('verifactu.configure'));
const { confirm } = useConfirm();
const tab = shallowRef<'erplora' | 'own'>('erplora');

const { data: config, status, error } = useLive('verifactu.config.get', () => ({}));
const upload = useCommand('verifactu.certificate.upload');
const remove = useCommand('verifactu.certificate.remove');
const busy = computed(() => upload.pending.value || remove.pending.value);

const fileInput = useTemplateRef<HTMLInputElement>('fileInput');
const picked = shallowRef<File | null>(null);
const password = shallowRef('');
const problem = shallowRef<string | null>(null);

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

function onPick(): void {
  picked.value = fileInput.value?.files?.[0] ?? null;
  problem.value = null;
  // The same file can be picked again (after fixing its password).
  if (fileInput.value) fileInput.value.value = '';
}

/** The file's bytes in base64: the .p12 travels in the body, never in a URL that a proxy would log. */
async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(binary);
}

async function uploadCertificate(): Promise<void> {
  problem.value = null;
  const file = picked.value;
  if (!file) {
    problem.value = t('verifactu.config.noFile');
    return;
  }
  if (file.size > MAX_CERTIFICATE_BYTES) {
    problem.value = t('verifactu.config.tooLarge');
    return;
  }
  let p12: string;
  try {
    p12 = await toBase64(file);
  } catch {
    problem.value = t('verifactu.config.unreadableFile');
    return;
  }
  let out;
  try {
    out = await upload.run({ p12_base64: p12, password: password.value });
  } catch {
    problem.value = refusal(upload.error.value, t('verifactu.config.uploadFailed'))?.message ?? t('verifactu.config.uploadFailed');
    return;
  }
  picked.value = null;
  password.value = '';
  void toastSuccess(t('verifactu.config.uploadedToast', { holder: out.own_certificate.holder, taxId: out.own_certificate.holder_tax_id }));
}

async function removeCertificate(): Promise<void> {
  problem.value = null;
  const yes = await confirm({
    title: t('verifactu.config.removeTitle'),
    message: t('verifactu.config.removeMessage'),
    confirmLabel: t('verifactu.config.remove'),
    cancelLabel: t('verifactu.cancel'),
    tone: 'danger',
  });
  if (!yes) return;
  try {
    await remove.run({});
  } catch {
    problem.value = refusal(remove.error.value, t('verifactu.config.removeFailed'))?.message ?? t('verifactu.config.removeFailed');
    return;
  }
  void toastSuccess(t('verifactu.config.removedToast'));
}
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

      <section
        v-if="tab === 'erplora'"
        class="verifactu-config__panel"
        data-testid="verifactu-config-erplora"
      >
        <InlineFeedback
          v-if="!config.synced_at"
          tone="info"
          data-testid="verifactu-config-not-synced"
        >
          {{ $t('verifactu.config.notSynced') }}
        </InlineFeedback>
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
        <a
          class="verifactu-config__manage"
          :href="config.account_url"
          target="_blank"
          rel="noopener"
          data-testid="verifactu-config-manage"
        >{{ $t('verifactu.config.manage') }} ↗</a>
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
            <dt>{{ $t('verifactu.config.holderTaxId') }}</dt>
            <dd>{{ config.own_certificate.holder_tax_id || '—' }}</dd>
            <dt>{{ $t('verifactu.config.kind.label') }}</dt>
            <dd>{{ config.own_certificate.kind ? $t(`verifactu.config.kind.${config.own_certificate.kind}`) : '—' }}</dd>
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
        <div
          v-if="canConfigure"
          class="verifactu-config__upload"
          data-testid="verifactu-config-cert-form"
        >
          <p class="verifactu-config__note">
            {{ $t('verifactu.config.certHint') }}
          </p>
          <div class="verifactu-config__file">
            <ion-button
              fill="outline"
              data-testid="verifactu-config-cert-choose"
              :disabled="busy"
              @click="fileInput?.click()"
            >
              <HubIcon
                slot="start"
                name="ion:key-outline"
              />
              {{ $t('verifactu.config.choose') }}
            </ion-button>
            <span
              v-if="picked"
              data-testid="verifactu-config-cert-picked"
            >{{ picked.name }}</span>
            <input
              ref="fileInput"
              type="file"
              accept=".p12,.pfx"
              hidden
              data-testid="verifactu-config-cert-file"
              @change="onPick"
            >
          </div>
          <ion-input
            type="password"
            mode="md"
            fill="outline"
            label-placement="floating"
            autocomplete="off"
            data-testid="verifactu-config-cert-password"
            :label="$t('verifactu.config.password')"
            :value="password"
            @ion-input="password = String($event.detail.value ?? '')"
          />
          <InlineFeedback
            v-if="problem"
            tone="danger"
            data-testid="verifactu-config-cert-error"
          >
            {{ problem }}
          </InlineFeedback>
          <div class="verifactu-config__actions">
            <ion-button
              data-testid="verifactu-config-cert-upload"
              :disabled="busy"
              @click="uploadCertificate"
            >
              {{ upload.pending.value ? $t('verifactu.config.uploading') : $t('verifactu.config.upload') }}
            </ion-button>
            <ion-button
              v-if="config.own_certificate.loaded"
              fill="outline"
              color="danger"
              data-testid="verifactu-config-cert-remove"
              :disabled="busy"
              @click="removeCertificate"
            >
              {{ $t('verifactu.config.remove') }}
            </ion-button>
          </div>
        </div>
        <p
          class="verifactu-config__note"
          data-testid="verifactu-config-keys"
        >
          {{ $t('verifactu.config.keysNote') }}
        </p>
      </section>
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
.verifactu-config__upload {
  display: grid;
  gap: 0.75rem;
  max-width: 32rem;
  margin: 1rem 0;
}
.verifactu-config__file {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
.verifactu-config__file ion-button,
.verifactu-config__actions ion-button {
  margin: 0;
}
.verifactu-config__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
