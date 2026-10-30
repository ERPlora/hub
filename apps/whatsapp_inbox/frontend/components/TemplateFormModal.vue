<script setup lang="ts">
// WHATSAPP_INBOX-F29 «Create a template and send it for review» and F30 «Edit a template», from Settings →
// «Meta templates» (the old module's panel): Name (lowercase, numbers and underscores; it never changes),
// Language, Category (Utility or Marketing), Header — a text, or a photo, a video or a document whose file is
// kept in the business's files at once (`whatsapp_inbox.template_sample.upload`, checked here first by type and
// size), shown with its thumbnail (`HeaderFilePreview`), and goes with the template to Meta's review —, Text with an «Example» box per variable it uses, Footer
// and up to 10 buttons — quick replies together, at most 2 links (https://) and 1 call (+34…). New sends
// `whatsapp_inbox.template.create`; Edit sends the whole content with `whatsapp_inbox.template.update` (what
// Meta has, or the changes still on their way), with its verdict and reason on top; the category only changes
// while Meta has not approved it. One key per save, kept until the Hub takes it: pressing again never
// registers it twice. The dialog closes when the Hub kept it (Meta's answer comes back live in the table);
// a refusal stays in it with what was typed.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonSpinner, IonTextarea } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { acceptsSample, fileToBase64, formatSize, SAMPLE_RULES } from '../lib/files';
import type {
  FileHeaderFormat,
  TemplateButtonIn,
  TemplateButtonType,
  TemplateOut,
  TemplateSampleOut,
  WritableCategory,
} from '../operations';
import HeaderFilePreview from './HeaderFilePreview.vue';

const props = defineProps<{
  /** The template being edited; `null` = «New template». */
  template: TemplateOut | null;
}>();
const open = defineModel<boolean>('open', { default: false });

const ID = 'whatsapp-inbox-template-editor';
const MAX_BUTTONS = 10;
/** Meta's languages a Spanish business writes in most; an edit keeps its own whatever it is. */
const LANGUAGES = ['es', 'es_ES', 'es_MX', 'es_AR', 'ca', 'eu', 'gl', 'en', 'en_US', 'en_GB', 'fr', 'de', 'it', 'pt_PT', 'pt_BR', 'nl', 'ro', 'ar'];
const CATEGORIES: WritableCategory[] = ['UTILITY', 'MARKETING'];
const BUTTON_TYPES: TemplateButtonType[] = ['QUICK_REPLY', 'URL', 'PHONE_NUMBER'];
/** A text header (empty: none), or one with a file. */
const HEADER_FORMATS = ['TEXT', 'IMAGE', 'VIDEO', 'DOCUMENT'] as const;
type HeaderKind = (typeof HEADER_FORMATS)[number];
const MB = 1024 * 1024;
const VARIABLE = /\{\{\s*(\d+)\s*\}\}/g;
const NAME = /^[a-z0-9_]+$/;
const PHONE = /^\+[1-9]\d{6,14}$/;

interface ButtonForm {
  type: TemplateButtonType;
  text: string;
  url: string;
  phone_number: string;
}
interface Form {
  name: string;
  language: string;
  category: WritableCategory;
  headerFormat: HeaderKind;
  header: string;
  /** The file of a photo, video or document header, kept in the business's files. */
  sample: TemplateSampleOut | null;
  body: string;
  examples: string[];
  footer: string;
  buttons: ButtonForm[];
}

const t = useT();
const locale = useLocale();
const creation = useCommand('whatsapp_inbox.template.create');
const update = useCommand('whatsapp_inbox.template.update');
const sampleUpload = useCommand('whatsapp_inbox.template_sample.upload');
const uploading = computed(() => sampleUpload.pending.value);
const pending = computed(() => creation.pending.value || update.pending.value);
const refusal = computed(() => (props.template ? update.error.value : creation.error.value));
/** The server's field names of what was changed since the last refusal: their errors are stale. */
const edited = ref<ReadonlySet<string>>(new Set());
watch(refusal, () => {
  edited.value = new Set();
});
/** The refusal as the dialog shows it: a field changed since stops showing its error. */
const error = computed(() => {
  const refused = refusal.value;
  if (!refused?.fields) return refused;
  const fields = Object.fromEntries(Object.entries(refused.fields).filter(([name]) => !edited.value.has(name)));
  return { message: refused.message, code: refused.code, status: refused.status, fields };
});
const title = computed(() =>
  props.template ? t('whatsapp_inbox.templates.editor.titleEdit', { name: props.template.name }) : t('whatsapp_inbox.templates.editor.titleNew'),
);

