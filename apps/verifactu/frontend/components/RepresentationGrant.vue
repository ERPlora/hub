<script setup lang="ts">
// «ERPlora files for you» → the representation authorisation (Anexo I of Convenio 17; VERIFACTU-F05, F06), the
// old module's `erp-verifactu-grant`. ERPlora files the business's records ON ITS BEHALF, and that needs its signed
// consent: the blank official model is downloaded here, signed away from the screen (by hand and scanned, or with
// AutoFirma) and uploaded with the signer's identity document; a person at ERPlora reviews it and its state comes
// back from the account. Its state first, in plain words; what was sent and its steps; «Send again» while it is under
// review or in force (asked for, never assumed: a duplicate is what a reviewer untangles by hand); the procedure when
// there is something to do. The taxpayer is Invoicing's issuer, read and never asked here; a self-employed business
// signs itself, a company names its legal representative and proves it. Every file is a PDF of 5 MB at most and
// travels in the body; the Hub keeps none of them. A refusal is said by its code.
import { formatDateTime, InlineFeedback, type InlineFeedbackTone } from '@erplora/ui/components';
import { ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, reactive, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { fileToBase64, saveBase64File } from '../lib/files';
import { refusal } from '../lib/refusal';
import type { ConfigOut, RepresentationDocument, RepresentationOut, RepresentationSubmitIn } from '../operations';

const props = defineProps<{ config: ConfigOut; canConfigure: boolean }>();

/** The contract's ceiling per document (the old module took 10 MB). */
const MAX_DOCUMENT_BYTES = 5 * 1024 * 1024;
const DOCUMENTS: RepresentationDocument[] = ['signed_model', 'id_copy', 'signature_sample', 'representation_proof'];
/** The refusals said in the person's words, by their code (`fiscal.*` from the SaaS or the Hub, `verifactu.*`). */
const KNOWN_REFUSALS = new Set([
  'signer_required',
  'document_type_invalid',
  'signed_model_required',
  'signed_model_not_pdf',
  'id_copy_required',
  'signature_sample_required',
  'representation_proof_required',
  'document_too_large',
  'document_not_pdf',
  'taxpayer_tax_id_invalid',
  'body_too_large',
  'payload_too_large',
  'hub_unregistered',
  'issuer_missing',
  'saas_unreachable',
]);
const TONES: Record<RepresentationOut['status'], InlineFeedbackTone> = {
  none: 'warning',
  submitted: 'info',
  approved: 'success',
  returned: 'danger',
  revoked: 'danger',
};

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const send = useCommand('verifactu.representation.submit');

/** What the command answered, until the live configuration catches up. */
const answered = shallowRef<RepresentationOut | null>(null);
watch(
  () => props.config.representation,
  () => {
    answered.value = null;
  },
);
const grant = computed(() => answered.value ?? props.config.representation);

const resendOpen = shallowRef(false);
const signerName = shallowRef('');
const signerNif = shallowRef('');
const documentType = shallowRef<'dni' | 'nie'>('dni');
const files = reactive<Record<RepresentationDocument, File | null>>({
  signed_model: null,
  id_copy: null,
  signature_sample: null,
  representation_proof: null,
});
const downloading = shallowRef(false);
const downloaded = shallowRef(false);
const problem = shallowRef<string | null>(null);

const date = (value: string | null | undefined) => (value ? formatDateTime(value, locale.value) : '—');
const company = computed(() => grant.value.company);
const issuerReady = computed(() => props.config.issuer_nif.trim() !== '');
const canResend = computed(() => grant.value.status === 'submitted' || grant.value.status === 'approved');
const showForm = computed(() => props.canConfigure && (!canResend.value || resendOpen.value));
const needsSample = computed(() => documentType.value === 'nie');
const shownDocuments = computed(() =>
  DOCUMENTS.filter((name) => {
    if (name === 'signature_sample') return needsSample.value;
    if (name === 'representation_proof') return company.value;
    return true;
  }),
);
const canSubmit = computed(
  () =>
    grant.value.linked &&
    issuerReady.value &&
    !send.pending.value &&
    files.signed_model !== null &&
    files.id_copy !== null &&
    (!needsSample.value || files.signature_sample !== null) &&
    (!company.value || (files.representation_proof !== null && signerName.value.trim() !== '' && signerNif.value.trim() !== '')),
);
const sentDocuments = computed(() => DOCUMENTS.filter((name) => grant.value.submission?.documents.includes(name)));

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const key = error.code.replace(/^(fiscal|verifactu)\./, '');
    if (KNOWN_REFUSALS.has(key)) return t(`verifactu.grant.errors.${key}`);
  }
  return refusal(error, t('verifactu.grant.failed'))?.message ?? t('verifactu.grant.failed');
}

