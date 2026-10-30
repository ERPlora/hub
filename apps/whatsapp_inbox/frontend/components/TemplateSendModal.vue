<script setup lang="ts">
// WHATSAPP_INBOX-F33 (send a template): the only way to write after Meta's 24-hour window, and the way
// to start a conversation. The templates Meta approved (the local copy erplora.com keeps in step) are
// offered (the ones the Hub can fill) with their language, category and text; the chosen one asks for its variables and previews
// the text as it will go out. A photo, video or document header goes with a file: the template's own (made here), which
// may be changed, or the one chosen now (made in WhatsApp Manager), kept at once in the business's files
// (`whatsapp_inbox.template_sample.upload`, checked here first by type and size), shown with its thumbnail (`HeaderFilePreview`). «Send» goes through erplora.com (`whatsapp_inbox.message.send`) with a key
// of its own, so pressing it again never sends twice; the dialog closes only when it was sent, and a
// refusal (marketing without consent, erplora.com down) stays on top of it.
import { FormModal } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonItem, IonLabel, IonRadio, IonRadioGroup, IonSpinner } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { acceptsSample, fileToBase64, formatSize, SAMPLE_RULES } from '../lib/files';
import { renderTemplate } from '../lib/thread';
import type { FileHeaderFormat, TemplateOut, TemplateSampleOut } from '../operations';
import HeaderFilePreview from './HeaderFilePreview.vue';

const props = defineProps<{ conversationId: string }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
// What the inbox can send now: approved, not being deleted; a file header with the file chosen (WHATSAPP_INBOX-F33).
const { data: templates } = useLive('whatsapp_inbox.template.list', () => ({ fillable: true, limit: 100 }));
const { run, error, pending } = useCommand('whatsapp_inbox.message.send');
const sampleUpload = useCommand('whatsapp_inbox.template_sample.upload');
const uploading = computed(() => sampleUpload.pending.value);
const locale = useLocale();
const FILE_HEADERS: readonly string[] = ['IMAGE', 'VIDEO', 'DOCUMENT'];
const MB = 1024 * 1024;
const sample = ref<TemplateSampleOut | null>(null);
const fileError = ref('');
const picker = shallowRef<HTMLInputElement | null>(null);

const chosenId = ref('');
const values = ref<string[]>([]);
/** One key per template being sent: a retry after a silence never sends it twice. */
const key = ref(crypto.randomUUID());

const chosen = computed<TemplateOut | undefined>(() => templates.value?.rows.find((row) => row.id === chosenId.value));
const fileKind = computed<FileHeaderFormat | null>(() =>
  chosen.value && FILE_HEADERS.includes(chosen.value.header_format) ? (chosen.value.header_format as FileHeaderFormat) : null,
);
const fileReady = computed(() => fileKind.value === null || (sample.value !== null && !uploading.value));
const complete = computed(
  () => !!chosen.value && values.value.length === chosen.value.variables && values.value.every((v) => v.trim() !== '') && fileReady.value,
);
const preview = computed(() => (chosen.value ? renderTemplate(chosen.value.body, values.value.map((v) => v.trim())) : ''));

function reset(): void {
  chosenId.value = '';
  values.value = [];
  key.value = crypto.randomUUID();
  error.value = null;
  sample.value = null;
  fileError.value = '';
}

function choose(id: unknown): void {
  // The key stays until the hub takes the message: a failed send may have reached it.
  chosenId.value = String(id ?? '');
  values.value = Array.from({ length: chosen.value?.variables ?? 0 }, () => '');
  sample.value = chosen.value?.header_sample ?? null; // one made here comes with its own file
  fileError.value = '';
}

async function onPick(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = ''; // choosing the same file again is a change too
  const kind = fileKind.value;
  if (!file || !kind) return;
  fileError.value = '';
  const verdict = acceptsSample(file, kind);
  if (verdict !== 'ok') {
    fileError.value =
      verdict === 'type'
        ? t(`whatsapp_inbox.templates.editor.fileWrongType.${kind}`)
        : t('whatsapp_inbox.templates.editor.fileTooHeavy', { mb: SAMPLE_RULES[kind].maxBytes / MB });
    return;
  }
  try {
    sample.value = await sampleUpload.run({ header_format: kind, name: file.name, content_base64: await fileToBase64(file) });
  } catch {
    const refused = sampleUpload.error.value;
    fileError.value = refused?.fields?.content_base64 ?? refused?.message ?? t('whatsapp_inbox.templates.editor.fileUploadFailed');
  }
}

function setValue(index: number, value: unknown): void {
  const next = [...values.value];
  next[index] = value == null ? '' : String(value);
  values.value = next;
}

async function send(): Promise<void> {
  const template = chosen.value;
  if (!template || !complete.value) return;
  try {
    await run({
      id: props.conversationId,
      template: {
        name: template.name,
        language: template.language,
        variables: values.value.map((v) => v.trim()),
        ...(fileKind.value && sample.value ? { header_sample: sample.value.id } : {}),
      },
      client_message_id: key.value,
    });
  } catch {
    return; // `error` holds it and the dialog paints it.
  }
  reset();
  open.value = false;
}