const form = ref<Form>(empty());
/** One key per save, kept until the Hub takes it (a silence may have reached it). */
const key = ref(crypto.randomUUID());
/** What is wrong with the header's file just chosen, said under it (the Hub's refusal, or the check here). */
const fileError = ref('');

function empty(): Form {
  return {
    name: '',
    language: 'es',
    category: 'UTILITY',
    headerFormat: 'TEXT',
    header: '',
    sample: null,
    body: '',
    examples: [],
    footer: '',
    buttons: [],
  };
}

const isFileKind = (kind: string): kind is FileHeaderFormat => kind === 'IMAGE' || kind === 'VIDEO' || kind === 'DOCUMENT';

function fromTemplate(template: TemplateOut | null): Form {
  if (!template) return empty();
  // The changes still on their way, if any; else what Meta has.
  const content = template.draft ?? template;
  const withFile = isFileKind(content.header_format);
  return {
    name: template.name,
    language: template.language,
    category: content.category === 'MARKETING' ? 'MARKETING' : 'UTILITY',
    headerFormat: withFile ? (content.header_format as FileHeaderFormat) : 'TEXT',
    header: withFile ? '' : content.header,
    sample: withFile ? content.header_sample : null,
    body: content.body,
    examples: [...content.body_examples],
    footer: content.footer,
    buttons: content.buttons.map((button) => ({
      type: (BUTTON_TYPES as string[]).includes(button.type) ? (button.type as TemplateButtonType) : 'QUICK_REPLY',
      text: button.text,
      url: button.url,
      phone_number: button.phone_number,
    })),
  };
}

watch(
  () => [open.value, props.template?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromTemplate(props.template);
    key.value = crypto.randomUUID();
    creation.error.value = null;
    update.error.value = null;
    fileError.value = '';
  },
  { immediate: true },
);

/** How many variables the text uses (its highest {{n}}): one example each. */
const variables = computed(() => Math.max(0, ...[...form.value.body.matchAll(VARIABLE)].map((match) => Number(match[1]))));
watch(variables, (count) => {
  const examples = form.value.examples.slice(0, count);
  while (examples.length < count) examples.push('');
  form.value = { ...form.value, examples };
});

const nameInvalid = computed(() => !props.template && form.value.name.trim() !== '' && !NAME.test(form.value.name.trim()));
/** Meta judged it and did not reject it: its category stays. */
const categoryFixed = computed(() => !!props.template && !['DRAFT', 'REJECTED'].includes(props.template.status));

function buttonComplete(button: ButtonForm): boolean {
  if (!button.text.trim()) return false;
  if (button.type === 'URL') return button.url.trim().startsWith('https://') && !button.url.includes('{{');
  if (button.type === 'PHONE_NUMBER') return PHONE.test(button.phone_number.trim());
  return true;
}

/** The header's kind when it carries a file. */
const fileKind = computed<FileHeaderFormat | null>(() => (isFileKind(form.value.headerFormat) ? form.value.headerFormat : null));
const headerFileReady = computed(() => fileKind.value === null || (form.value.sample !== null && !uploading.value));

const complete = computed(() => {
  const f = form.value;
  const identity = props.template ? true : NAME.test(f.name.trim()) && f.language !== '';
  return (
    identity &&
    headerFileReady.value &&
    f.body.trim() !== '' &&
    f.examples.every((example) => example.trim() !== '') &&
    f.buttons.every(buttonComplete)
  );
});