function onPick(name: RepresentationDocument, event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  problem.value = null;
  // The same file can be picked again (after it was removed).
  input.value = '';
  if (file && file.size > MAX_DOCUMENT_BYTES) {
    problem.value = t('verifactu.grant.tooLarge');
    return;
  }
  files[name] = file;
}

/** Each document's hidden file input, opened by its «Attach…» button. */
const inputs: Partial<Record<RepresentationDocument, HTMLInputElement>> = {};

function keepInput(name: RepresentationDocument, el: unknown): void {
  if (el instanceof HTMLInputElement) inputs[name] = el;
  else delete inputs[name];
}

function choose(name: RepresentationDocument): void {
  inputs[name]?.click();
}

async function downloadModel(): Promise<void> {
  problem.value = null;
  downloading.value = true;
  try {
    const model = await client.api.call('verifactu.representation.model', {});
    saveBase64File(model.filename, model.content_type, model.content_base64);
    downloaded.value = true;
  } catch (error) {
    problem.value = errorText(error);
  } finally {
    downloading.value = false;
  }
}

async function submit(): Promise<void> {
  problem.value = null;
  const { signed_model: signed, id_copy: idCopy, signature_sample: sample, representation_proof: proof } = files;
  if (!signed || !idCopy) return;
  let input: RepresentationSubmitIn;
  try {
    input = {
      signer_document_type: documentType.value,
      signed_model_base64: await fileToBase64(signed),
      id_copy_base64: await fileToBase64(idCopy),
    };
    if (company.value) {
      input.signer_name = signerName.value.trim();
      input.signer_tax_id = signerNif.value.trim();
      if (proof) input.representation_proof_base64 = await fileToBase64(proof);
    }
    if (needsSample.value && sample) input.signature_sample_base64 = await fileToBase64(sample);
  } catch {
    problem.value = t('verifactu.grant.unreadableFile');
    return;
  }
  let out: ConfigOut;
  try {
    out = await send.run(input);
  } catch (error) {
    problem.value = errorText(error);
    return;
  }
  answered.value = out.representation;
  for (const name of DOCUMENTS) files[name] = null;
  resendOpen.value = false;
  downloaded.value = false;
  void toastSuccess(t('verifactu.grant.sentToast'));
}

function historyLabel(step: RepresentationOut['history'][number]): string {
  if (step.status === 'submitted' && step.version !== null) return t('verifactu.grant.historySent', { n: step.version });
  return t(`verifactu.grant.history.${step.status}`);
}
</script>