watch(open, (isOpen) => {
  if (!isOpen) reset();
});
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="whatsapp-inbox-template-form"
    :title="t('whatsapp_inbox.templates.sendTitle')"
    :submit-label="t('whatsapp_inbox.templates.send')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="send"
    @cancel="reset"
  >
    <div class="wa-template">
      <p
        v-if="templates && !templates.rows.length"
        class="wa-template__none"
        data-testid="whatsapp-inbox-template-none"
      >
        {{ $t('whatsapp_inbox.templates.none') }}
      </p>
      <ion-radio-group
        v-else
        :value="chosenId"
        :aria-label="$t('whatsapp_inbox.templates.pick')"
        data-testid="whatsapp-inbox-template-pick"
        @ion-change="choose($event.detail.value)"
      >
        <ion-item
          v-for="row in templates?.rows ?? []"
          :key="row.id"
          lines="full"
        >
          <ion-radio
            :value="row.id"
            justify="start"
            label-placement="end"
          >
            <ion-label class="ion-text-wrap">
              <div :data-testid="`whatsapp-inbox-template-option-${row.id}`">
                <strong>{{ row.name }}</strong>
                <span class="wa-template__meta"> · {{ row.language }} · {{ $t(`whatsapp_inbox.templates.categories.${row.category}`) }}</span>
                <p>{{ row.body }}</p>
              </div>
            </ion-label>
          </ion-radio>
        </ion-item>
      </ion-radio-group>
      <template v-if="chosen">
        <div
          v-if="fileKind"
          class="wa-template__file"
          data-testid="whatsapp-inbox-template-file"
        >
          <div class="wa-template__file-row">
            <HeaderFilePreview
              v-if="sample"
              :sample="sample"
              testid="whatsapp-inbox-template-file-preview"
            >
              <p data-testid="whatsapp-inbox-template-file-name">
                {{ t(`whatsapp_inbox.templates.editor.headerFormats.${fileKind}`) }}:
                <strong>{{ sample.name }}</strong> · {{ formatSize(sample.size, locale) }}
              </p>
            </HeaderFilePreview>
            <p
              v-else
              class="wa-template__meta"
              data-testid="whatsapp-inbox-template-file-empty"
            >
              {{ $t('whatsapp_inbox.templates.editor.noFile') }}
            </p>
            <ion-button
              fill="outline"
              size="small"
              :disabled="uploading"
              data-testid="whatsapp-inbox-template-file-choose"
              @click="picker?.click()"
            >
              <ion-spinner
                v-if="uploading"
                slot="start"
                name="crescent"
              />
              {{ uploading ? $t('whatsapp_inbox.templates.editor.uploading') : sample ? $t('whatsapp_inbox.templates.editor.changeFile') : $t('whatsapp_inbox.templates.editor.chooseFile') }}
            </ion-button>
          </div>
          <p
            class="wa-template__meta"
            data-testid="whatsapp-inbox-template-file-rules"
          >
            {{ t(`whatsapp_inbox.templates.editor.fileRules.${fileKind}`) }}
            {{ $t('whatsapp_inbox.templates.sendFile') }}
          </p>
          <p
            v-if="fileError"
            class="wa-template__error"
            role="alert"
            data-testid="whatsapp-inbox-template-file-error"
          >
            {{ fileError }}
          </p>
          <input
            ref="picker"
            type="file"
            hidden
            :accept="SAMPLE_RULES[fileKind].accept"
            data-testid="whatsapp-inbox-template-file-input"
            @change="onPick"
          >
        </div>
        <ion-input
          v-for="(value, index) in values"
          :key="`${chosen.id}-${index}`"
          :data-testid="`whatsapp-inbox-template-variable-${index + 1}`"
          :value="value"
          :label="t('whatsapp_inbox.templates.variable', { n: index + 1 })"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="1024"
          @ion-input="setValue(index, $event.detail.value)"
        />
        <section
          class="wa-template__preview"
          data-testid="whatsapp-inbox-template-preview"
        >
          <span class="wa-template__meta">{{ $t('whatsapp_inbox.templates.preview') }}</span>
          <p>{{ preview }}</p>
        </section>
      </template>
    </div>
  </FormModal>
</template>

<style scoped>
.wa-template {
  display: grid;
  gap: 12px;
}
.wa-template__none {
  margin: 0;
  color: var(--ion-color-medium-shade);
}
.wa-template__meta {
  font-size: 0.8rem;
  color: var(--ion-color-medium-shade);
}
.wa-template__file {
  display: grid;
  gap: 6px;
}
.wa-template__file-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.wa-template__error {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-danger);
}
.wa-template__preview {
  border-radius: 12px;
  padding: 0.5rem 0.75rem;
  background: var(--ion-color-primary-tint, #d0ebff);
}
.wa-template__preview p {
  margin: 0.2rem 0 0;
  white-space: pre-wrap;
}
</style>