const languageNames = computed(() => {
  try {
    return new Intl.DisplayNames([locale.value], { type: 'language' });
  } catch {
    return null;
  }
});
function languageLabel(code: string): string {
  const name = languageNames.value?.of(code.replace('_', '-'));
  return name && name !== code ? `${name} · ${code}` : code;
}

/** What Meta says of the template being edited, and what is on its way. */
const state = computed(() => {
  const template = props.template;
  if (!template) return [];
  const lines = [t(`whatsapp_inbox.templates.statuses.${template.status}`)];
  if (template.rejected_reason) lines.push(t('whatsapp_inbox.templates.rejectedReason', { reason: template.rejected_reason }));
  if (template.submit_error) lines.push(template.submit_error);
  else if (template.submit_state === 'queued' || template.submit_state === 'sending') lines.push(t('whatsapp_inbox.templates.state.sending'));
  if (template.status === 'APPROVED') lines.push(t('whatsapp_inbox.templates.editor.approvedKept'));
  return lines;
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));

/** The server's name of each field of the form. */
const SERVER_FIELD: Record<keyof Form, string> = {
  name: 'name',
  language: 'language',
  category: 'category',
  headerFormat: 'header_format',
  header: 'header',
  sample: 'header_sample',
  body: 'body',
  examples: 'body_examples',
  footer: 'footer',
  buttons: 'buttons',
};
function set<K extends keyof Form>(field: K, value: Form[K]): void {
  form.value = { ...form.value, [field]: value };
  if (refusal.value?.fields?.[SERVER_FIELD[field]] !== undefined) edited.value = new Set([...edited.value, SERVER_FIELD[field]]);
}
function setExample(index: number, value: unknown): void {
  const examples = [...form.value.examples];
  examples[index] = text(value);
  set('examples', examples);
}
function setButton(index: number, patch: Partial<ButtonForm>): void {
  set(
    'buttons',
    form.value.buttons.map((button, at) => (at === index ? { ...button, ...patch } : button)),
  );
}
// ── The header's file ──────────────────────────────────────────────────────────────────────────────

const picker = shallowRef<HTMLInputElement | null>(null);

function setHeaderFormat(value: string): void {
  const kind: HeaderKind = (HEADER_FORMATS as readonly string[]).includes(value) ? (value as HeaderKind) : 'TEXT';
  if (kind === form.value.headerFormat) return;
  fileError.value = '';
  set('headerFormat', kind);
  // A file of another kind does not go with this header.
  if (form.value.sample && form.value.sample.header_format !== kind) set('sample', null);
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
    const sample = await sampleUpload.run({ header_format: kind, name: file.name, content_base64: await fileToBase64(file) });
    set('sample', sample);
  } catch {
    const refused = sampleUpload.error.value;
    fileError.value = refused?.fields?.content_base64 ?? refused?.message ?? t('whatsapp_inbox.templates.editor.fileUploadFailed');
  }
}

function addButton(): void {
  if (form.value.buttons.length >= MAX_BUTTONS) return;
  set('buttons', [...form.value.buttons, { type: 'QUICK_REPLY', text: '', url: '', phone_number: '' }]);
}
function removeButton(index: number): void {
  set(
    'buttons',
    form.value.buttons.filter((_, at) => at !== index),
  );
}

function written() {
  const f = form.value;
  const buttons: TemplateButtonIn[] = f.buttons.map((button) => {
    const out: TemplateButtonIn = { type: button.type, text: button.text.trim() };
    if (button.type === 'URL') out.url = button.url.trim();
    if (button.type === 'PHONE_NUMBER') out.phone_number = button.phone_number.trim();
    return out;
  });
  const kind = fileKind.value;
  // A text header goes as it always went; one with a file names it, without text.
  const header = kind ? { header_format: kind, header: '', header_sample: f.sample?.id ?? null } : { header: f.header.trim() };
  return {
    category: f.category,
    ...header,
    body: f.body.trim(),
    body_examples: f.examples.map((example) => example.trim()),
    footer: f.footer.trim(),
    buttons,
    submit_key: key.value,
  };
}

