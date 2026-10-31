<script setup lang="ts">
// The form of «Send a message» (WORKBOOK FLOW-F31; the old module's flows-f15): a «Do something» step of the
// WhatsApp inbox's narrow send (`whatsapp_inbox.message.notify`). To whom is a datum — the customer's exact
// international number, never one typed by hand —; the message goes as it is within the customer's 24 hours;
// after them WhatsApp only lets an approved template through, chosen from the ones the inbox can fill (read live
// from it) with a value for each of its blanks. A template it no longer finds stays chosen and says so.
// A template with a photo, a video or a document at the top (FLOW-F32; the old hub's HUB-F112) goes with a file: its
// own, or the one chosen here, kept at once in the business's files (`whatsapp_inbox.template_sample.upload`, checked
// here first by type and size) and kept by the step as `template.header_sample`; a saved step's file is read by its id.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { bytesToBase64 } from '../../../../base/frontend/lib/data';
import { useLocale, useT } from '../composables/useT';
import { asCallText } from '../lib/document';
import { formatFileSize, HEADER_FILE_RULES, headerFileKind, judgeHeaderFile } from '../lib/headerFile';
import type { CatalogOut, Step } from '../operations';
import ValueBox from './ValueBox.vue';

interface TemplateParam {
  name: string;
  language?: string;
  variables: string[];
  /** The id of the file a photo, video or document header goes with, chosen in the step (FLOW-F32). */
  header_sample?: string;
}

/** A file of a template's header, as the inbox answers it. */
interface HeaderFile {
  id: string;
  header_format: string;
  size: number;
  name: string;
}

const props = defineProps<{
  step: Step;
  index: number;
  steps: readonly Step[];
  catalog: CatalogOut | null;
  /** The server's refusals by field (`steps.<index>.<field>`). */
  errors: Readonly<Record<string, string>>;
  /** Opens the editor's picker for this step; the chosen path, or `null`. */
  pick: () => Promise<string | null>;
}>();
const emit = defineEmits<{ 'update:step': [step: Step] }>();

const t = useT();
const locale = useLocale();
const client = useLiveClient();
// What the inbox can send: approved and filled by the Hub; a photo, video or document header asks for its file.
const templates = useLive('whatsapp_inbox.template.list', { fillable: true, limit: 100 });
const sampleUpload = useCommand('whatsapp_inbox.template_sample.upload');

const id = computed(() => props.step.id);
const params = computed<Record<string, unknown>>(() => (props.step.kind === 'command' ? props.step.params : {}));
const error = (field: string): string | undefined => props.errors[`steps.${props.index}.params.${field}`];

const chosen = computed<TemplateParam | null>(() => {
  const value = params.value.template as TemplateParam | undefined;
  return value && typeof value === 'object' && value.name ? { ...value, variables: [...(value.variables ?? [])] } : null;
});
const rows = computed(() => templates.data.value?.rows ?? []);
const optionOf = (name: string, language = ''): string => `${name}|${language}`;
const known = computed(() => rows.value.find((row) => row.name === chosen.value?.name && (!chosen.value?.language || row.language === chosen.value.language)) ?? null);
/** Chosen, but not among the approved ones read (renamed, deleted…): kept, and said. */
const missing = computed(() => !!chosen.value && !!templates.data.value && !known.value);

// ── The file at the top (FLOW-F32) ──
const fileKind = computed(() => headerFileKind(known.value?.header_format));
/** The file the step chose, by its id: the upload's answer, or read once when the step is opened. */
const stepFile = shallowRef<HeaderFile | null>(null);
const stepFileState = ref<'idle' | 'reading' | 'gone' | 'failed'>('idle');
const fileError = ref('');
const picker = shallowRef<HTMLInputElement | null>(null);
const uploading = computed(() => sampleUpload.pending.value);
/** What goes at the top: the step's own choice, else the template's file. */
const file = computed<HeaderFile | null>(() =>
  chosen.value?.header_sample ? stepFile.value : (known.value?.header_sample ?? null),
);

async function readStepFile(): Promise<void> {
  const sample = chosen.value?.header_sample;
  if (!sample || stepFile.value?.id === sample) return;
  stepFile.value = null;
  stepFileState.value = 'reading';
  try {
    stepFile.value = await client.api.call('whatsapp_inbox.template_sample.detail', { id: sample });
    stepFileState.value = 'idle';
  } catch (err) {
    const code = (err as { code?: string } | null)?.code;
    stepFileState.value = code === 'whatsapp_inbox.sample_not_found' ? 'gone' : 'failed';
  }
}

watch(() => chosen.value?.header_sample, readStepFile, { immediate: true });

