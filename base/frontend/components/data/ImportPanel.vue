<script setup lang="ts">
// Settings › Data › Import (BASE-G103–G107; the old hub's ImportPanel): only for who administers the hub. It opens
// with the last import that did not go in whole, when there is one (its report, «Retry what is missing», «See the
// templates»); otherwise «Choose what to load»: the catalogue and «Upload from file». Choosing reads the template or
// the file (`base.blueprint.inspect`, nothing written) → «Review what it brings» → `base.blueprint.import` → its
// report. What cannot be read says why and stays on the choice; an import refused stays on the review.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';

import { bytesToBase64, MAX_FILE_BYTES } from '../../lib/data';
import { useBaseI18n } from '../../lib/i18n';
import type { BlueprintSource, BlueprintSummary, ImportRow, Template } from '../../operations';
import BlueprintReview from './BlueprintReview.vue';
import ImportReport from './ImportReport.vue';
import TemplateCatalog from './TemplateCatalog.vue';
import '../../data.css';

type Step =
  | { kind: 'choose' }
  | { kind: 'review'; source: BlueprintSource; summary: BlueprintSummary }
  | { kind: 'report'; load: ImportRow };

const { t } = useBaseI18n();
const session = useSession();
const admin = session.can('base.administer_hub');
const imports = admin ? useLive('base.import.list', {}) : undefined;
const inspect = useCommand('base.blueprint.inspect');
const importer = useCommand('base.blueprint.import');

const step = ref<Step>({ kind: 'choose' });
/** The last unfinished import was seen through this visit: the catalogue comes next. */
const pastUnfinished = ref(false);
const reading = ref('');
const readError = ref('');
const importError = ref('');
const retryError = ref('');
const fileInput = ref<HTMLInputElement | null>(null);

const unfinished = computed(() =>
  step.value.kind === 'choose' && !pastUnfinished.value ? (imports?.data.value?.unfinished ?? null) : null,
);

const reason = (error: unknown) => (error as ApiError | undefined)?.message ?? String(error);

async function open(source: BlueprintSource, label: string): Promise<void> {
  readError.value = '';
  reading.value = label;
  try {
    const summary = await inspect.run(source);
    importError.value = '';
    step.value = { kind: 'review', source, summary };
  } catch (error) {
    readError.value = t('base.data.import.readError', { reason: reason(error) });
  } finally {
    reading.value = '';
  }
}

function useTemplate(template: Template): void {
  void open({ template: template.key }, template.key);
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  // Emptied at once, so the same file can be chosen again after an error.
  input.value = '';
  if (!file) return;
  if (file.size > MAX_FILE_BYTES) {
    readError.value = t('base.data.import.readError', { reason: t('base.data.import.tooBig') });
    return;
  }
  reading.value = 'file';
  let content: string;
  try {
    content = bytesToBase64(new Uint8Array(await file.arrayBuffer()));
  } catch (error) {
    reading.value = '';
    readError.value = t('base.data.import.readError', { reason: reason(error) });
    return;
  }
  await open({ file_base64: content }, 'file');
}

async function load(apps: string[]): Promise<void> {
  if (step.value.kind !== 'review') return;
  importError.value = '';
  try {
    const done = await importer.run({ ...step.value.source, apps });
    pastUnfinished.value = true;
    step.value = { kind: 'report', load: done };
  } catch (error) {
    importError.value = reason(error);
  }
}

async function retry(of: ImportRow): Promise<void> {
  retryError.value = '';
  try {
    const done = await importer.run({ retry_of: of.id });
    pastUnfinished.value = true;
    step.value = { kind: 'report', load: done };
  } catch (error) {
    retryError.value = reason(error);
  }
}

function toCatalogue(): void {
  pastUnfinished.value = true;
  retryError.value = '';
  step.value = { kind: 'choose' };
}
</script>

<template>
  <EmptyState
    v-if="!admin"
    icon="ion:file-tray-outline"
    :message="t('base.data.import.adminOnly')"
    data-testid="import-admin-only"
  />

  <ImportReport
    v-else-if="unfinished"
    :load="unfinished"
    unfinished
    :retrying="importer.pending.value"
    :retry-error="retryError"
    @retry="retry(unfinished)"
    @templates="toCatalogue"
  />

  <BlueprintReview
    v-else-if="step.kind === 'review'"
    :summary="step.summary"
    :pending="importer.pending.value"
    :error="importError"
    @import="load"
    @back="toCatalogue"
  />

  <ImportReport
    v-else-if="step.kind === 'report'"
    :load="step.load"
    :retrying="importer.pending.value"
    :retry-error="retryError"
    @retry="retry(step.load)"
    @templates="toCatalogue"
  />

  <div
    v-else
    class="data-stack"
  >
    <p class="data-hint">
      {{ t('base.data.import.intro') }}
    </p>
    <div class="data-head">
      <div>
        <h3 class="data-title">
          {{ t('base.data.import.chooseTitle') }}
        </h3>
        <p class="data-hint">
          {{ t('base.data.import.chooseHint') }}
        </p>
      </div>
      <ion-button
        fill="outline"
        data-testid="import-upload"
        :disabled="reading !== ''"
        @click="fileInput?.click()"
      >
        <ion-spinner
          v-if="reading === 'file'"
          slot="start"
          name="crescent"
        />
        <HubIcon
          v-else
          slot="start"
          name="ion:cloud-upload-outline"
        />
        {{ t('base.data.import.upload') }}
      </ion-button>
      <input
        ref="fileInput"
        class="import-file"
        type="file"
        accept=".zip,application/zip"
        data-testid="import-file"
        :aria-label="t('base.data.import.upload')"
        @change="onFile"
      >
    </div>
    <InlineFeedback
      v-if="readError"
      tone="danger"
      data-testid="import-read-error"
    >
      {{ readError }}
    </InlineFeedback>
    <TemplateCatalog
      :busy="reading === 'file' ? '' : reading"
      @use="useTemplate"
    />
  </div>
</template>

<style scoped>
.import-file {
  display: none;
}
</style>