async function save(): Promise<void> {
  if (!complete.value) return;
  try {
    if (props.template) await update.run({ id: props.template.id, ...written() });
    else await creation.run({ name: form.value.name.trim(), language: form.value.language, ...written() });
  } catch {
    return; // The dialog paints the refusal; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :testid="ID"
    size="md"
    :title="title"
    :submit-label="template ? $t('whatsapp_inbox.templates.editor.save') : $t('whatsapp_inbox.templates.editor.send')"
    :cancel-label="$t('whatsapp_inbox.cancel')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="wa-template-form">
        <InlineFeedback
          v-if="template"
          :data-testid="`${ID}-state`"
          :tone="template.submit_state === 'failed' || template.status === 'REJECTED' ? 'danger' : 'neutral'"
          :heading="state[0]"
        >
          <p
            v-for="line in state.slice(1)"
            :key="line"
            class="wa-template-form__line"
          >
            {{ line }}
          </p>
        </InlineFeedback>

        <p
          v-if="template"
          class="wa-template-form__identity"
          :data-testid="`${ID}-identity`"
        >
          <strong>{{ template.name }}</strong> · {{ languageLabel(template.language) }}
        </p>
        <template v-else>
          <div>
            <ion-input
              :data-testid="`${ID}-name`"
              :value="form.name"
              :label="$t('whatsapp_inbox.templates.editor.name')"
              :helper-text="$t('whatsapp_inbox.templates.editor.nameHint')"
              label-placement="floating"
              fill="outline"
              mode="md"
              autocapitalize="off"
              :maxlength="512"
              :error-text="fieldErrors.name"
              :class="{ 'ion-invalid': !!fieldErrors.name || nameInvalid, 'ion-touched': !!fieldErrors.name || nameInvalid }"
              @ion-input="set('name', text($event.detail.value))"
            />
            <p
              v-if="nameInvalid"
              class="wa-template-form__rule"
              :data-testid="`${ID}-name-rule`"
            >
              {{ $t('whatsapp_inbox.templates.editor.nameRule') }}
            </p>
          </div>
          <ion-select
            :data-testid="`${ID}-language`"
            :value="form.language"
            :label="$t('whatsapp_inbox.templates.editor.language')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="set('language', text($event.detail.value))"
          >
            <ion-select-option
              v-for="code in LANGUAGES"
              :key="code"
              :value="code"
            >
              {{ languageLabel(code) }}
            </ion-select-option>
          </ion-select>
        </template>

        <ion-select
          :data-testid="`${ID}-category`"
          :value="form.category"
          :label="$t('whatsapp_inbox.templates.editor.category')"
          :disabled="categoryFixed"
          :helper-text="categoryFixed ? $t('whatsapp_inbox.templates.editor.categoryFixed') : undefined"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="set('category', $event.detail.value === 'MARKETING' ? 'MARKETING' : 'UTILITY')"
        >
          <ion-select-option
            v-for="category in CATEGORIES"
            :key="category"
            :value="category"
          >
            {{ t(`whatsapp_inbox.templates.categories.${category}`) }}
          </ion-select-option>
        </ion-select>

        <ion-select
          :data-testid="`${ID}-header-format`"
          :value="form.headerFormat"
          :label="$t('whatsapp_inbox.templates.editor.headerFormat')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="setHeaderFormat(text($event.detail.value))"
        >
          <ion-select-option
            v-for="kind in HEADER_FORMATS"
            :key="kind"
            :value="kind"
          >
            {{ t(`whatsapp_inbox.templates.editor.headerFormats.${kind}`) }}
          </ion-select-option>
        </ion-select>
        <div
          v-if="fileKind"
          class="wa-template-form__file"
          :data-testid="`${ID}-header-file`"
        >
          <div class="wa-template-form__file-row">
            <HeaderFilePreview
              v-if="form.sample"
              :sample="form.sample"
              :testid="`${ID}-header-file-preview`"
            >
              <p :data-testid="`${ID}-header-file-name`">
                <strong>{{ form.sample.name }}</strong> · {{ formatSize(form.sample.size, locale) }}
              </p>
            </HeaderFilePreview>
            <p
              v-else
              class="wa-template-form__hint"
              :data-testid="`${ID}-header-file-empty`"
            >
              {{ $t('whatsapp_inbox.templates.editor.noFile') }}
            </p>
            <ion-button
              fill="outline"
              size="small"
              :disabled="uploading"
              :data-testid="`${ID}-header-file-choose`"
              @click="picker?.click()"
            >
              <ion-spinner
                v-if="uploading"
                slot="start"
                name="crescent"
              />
              <HubIcon
                v-else
                slot="start"
                name="ion:cloud-upload-outline"
              />
              {{ uploading ? $t('whatsapp_inbox.templates.editor.uploading') : form.sample ? $t('whatsapp_inbox.templates.editor.changeFile') : $t('whatsapp_inbox.templates.editor.chooseFile') }}
            </ion-button>
          </div>
          <p
            class="wa-template-form__hint"
            :data-testid="`${ID}-header-file-rules`"
          >
            {{ t(`whatsapp_inbox.templates.editor.fileRules.${fileKind}`) }}
            {{ $t('whatsapp_inbox.templates.editor.fileReview') }}
          </p>
          <p
            v-if="fileError || fieldErrors.header_sample"
            class="wa-template-form__rule"
            role="alert"
            :data-testid="`${ID}-header-file-error`"
          >
            {{ fileError || fieldErrors.header_sample }}
          </p>
          <input
            ref="picker"
            type="file"
            hidden
            :accept="SAMPLE_RULES[fileKind].accept"
            :data-testid="`${ID}-header-file-input`"
            @change="onPick"
          >
        </div>
        <ion-input
          v-else
          :data-testid="`${ID}-header`"
          :value="form.header"
          :label="$t('whatsapp_inbox.templates.editor.header')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="60"
          :counter="true"
          :error-text="fieldErrors.header"
          :class="{ 'ion-invalid': !!fieldErrors.header, 'ion-touched': !!fieldErrors.header }"
          @ion-input="set('header', text($event.detail.value))"
        />
        <ion-textarea
          :data-testid="`${ID}-body`"
          :value="form.body"
          :label="$t('whatsapp_inbox.templates.editor.body')"
          :helper-text="$t('whatsapp_inbox.templates.editor.bodyHint')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :rows="4"
          :maxlength="1024"
          :counter="true"
          :error-text="fieldErrors.body"
          :class="{ 'ion-invalid': !!fieldErrors.body, 'ion-touched': !!fieldErrors.body }"
          @ion-input="set('body', text($event.detail.value))"
        />
        <div
          v-if="form.examples.length"
          class="wa-template-form__group"
        >
          <p class="wa-template-form__hint">
            {{ $t('whatsapp_inbox.templates.editor.examplesHint') }}
          </p>
          <ion-input
            v-for="(example, index) in form.examples"
            :key="index"
            :data-testid="`${ID}-example-${index + 1}`"
            :value="example"
            :label="t('whatsapp_inbox.templates.editor.example', { n: index + 1 })"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="1024"
            :error-text="index === 0 ? fieldErrors.body_examples : undefined"
            :class="{ 'ion-invalid': index === 0 && !!fieldErrors.body_examples, 'ion-touched': index === 0 && !!fieldErrors.body_examples }"
            @ion-input="setExample(index, $event.detail.value)"
          />
        </div>
        <ion-input
          :data-testid="`${ID}-footer`"
          :value="form.footer"
          :label="$t('whatsapp_inbox.templates.editor.footer')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="60"
          :counter="true"
          :error-text="fieldErrors.footer"
          :class="{ 'ion-invalid': !!fieldErrors.footer, 'ion-touched': !!fieldErrors.footer }"
          @ion-input="set('footer', text($event.detail.value))"
        />

        <section class="wa-template-form__group">
          <h3 class="wa-template-form__title">
            {{ $t('whatsapp_inbox.templates.editor.buttons') }}
          </h3>
          <p
            v-if="fieldErrors.buttons"
            class="wa-template-form__rule"
          >
            {{ fieldErrors.buttons }}
          </p>
          <div
            v-for="(button, index) in form.buttons"
            :key="index"
            class="wa-template-form__button"
          >
            <ion-select
              :data-testid="`${ID}-button-${index}-type`"
              :value="button.type"
              :label="$t('whatsapp_inbox.templates.editor.buttonType')"
              label-placement="floating"
              fill="outline"
              mode="md"
              interface="popover"
              @ion-change="setButton(index, { type: (BUTTON_TYPES as string[]).includes(text($event.detail.value)) ? (text($event.detail.value) as TemplateButtonType) : 'QUICK_REPLY' })"
            >
              <ion-select-option
                v-for="kind in BUTTON_TYPES"
                :key="kind"
                :value="kind"
              >
                {{ t(`whatsapp_inbox.templates.editor.buttonTypes.${kind}`) }}
              </ion-select-option>
            </ion-select>
            <ion-input
              :data-testid="`${ID}-button-${index}-text`"
              :value="button.text"
              :label="$t('whatsapp_inbox.templates.editor.buttonText')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :maxlength="25"
              @ion-input="setButton(index, { text: text($event.detail.value) })"
            />
            <ion-input
              v-if="button.type === 'URL'"
              :data-testid="`${ID}-button-${index}-url`"
              :value="button.url"
              type="url"
              inputmode="url"
              :label="$t('whatsapp_inbox.templates.editor.buttonUrl')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :maxlength="2000"
              @ion-input="setButton(index, { url: text($event.detail.value) })"
            />
            <ion-input
              v-if="button.type === 'PHONE_NUMBER'"
              :data-testid="`${ID}-button-${index}-phone_number`"
              :value="button.phone_number"
              type="tel"
              inputmode="tel"
              :label="$t('whatsapp_inbox.templates.editor.buttonPhone')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :maxlength="16"
              @ion-input="setButton(index, { phone_number: text($event.detail.value) })"
            />
            <ion-button
              fill="clear"
              color="medium"
              :data-testid="`${ID}-button-${index}-remove`"
              :aria-label="$t('whatsapp_inbox.templates.editor.buttonRemove')"
              @click="removeButton(index)"
            >
              <HubIcon
                slot="icon-only"
                name="ion:close-outline"
              />
            </ion-button>
          </div>
          <ion-button
            fill="outline"
            size="small"
            :data-testid="`${ID}-button-add`"
            :disabled="form.buttons.length >= MAX_BUTTONS"
            @click="addButton"
          >
            <HubIcon
              slot="start"
              name="ion:add-outline"
            />
            {{ $t('whatsapp_inbox.templates.editor.buttonAdd') }}
          </ion-button>
        </section>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.wa-template-form {
  display: grid;
  gap: 14px;
}
.wa-template-form__group {
  display: grid;
  gap: 10px;
}
.wa-template-form__title {
  margin: 0;
  font-size: 0.95rem;
}
.wa-template-form__hint,
.wa-template-form__identity,
.wa-template-form__line {
  margin: 0;
  color: var(--ion-color-medium-shade);
}
.wa-template-form__identity strong {
  color: var(--ion-text-color);
}
.wa-template-form__file {
  display: grid;
  gap: 6px;
}
.wa-template-form__file-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.wa-template-form__rule {
  margin: 4px 0 0;
  color: var(--ion-color-danger);
  font-size: 0.85rem;
}
.wa-template-form__button {
  display: grid;
  grid-template-columns: minmax(0, 9rem) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: start;
}
.wa-template-form__button > ion-input:nth-of-type(2) {
  grid-column: 1 / 3;
}
@media (max-width: 480px) {
  .wa-template-form__button {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .wa-template-form__button > ion-select {
    grid-column: 1 / 2;
  }
  .wa-template-form__button > ion-input {
    grid-column: 1 / 2;
  }
}
</style>