async function onPick(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const picked = input.files?.[0];
  input.value = ''; // choosing the same file again is a change too
  const kind = fileKind.value;
  if (!picked || !kind || !chosen.value) return;
  fileError.value = '';
  const verdict = judgeHeaderFile(picked, kind);
  if (verdict !== 'ok') {
    fileError.value =
      verdict === 'type'
        ? t(`flow.message.fileWrongType.${kind}`)
        : t('flow.message.fileTooHeavy', { mb: HEADER_FILE_RULES[kind].maxBytes / (1024 * 1024) });
    return;
  }
  try {
    const kept = await sampleUpload.run({
      header_format: kind,
      name: picked.name,
      content_base64: bytesToBase64(new Uint8Array(await picked.arrayBuffer())),
    });
    stepFile.value = kept;
    stepFileState.value = 'idle';
    setParams({ ...params.value, template: { ...chosen.value, header_sample: kept.id } });
  } catch {
    const refused = sampleUpload.error.value;
    fileError.value = refused?.fields?.content_base64 ?? refused?.message ?? t('flow.message.fileUploadFailed');
  }
}

function setParams(next: Record<string, unknown>): void {
  if (props.step.kind === 'command') emit('update:step', { ...props.step, params: next });
}

function setPhone(value: unknown): void {
  setParams({ ...params.value, phone: value });
}

function setText(value: unknown): void {
  setParams({ ...params.value, text: asCallText(value) });
}

function chooseTemplate(value: string | null | undefined): void {
  const next = { ...params.value };
  if (!value) {
    delete next.template;
    setParams(next);
    return;
  }
  const [name, language = ''] = value.split('|');
  const row = rows.value.find((candidate) => candidate.name === name && candidate.language === language);
  const count = row?.variables ?? chosen.value?.variables.length ?? 0;
  // Another template lets the step's file go: it goes with its own, or asks for one of its kind.
  next.template = { name, language, variables: Array.from({ length: count }, (_, i) => chosen.value?.variables[i] ?? '') };
  fileError.value = '';
  setParams(next);
}

function setVariable(position: number, value: unknown): void {
  if (!chosen.value) return;
  const variables = [...chosen.value.variables];
  variables[position] = asCallText(value);
  setParams({ ...params.value, template: { ...chosen.value, variables } });
}
</script>