<template>
  <div class="representation-grant">
    <h3>{{ $t('verifactu.config.grantTitle') }}</h3>
    <InlineFeedback
      :tone="TONES[grant.status]"
      data-testid="verifactu-config-grant"
    >
      {{ $t(`verifactu.config.grant.${grant.status}`, { date: date(grant.updated_at) }) }}
    </InlineFeedback>
    <InlineFeedback
      v-if="grant.reason"
      tone="danger"
      data-testid="verifactu-config-grant-reason"
    >
      {{ $t('verifactu.config.reviewNote') }}: {{ grant.reason }}
    </InlineFeedback>

    <div
      v-if="grant.submission"
      class="representation-grant__block"
      data-testid="verifactu-grant-submitted"
    >
      <h4>{{ $t('verifactu.grant.submittedTitle') }}</h4>
      <p class="representation-grant__hint">
        {{ $t('verifactu.grant.submittedOn', { n: grant.submission.version, date: date(grant.submission.submitted_at) }) }}
      </p>
      <ul class="representation-grant__docs">
        <li
          v-for="name in sentDocuments"
          :key="name"
          :data-testid="`verifactu-grant-doc-${name}`"
        >
          <HubIcon name="ion:checkmark-circle-outline" />{{ $t(`verifactu.grant.doc.${name}`) }}
        </li>
      </ul>
    </div>

    <div
      v-if="grant.history.length > 1"
      class="representation-grant__block"
      data-testid="verifactu-grant-history"
    >
      <h4>{{ $t('verifactu.grant.historyTitle') }}</h4>
      <ul class="representation-grant__rows">
        <li
          v-for="(step, index) in grant.history"
          :key="index"
          data-testid="verifactu-grant-history-row"
        >
          <span class="representation-grant__when">{{ date(step.at) }}</span>
          <span>{{ historyLabel(step) }}{{ step.reason ? `: ${step.reason}` : '' }}</span>
        </li>
      </ul>
    </div>

    <template v-if="canConfigure && canResend">
      <div
        v-if="!resendOpen"
        class="representation-grant__actions"
      >
        <ion-button
          fill="outline"
          size="small"
          data-testid="verifactu-grant-resend"
          @click="resendOpen = true"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
          />
          {{ $t('verifactu.grant.resend') }}
        </ion-button>
      </div>
      <template v-else>
        <InlineFeedback
          tone="info"
          data-testid="verifactu-grant-resend-hint"
        >
          {{ grant.status === 'approved' ? $t('verifactu.grant.resendHintInForce') : $t('verifactu.grant.resendHintPending') }}
        </InlineFeedback>
        <div class="representation-grant__actions">
          <ion-button
            fill="clear"
            size="small"
            data-testid="verifactu-grant-resend-cancel"
            @click="resendOpen = false"
          >
            {{ $t('verifactu.grant.resendCancel') }}
          </ion-button>
        </div>
      </template>
    </template>

    <section
      v-if="showForm"
      class="representation-grant__form"
      data-testid="verifactu-grant-form"
    >
      <p
        class="representation-grant__hint"
        data-testid="verifactu-grant-intro"
      >
        {{ $t('verifactu.grant.intro') }}
      </p>
      <InlineFeedback
        v-if="!issuerReady"
        tone="warning"
        data-testid="verifactu-grant-issuer-missing"
      >
        {{ $t('verifactu.grant.issuerMissing') }}
      </InlineFeedback>
      <p
        v-else
        data-testid="verifactu-grant-taxpayer"
      >
        {{ $t('verifactu.grant.taxpayer', { name: config.issuer_name, taxId: config.issuer_nif }) }}
      </p>
      <InlineFeedback
        v-if="!grant.linked"
        tone="warning"
        data-testid="verifactu-grant-not-linked"
      >
        {{ $t('verifactu.grant.notLinked') }}
      </InlineFeedback>

      <h4>{{ $t('verifactu.grant.step1Title') }}</h4>
      <p class="representation-grant__hint">
        {{ $t('verifactu.grant.step1Hint') }}
      </p>
      <template v-if="company">
        <h4 data-testid="verifactu-grant-legal-representative">
          {{ $t('verifactu.grant.legalRepresentative') }}
        </h4>
        <p class="representation-grant__hint">
          {{ $t('verifactu.grant.legalRepresentativeHint') }}
        </p>
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          autocomplete="name"
          data-testid="verifactu-grant-signer-name"
          :label="$t('verifactu.grant.signerName')"
          :value="signerName"
          @ion-input="signerName = String($event.detail.value ?? '')"
        />
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          autocomplete="off"
          data-testid="verifactu-grant-signer-nif"
          :label="$t('verifactu.grant.signerNif')"
          :value="signerNif"
          @ion-input="signerNif = String($event.detail.value ?? '')"
        />
      </template>
      <div class="representation-grant__actions">
        <ion-button
          data-testid="verifactu-grant-download"
          :disabled="downloading"
          @click="downloadModel"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
          />
          {{ downloading ? $t('verifactu.grant.downloading') : $t('verifactu.grant.downloadModel') }}
        </ion-button>
      </div>
      <InlineFeedback
        v-if="downloaded"
        tone="success"
        data-testid="verifactu-grant-downloaded"
      >
        {{ $t('verifactu.grant.downloaded') }}
      </InlineFeedback>
      <p class="representation-grant__hint">
        {{ $t('verifactu.grant.howToByHand') }}
      </p>
      <p class="representation-grant__hint">
        {{ $t('verifactu.grant.howToElectronic') }}
      </p>

      <!-- The essentials of art. 13 GDPR go HERE, before anybody uploads an identity document, not in a link at the end. -->
      <div
        class="representation-grant__privacy"
        data-testid="verifactu-grant-privacy"
      >
        <p class="representation-grant__privacy-title">
          {{ $t('verifactu.grant.privacyTitle') }}
        </p>
        <p>{{ $t('verifactu.grant.privacyController') }}</p>
        <p>{{ $t('verifactu.grant.privacyPurpose') }}</p>
        <p>{{ $t('verifactu.grant.privacyRights') }}</p>
      </div>

      <h4>{{ $t('verifactu.grant.step2Title') }}</h4>
      <p class="representation-grant__hint">
        {{ $t('verifactu.grant.step2Hint') }}
      </p>
      <ion-select
        mode="md"
        fill="outline"
        label-placement="floating"
        interface="popover"
        data-testid="verifactu-grant-document-type"
        :label="$t('verifactu.grant.documentType')"
        :value="documentType"
        @ion-change="documentType = $event.detail.value === 'nie' ? 'nie' : 'dni'"
      >
        <ion-select-option value="dni">
          {{ $t('verifactu.grant.documentTypeDni') }}
        </ion-select-option>
        <ion-select-option value="nie">
          {{ $t('verifactu.grant.documentTypeNie') }}
        </ion-select-option>
      </ion-select>
      <div
        v-for="name in shownDocuments"
        :key="name"
        class="representation-grant__file"
      >
        <p
          v-if="name === 'signature_sample'"
          class="representation-grant__hint"
          data-testid="verifactu-grant-signature-sample-why"
        >
          {{ $t('verifactu.grant.signatureSampleWhy') }}
        </p>
        <p
          v-if="name === 'representation_proof'"
          class="representation-grant__hint"
          data-testid="verifactu-grant-representation-proof-why"
        >
          {{ $t('verifactu.grant.representationProofWhy') }}
        </p>
        <div class="representation-grant__picker">
          <ion-button
            fill="outline"
            :data-testid="`verifactu-grant-choose-${name}`"
            :disabled="send.pending.value"
            @click="choose(name)"
          >
            <HubIcon
              slot="start"
              name="ion:file-tray-outline"
            />
            {{ $t(`verifactu.grant.choose.${name}`) }}
          </ion-button>
          <span
            v-if="files[name]"
            class="representation-grant__picked"
            :data-testid="`verifactu-grant-picked-${name}`"
          >
            <HubIcon name="ion:checkmark-circle-outline" />{{ files[name]?.name }}
            <ion-button
              fill="clear"
              size="small"
              color="medium"
              :aria-label="$t('verifactu.grant.remove', { name: files[name]?.name ?? '' })"
              :data-testid="`verifactu-grant-remove-${name}`"
              @click="files[name] = null"
            >
              <HubIcon
                slot="icon-only"
                name="ion:close-circle-outline"
              />
            </ion-button>
          </span>
          <input
            :ref="(el) => keepInput(name, el)"
            type="file"
            accept=".pdf,application/pdf"
            hidden
            :data-testid="`verifactu-grant-file-${name}`"
            @change="onPick(name, $event)"
          >
        </div>
      </div>
      <InlineFeedback
        v-if="problem"
        tone="danger"
        data-testid="verifactu-grant-error"
      >
        {{ problem }}
      </InlineFeedback>
      <div class="representation-grant__actions">
        <ion-button
          data-testid="verifactu-grant-submit"
          :disabled="!canSubmit"
          @click="submit"
        >
          {{ send.pending.value ? $t('verifactu.grant.sending') : $t('verifactu.grant.submit') }}
        </ion-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.representation-grant {
  display: grid;
  gap: 0.75rem;
}
.representation-grant h3 {
  margin: 0;
  font-size: 0.95rem;
}
.representation-grant h4 {
  margin: 0.5rem 0 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8a8577);
}
.representation-grant__hint {
  margin: 0;
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.85rem;
}
.representation-grant__block,
.representation-grant__form {
  display: grid;
  gap: 0.5rem;
}
.representation-grant__form {
  max-width: 40rem;
}
.representation-grant__docs,
.representation-grant__rows {
  display: grid;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.representation-grant__docs li,
.representation-grant__picked {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
}
.representation-grant__docs li :deep(svg),
.representation-grant__picked > :deep(svg) {
  color: var(--ion-color-success, #2dd36f);
}
.representation-grant__rows li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 0.75rem;
  padding: 0.3rem 0;
  border-bottom: 1px solid var(--ion-color-light, #eceef1);
  font-size: 0.85rem;
}
.representation-grant__when {
  color: var(--ion-color-medium, #8a8577);
}
.representation-grant__privacy {
  display: grid;
  gap: 0.35rem;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  background: var(--ion-color-light, #f4f5f8);
}
.representation-grant__privacy p {
  margin: 0;
  font-size: 0.8rem;
}
.representation-grant__privacy-title {
  font-weight: 600;
}
.representation-grant__file,
.representation-grant__picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.representation-grant__file {
  flex-direction: column;
  align-items: flex-start;
}
.representation-grant__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.representation-grant ion-button {
  min-height: 44px;
  margin: 0;
}
</style>