<template>
  <div
    class="flow-message"
    :data-testid="`flow-message-${id}`"
  >
    <ValueBox
      :testid="`flow-message-phone-${id}`"
      :model-value="params.phone"
      :label="$t('flow.message.phone')"
      :required="true"
      :error-text="error('phone')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="setPhone"
    />
    <span
      class="flow-card__hint"
      :data-testid="`flow-message-phonehint-${id}`"
    >{{ $t('flow.message.phoneHint') }}</span>
    <ValueBox
      :testid="`flow-message-text-${id}`"
      :model-value="params.text"
      :label="$t('flow.message.text')"
      :error-text="error('text')"
      :steps="steps"
      :catalog="catalog"
      :pick="pick"
      @update:model-value="setText"
    />
    <span
      class="flow-card__hint"
      :data-testid="`flow-message-texthint-${id}`"
    >{{ $t('flow.message.textHint') }}</span>
    <InlineFeedback
      v-if="templates.error.value && !templates.data.value"
      tone="danger"
      :data-testid="`flow-message-templateerror-${id}`"
    >
      {{ $t('flow.message.templatesError') }}
      <IonButton
        size="small"
        fill="clear"
        :data-testid="`flow-message-templateretry-${id}`"
        @click="templates.refresh()"
      >
        {{ $t('flow.live.retry') }}
      </IonButton>
    </InlineFeedback>
    <span
      v-else-if="!templates.data.value"
      class="flow-card__hint"
      :data-testid="`flow-message-templateloading-${id}`"
    >{{ $t('flow.message.templatesLoading') }}</span>
    <IonSelect
      v-else
      :data-testid="`flow-message-template-${id}`"
      :value="chosen ? optionOf(chosen.name, known?.language ?? chosen.language) : ''"
      :label="$t('flow.message.template')"
      label-placement="floating"
      fill="outline"
      mode="md"
      interface="popover"
      :error-text="error('template')"
      :class="{ 'ion-invalid ion-touched': !!error('template') }"
      @ion-change="chooseTemplate($event.detail.value)"
    >
      <IonSelectOption value="">
        {{ $t('flow.message.noTemplate') }}
      </IonSelectOption>
      <IonSelectOption
        v-for="row in rows"
        :key="row.id"
        :value="optionOf(row.name, row.language)"
      >
        {{ row.name }} ({{ row.language }})
      </IonSelectOption>
      <IonSelectOption
        v-if="missing && chosen"
        :value="optionOf(chosen.name, chosen.language)"
      >
        {{ chosen.name }}
      </IonSelectOption>
    </IonSelect>
    <span
      class="flow-card__hint"
      :data-testid="`flow-message-templatehint-${id}`"
    >{{ $t('flow.message.templateHint') }}</span>
    <span
      v-if="templates.data.value && !rows.length && !chosen"
      class="flow-card__hint"
      :data-testid="`flow-message-notemplates-${id}`"
    >{{ $t('flow.message.noTemplates') }}</span>
    <InlineFeedback
      v-if="missing && chosen"
      tone="warning"
      :data-testid="`flow-message-missing-${id}`"
    >
      {{ $t('flow.message.missing', { name: chosen.name }) }}
    </InlineFeedback>
    <template v-if="chosen">
      <p
        v-if="known"
        class="flow-message__preview"
        :data-testid="`flow-message-preview-${id}`"
      >
        {{ known.body }}
      </p>
      <div
        v-if="fileKind"
        class="flow-message__file"
        :data-testid="`flow-message-file-${id}`"
      >
        <div class="flow-message__file-row">
          <span
            v-if="file"
            class="flow-message__file-name"
            :data-testid="`flow-message-file-name-${id}`"
          >{{ $t('flow.message.fileName', { kind: $t(`flow.message.fileKinds.${fileKind}`), name: file.name, size: formatFileSize(file.size, locale) }) }}</span>
          <span
            v-else-if="stepFileState === 'reading'"
            class="flow-card__hint"
            :data-testid="`flow-message-file-reading-${id}`"
          >{{ $t('flow.message.fileReading') }}</span>
          <span
            v-else
            class="flow-card__hint"
            :data-testid="`flow-message-file-empty-${id}`"
          >{{ $t('flow.message.fileNone') }}</span>
          <IonButton
            fill="outline"
            size="small"
            :disabled="uploading"
            :data-testid="`flow-message-file-choose-${id}`"
            @click="picker?.click()"
          >
            <IonSpinner
              v-if="uploading"
              slot="start"
              name="crescent"
            />
            {{ uploading ? $t('flow.message.fileUploading') : file ? $t('flow.message.fileChange') : $t('flow.message.fileChoose') }}
          </IonButton>
        </div>
        <span
          class="flow-card__hint"
          :data-testid="`flow-message-file-rules-${id}`"
        >{{ $t(`flow.message.fileRules.${fileKind}`) }} {{ $t('flow.message.fileGoes') }}</span>
        <InlineFeedback
          v-if="stepFileState === 'gone'"
          tone="warning"
          :data-testid="`flow-message-file-gone-${id}`"
        >
          {{ $t('flow.message.fileGone') }}
        </InlineFeedback>
        <InlineFeedback
          v-else-if="stepFileState === 'failed'"
          tone="danger"
          :data-testid="`flow-message-file-readerror-${id}`"
        >
          {{ $t('flow.message.fileReadFailed') }}
          <IonButton
            size="small"
            fill="clear"
            :data-testid="`flow-message-file-retry-${id}`"
            @click="readStepFile()"
          >
            {{ $t('flow.live.retry') }}
          </IonButton>
        </InlineFeedback>
        <InlineFeedback
          v-else-if="!file && stepFileState !== 'reading'"
          tone="warning"
          :data-testid="`flow-message-file-missing-${id}`"
        >
          {{ $t(`flow.message.fileMissing.${fileKind}`) }}
        </InlineFeedback>
        <p
          v-if="fileError"
          class="flow-message__file-error"
          role="alert"
          :data-testid="`flow-message-file-error-${id}`"
        >
          {{ fileError }}
        </p>
        <input
          ref="picker"
          type="file"
          hidden
          :accept="HEADER_FILE_RULES[fileKind].accept"
          :data-testid="`flow-message-file-input-${id}`"
          @change="onPick"
        >
      </div>
      <ValueBox
        v-for="(value, position) in chosen.variables"
        :key="position"
        :testid="`flow-message-var-${id}-${position}`"
        :model-value="value"
        :label="$t('flow.message.variable', { n: position + 1 })"
        :required="true"
        :steps="steps"
        :catalog="catalog"
        :pick="pick"
        @update:model-value="setVariable(position, $event)"
      />
    </template>
  </div>
</template>

<style scoped src="./spine.css"></style>
<style scoped>
.flow-message {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}
.flow-message__preview {
  margin: 0;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--ep-border-soft, rgba(0, 0, 0, 0.08));
  border-radius: 0.5rem;
  background: var(--ep-surface, var(--ion-card-background, #fff));
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.flow-message__file {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}
.flow-message__file-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  min-width: 0;
}
.flow-message__file-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
.flow-message__file-error {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-danger);
}
</style>
