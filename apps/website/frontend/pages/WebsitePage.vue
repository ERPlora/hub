<script setup lang="ts">
// Website → the editor (WORKBOOK «El editor»): the site live (`website.site.get`), its status (never published,
// offline, online and whether the draft has unpublished changes), and, for whoever manages it, the form: the four
// designs, the palette (or the owner's two colours) and the page mode, and one block per fixed section (the optional ones with «Show»). The draft
// is saved by hand or two seconds after the last change (`website.site.save`), and the real preview beside it
// reloads after each save (`website.site.preview`, in a frame). «Publish» and «Take offline» ask first; «Share and
// QR» gives the address and its QR. On a computer the form and the preview stand side by side; on a tablet or a
// phone a segment switches between them. Squarespace's, Wix's and Shopify's editors, reduced to fixed sections.
import { ColorInput, ImageUpload, InlineFeedback, useConfirm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import {
  IonAccordion,
  IonAccordionGroup,
  IonButton,
  IonInput,
  IonItem,
  IonLabel,
  IonList,
  IonNote,
  IonSegment,
  IonSegmentButton,
  IonSelect,
  IonSelectOption,
  IonSpinner,
  IonTextarea,
  IonToggle,
  onIonViewWillLeave,
} from '@ionic/vue';
import { computed, onBeforeUnmount, ref, watch } from 'vue';

import CategoryPicker from '../components/CategoryPicker.vue';
import HoursEditor from '../components/HoursEditor.vue';
import PalettePicker from '../components/PalettePicker.vue';
import PreviewFrame from '../components/PreviewFrame.vue';
import ShareDialog from '../components/ShareDialog.vue';
import TemplatePicker from '../components/TemplatePicker.vue';
import { useT } from '../composables/useT';
import { copyOf, errorUnder, sameDraft, toDraft, toSaveIn } from '../lib/draft';
import { defaultHours } from '../lib/hours';
import { startingCustom, themeColours } from '../lib/palettes';
import { makeUploader } from '../lib/upload';
import type { CatalogSource, Content, PaletteId, SaveIn, ThemeMode } from '../operations';

/** Saved this long after the last change. */
const AUTOSAVE_MS = 2000;
/** The sections a visitor may not see, each with its «Show». */
const OPTIONAL = ['about', 'catalog', 'contact', 'location'] as const;
type Optional = (typeof OPTIONAL)[number];
const SOCIALS = ['instagram', 'facebook', 'tiktok', 'x'] as const;
const CONTACT_FIELDS = ['phone', 'whatsapp', 'email'] as const;
/** What a link field starts with. (A literal `https://` in a template attribute trips vue-tsc's parser.) */
const HTTPS = 'https://';
const SOURCES: readonly CatalogSource[] = ['inventory', 'service'];
const MODES: readonly ThemeMode[] = ['light', 'dark', 'auto'];

const t = useT();
const session = useSession();
const { confirm } = useConfirm();
const canView = computed(() => session.can('website.view'));
const canManage = computed(() => session.can('website.manage'));

const { data: site, status, error: loadError } = useLive('website.site.get', {});
const save = useCommand('website.site.save');
const publish = useCommand('website.site.publish');
const unpublish = useCommand('website.site.unpublish');
const uploadImage = useCommand('website.image.upload');
const upload = makeUploader((input) => uploadImage.run(input));

/** The form: a copy of the site's draft, edited here; `saved` is what the server holds of it. */
const draft = ref<SaveIn | null>(null);
const saved = ref<SaveIn | null>(null);
const previewKey = ref(1);
/** The sections unfolded in the form. Kept here: Vue sets the group's `value` again on every render, and a constant
 * there folded the section being typed in at each keystroke (the field lost the focus, the page jumped). */
const openSections = ref<string[]>(['topbar', 'hero']);
const view = ref<'edit' | 'preview'>('edit');
const sharing = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

const dirty = computed(() => !!draft.value && !!saved.value && !sameDraft(draft.value, saved.value));
const saving = computed(() => save.pending.value);
const fields = computed(() => save.error.value?.fields);
const state = computed(() => {
  if (!site.value) return null;
  if (!site.value.published_version) return 'never';
  return site.value.is_live ? 'live' : 'offline';
});
/** The chosen palette's colours, to draw the designs with. */
const colours = computed(() => themeColours((draft.value as SaveIn).theme));
/** The catalog's sources this business has on (Inventory, Services). */
const sources = computed(() => {
  const on = new Set((session.me.value?.apps ?? []).filter((app) => app.state === 'on').map((app) => app.label));
  return SOURCES.filter((source) => on.has(source));
});

watch(
  site,
  (now) => {
    if (!now) return;
    // A result never overwrites what is being edited: with nothing pending it follows another editor's save, and our
    // own save coming back (trimmed by the server) leaves the fields as they are being typed.
    const fresh = toDraft(now);
    if (!draft.value || (!dirty.value && !sameDraft(draft.value, fresh))) draft.value = fresh;
    saved.value = toDraft(now);
  },
  { immediate: true },
);

watch(
  draft,
  () => {
    clearTimeout(timer);
    if (canManage.value && dirty.value) timer = setTimeout(() => void saveNow(), AUTOSAVE_MS);
  },
  { deep: true },
);

/** Saves the draft if it changed; `false` when the server refused it (its error is on the page). */
async function saveNow(): Promise<boolean> {
  clearTimeout(timer);
  if (!draft.value || !dirty.value) return true;
  const sending = toSaveIn(draft.value);
  try {
    await save.run(sending);
  } catch {
    return false;
  }
  saved.value = copyOf(sending);
  previewKey.value += 1;
  return true;
}

function flushPending(): void {
  if (dirty.value && canManage.value) void saveNow();
}
onIonViewWillLeave(flushPending);
onBeforeUnmount(() => {
  flushPending();
  clearTimeout(timer);
});

async function publishSite(): Promise<void> {
  const url = site.value?.public_url ?? '';
  const asked = await confirm({
    title: t('website.publish.title'),
    message: t('website.publish.message', { url }),
    tone: 'primary',
    confirmLabel: t('website.actions.publish'),
    confirmIcon: 'ion:cloud-upload-outline',
  });
  if (!asked) return;
  if (!(await saveNow())) {
    void toastError(t('website.saveError'));
    return;
  }
  try {
    await publish.run({});
    void toastSuccess(t('website.publish.done'));
  } catch {
    void toastError(t('website.publish.error'));
  }
}

async function unpublishSite(): Promise<void> {
  const url = site.value?.public_url ?? '';
  const asked = await confirm({
    title: t('website.unpublish.title'),
    message: t('website.unpublish.message', { url }),
    tone: 'warning',
    confirmLabel: t('website.actions.unpublish'),
  });
  if (!asked) return;
  try {
    await unpublish.run({});
    void toastSuccess(t('website.unpublish.done'));
  } catch {
    void toastError(t('website.unpublish.error'));
  }
}

/** The group's own change only: a field's or a switch's `ionChange` inside it bubbles up to it too. */
function followOpenSections(event: CustomEvent<{ value: unknown }>): void {
  if (event.target !== event.currentTarget) return;
  const value = event.detail.value;
  openSections.value = Array.isArray(value) ? value.map(String) : typeof value === 'string' ? [value] : [];
}

// Field helpers

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const err = (path: string): string | undefined => errorUnder(fields.value, path);
const invalid = (path: string) => ({ 'ion-invalid': !!err(path), 'ion-touched': !!err(path) });

function section<K extends keyof Content>(name: K): Content[K] {
  return (draft.value as SaveIn).content[name];
}

function setShown(name: Optional, shown: boolean): void {
  section(name).hidden = !shown;
}

function setSource(value: unknown): void {
  const catalog = section('catalog');
  const source = SOURCES.find((known) => known === value) ?? null;
  if (catalog.source !== source) catalog.category_ids = [];
  catalog.source = source;
}

/** Another palette; «Your colours» opens on the colours chosen before, or on those of the palette on show. */
function choosePalette(palette: PaletteId): void {
  const theme = (draft.value as SaveIn).theme;
  if (palette === 'custom') theme.custom = startingCustom(theme);
  theme.palette = palette;
}

function setMode(value: unknown): void {
  const mode = MODES.find((known) => known === value);
  if (mode) (draft.value as SaveIn).theme.mode = mode;
}

function setHoursShown(shown: boolean): void {
  section('contact').hours = shown ? defaultHours() : [];
}
</script>

<template>
  <AppPage
    :title="t('website.title')"
    content-layout="fluid"
  >
    <InlineFeedback
      v-if="!canView"
      tone="warning"
      data-testid="website-forbidden"
      :heading="t('website.noPermission')"
    />
    <InlineFeedback
      v-else-if="status === 'error' && loadError"
      tone="danger"
      data-testid="website-load-error"
      :heading="loadError.code === 'app_inactive' ? t('website.appInactive') : t('website.loadError')"
    >
      {{ loadError.message }}
    </InlineFeedback>
    <div
      v-else-if="site && draft"
      class="we"
    >
      <div class="we-bar">
        <InlineFeedback
          v-if="state === 'never'"
          tone="info"
          data-testid="website-status-never"
        >
          {{ t('website.status.never') }}
        </InlineFeedback>
        <InlineFeedback
          v-else-if="state === 'offline'"
          tone="warning"
          data-testid="website-status-offline"
        >
          {{ t('website.status.offline') }}
        </InlineFeedback>
        <InlineFeedback
          v-else
          tone="success"
          data-testid="website-status-live"
        >
          {{ t('website.status.live', { url: site.public_url }) }}
        </InlineFeedback>
        <InlineFeedback
          v-if="state !== 'never' && site.has_changes"
          tone="info"
          data-testid="website-status-changes"
        >
          {{ t('website.status.changes') }}
        </InlineFeedback>
        <div class="we-actions">
          <span
            v-if="canManage"
            class="we-save-state"
            aria-live="polite"
            data-testid="website-save-state"
          >{{ saving ? t('website.actions.saving') : dirty ? t('website.actions.unsaved') : t('website.actions.saved') }}</span>
          <ion-button
            v-if="canManage"
            fill="outline"
            data-testid="website-save"
            :disabled="!dirty || saving"
            @click="saveNow"
          >
            {{ t('website.actions.save') }}
          </ion-button>
          <ion-button
            v-if="canManage"
            data-testid="website-publish"
            :disabled="publish.pending.value"
            @click="publishSite"
          >
            <HubIcon
              slot="start"
              name="ion:cloud-upload-outline"
            />
            {{ t('website.actions.publish') }}
          </ion-button>
          <ion-button
            v-if="canManage && site.is_live"
            fill="clear"
            color="medium"
            data-testid="website-unpublish"
            :disabled="unpublish.pending.value"
            @click="unpublishSite"
          >
            {{ t('website.actions.unpublish') }}
          </ion-button>
          <ion-button
            fill="clear"
            data-testid="website-share"
            @click="sharing = true"
          >
            <HubIcon
              slot="start"
              name="ion:qr-code-outline"
            />
            {{ t('website.actions.share') }}
          </ion-button>
        </div>
      </div>

      <InlineFeedback
        v-if="!canManage"
        tone="info"
        data-testid="website-read-only"
      >
        {{ t('website.noPermission') }}
      </InlineFeedback>
      <template v-else>
        <InlineFeedback
          v-if="save.error.value"
          tone="danger"
          data-testid="website-save-error"
          :heading="t('website.saveError')"
        >
          {{ save.error.value.message }}
        </InlineFeedback>
        <ion-segment
          class="we-switch"
          data-testid="website-view"
          :value="view"
          :aria-label="t('website.view.label')"
          @ion-change="view = $event.detail.value === 'preview' ? 'preview' : 'edit'"
        >
          <ion-segment-button value="edit">
            <ion-label>{{ t('website.view.edit') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="preview">
            <ion-label>{{ t('website.view.preview') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
        <div
          class="we-grid"
          :class="`we-grid--${view}`"
        >
          <section
            class="we-form"
            data-testid="website-editor"
          >
            <h2 class="we-heading">
              {{ t('website.template.heading') }}
            </h2>
            <TemplatePicker
              v-model="draft.template"
              :primary="colours.primary"
              :accent="colours.accent"
            />

            <h2 class="we-heading">
              {{ t('website.colours.heading') }}
            </h2>
            <PalettePicker
              :model-value="draft.theme.palette"
              :custom="draft.theme.custom"
              @update:model-value="choosePalette"
            />
            <ion-list inset>
              <template v-if="draft.theme.palette === 'custom' && draft.theme.custom">
                <ColorInput
                  v-model="draft.theme.custom.primary"
                  :label="t('website.colours.primary')"
                  testid="website-colour-primary"
                />
                <ColorInput
                  v-model="draft.theme.custom.accent"
                  :label="t('website.colours.accent')"
                  testid="website-colour-accent"
                />
                <ion-item lines="none">
                  <ion-note class="we-note">
                    {{ t('website.palette.customHint') }}
                  </ion-note>
                </ion-item>
              </template>
              <ion-item lines="none">
                <ion-label>{{ t('website.colours.mode') }}</ion-label>
              </ion-item>
              <ion-item>
                <ion-segment
                  class="we-mode"
                  data-testid="website-mode"
                  :aria-label="t('website.colours.mode')"
                  :value="draft.theme.mode"
                  @ion-change="setMode($event.detail.value)"
                >
                  <ion-segment-button value="light">
                    <ion-label>{{ t('website.colours.light') }}</ion-label>
                  </ion-segment-button>
                  <ion-segment-button value="dark">
                    <ion-label>{{ t('website.colours.dark') }}</ion-label>
                  </ion-segment-button>
                  <ion-segment-button value="auto">
                    <ion-label>{{ t('website.colours.auto') }}</ion-label>
                  </ion-segment-button>
                </ion-segment>
              </ion-item>
              <ion-item
                v-if="draft.theme.mode === 'auto'"
                lines="none"
              >
                <ion-note
                  class="we-note"
                  data-testid="website-mode-auto-hint"
                >
                  {{ t('website.colours.autoHint') }}
                </ion-note>
              </ion-item>
            </ion-list>

            <h2 class="we-heading">
              {{ t('website.sections.heading') }}
            </h2>
            <ion-accordion-group
              multiple
              data-testid="website-sections"
              :value="openSections"
              @ion-change="followOpenSections"
            >
              <!-- Top bar: always there, with «Log in». -->
              <ion-accordion
                value="topbar"
                data-testid="website-section-topbar"
              >
                <ion-item slot="header">
                  <ion-label>
                    {{ t('website.sections.topbar') }}
                    <p>{{ t('website.sections.always') }}</p>
                  </ion-label>
                </ion-item>
                <ion-list
                  slot="content"
                  inset
                >
                  <ion-item>
                    <ion-input
                      data-testid="website-field-topbar-name"
                      :label="t('website.fields.name')"
                      label-placement="stacked"
                      :maxlength="80"
                      :value="draft.content.topbar.name"
                      :error-text="err('content.topbar.name')"
                      :class="invalid('content.topbar.name')"
                      @ion-input="draft.content.topbar.name = text($event.detail.value)"
                    />
                  </ion-item>
                  <ImageUpload
                    v-model="draft.content.topbar.logo"
                    :label="t('website.fields.logo')"
                    :upload="upload"
                    testid="website-image-logo"
                  />
                </ion-list>
              </ion-accordion>

              <!-- Header (hero): always there. -->
              <ion-accordion
                value="hero"
                data-testid="website-section-hero"
              >
                <ion-item slot="header">
                  <ion-label>
                    {{ t('website.sections.hero') }}
                    <p>{{ t('website.sections.always') }}</p>
                  </ion-label>
                </ion-item>
                <ion-list
                  slot="content"
                  inset
                >
                  <ion-item>
                    <ion-input
                      data-testid="website-field-hero-title"
                      :label="t('website.fields.title')"
                      label-placement="stacked"
                      :maxlength="80"
                      counter
                      :value="draft.content.hero.title"
                      :error-text="err('content.hero.title')"
                      :class="invalid('content.hero.title')"
                      @ion-input="draft.content.hero.title = text($event.detail.value)"
                    />
                  </ion-item>
                  <ion-item>
                    <ion-input
                      data-testid="website-field-hero-tagline"
                      :label="t('website.fields.tagline')"
                      label-placement="stacked"
                      :maxlength="160"
                      counter
                      :value="draft.content.hero.tagline"
                      :error-text="err('content.hero.tagline')"
                      :class="invalid('content.hero.tagline')"
                      @ion-input="draft.content.hero.tagline = text($event.detail.value)"
                    />
                  </ion-item>
                  <ImageUpload
                    v-model="draft.content.hero.cover"
                    :label="t('website.fields.cover')"
                    :upload="upload"
                    testid="website-image-cover"
                  />
                </ion-list>
              </ion-accordion>

              <!-- The optional sections, each with «Show». -->
              <ion-accordion
                v-for="name in OPTIONAL"
                :key="name"
                :value="name"
                :data-testid="`website-section-${name}`"
              >
                <ion-item slot="header">
                  <ion-label>
                    {{ t(`website.sections.${name}`) }}
                    <p v-if="draft.content[name].hidden">
                      {{ t('website.sections.hidden') }}
                    </p>
                  </ion-label>
                </ion-item>
                <ion-list
                  slot="content"
                  inset
                >
                  <ion-item>
                    <ion-toggle
                      :data-testid="`website-show-${name}`"
                      :checked="!draft.content[name].hidden"
                      justify="space-between"
                      @ion-change="setShown(name, $event.detail.checked)"
                    >
                      {{ t('website.sections.show') }}
                    </ion-toggle>
                  </ion-item>
                  <ion-item>
                    <ion-input
                      :data-testid="`website-field-${name}-title`"
                      :label="t('website.fields.heading')"
                      label-placement="stacked"
                      :helper-text="t('website.fields.headingHelp')"
                      :maxlength="80"
                      :value="draft.content[name].title"
                      :error-text="err(`content.${name}.title`)"
                      :class="invalid(`content.${name}.title`)"
                      @ion-input="draft.content[name].title = text($event.detail.value)"
                    />
                  </ion-item>

                  <template v-if="name === 'about'">
                    <ion-item>
                      <ion-textarea
                        data-testid="website-field-about-text"
                        :label="t('website.fields.text')"
                        label-placement="stacked"
                        :helper-text="t('website.fields.textHelp')"
                        auto-grow
                        :maxlength="4000"
                        counter
                        :value="draft.content.about.text"
                        :error-text="err('content.about.text')"
                        :class="invalid('content.about.text')"
                        @ion-input="draft.content.about.text = text($event.detail.value)"
                      />
                    </ion-item>
                    <ImageUpload
                      v-model="draft.content.about.image"
                      :label="t('website.fields.image')"
                      :upload="upload"
                      testid="website-image-about"
                    />
                  </template>

                  <template v-else-if="name === 'catalog'">
                    <ion-item>
                      <ion-select
                        data-testid="website-catalog-source"
                        :label="t('website.fields.source')"
                        label-placement="stacked"
                        interface="popover"
                        :value="draft.content.catalog.source ?? ''"
                        @ion-change="setSource($event.detail.value)"
                      >
                        <ion-select-option value="">
                          {{ t('website.fields.sourceNone') }}
                        </ion-select-option>
                        <ion-select-option
                          v-for="source in sources"
                          :key="source"
                          :value="source"
                        >
                          {{ source === 'inventory' ? t('website.fields.sourceInventory') : t('website.fields.sourceService') }}
                        </ion-select-option>
                      </ion-select>
                    </ion-item>
                    <ion-item
                      v-if="!sources.length"
                      lines="none"
                    >
                      <ion-note data-testid="website-catalog-no-source">
                        {{ t('website.fields.noSource') }}
                      </ion-note>
                    </ion-item>
                    <template v-if="draft.content.catalog.source">
                      <ion-item>
                        <CategoryPicker
                          v-model="draft.content.catalog.category_ids"
                          :source="draft.content.catalog.source"
                        />
                      </ion-item>
                      <ion-item>
                        <ion-toggle
                          data-testid="website-catalog-prices"
                          :checked="draft.content.catalog.show_prices"
                          justify="space-between"
                          @ion-change="draft.content.catalog.show_prices = $event.detail.checked"
                        >
                          {{ t('website.fields.showPrices') }}
                        </ion-toggle>
                      </ion-item>
                    </template>
                  </template>

                  <template v-else-if="name === 'contact'">
                    <ion-item
                      v-for="field in CONTACT_FIELDS"
                      :key="field"
                    >
                      <ion-input
                        :data-testid="`website-field-contact-${field}`"
                        :type="field === 'email' ? 'email' : 'tel'"
                        :label="t(`website.fields.${field}`)"
                        label-placement="stacked"
                        :helper-text="field === 'whatsapp' ? t('website.fields.whatsappHelp') : undefined"
                        :value="draft.content.contact[field]"
                        :error-text="err(`content.contact.${field}`)"
                        :class="invalid(`content.contact.${field}`)"
                        @ion-input="draft.content.contact[field] = text($event.detail.value)"
                      />
                    </ion-item>
                    <ion-item
                      v-for="network in SOCIALS"
                      :key="network"
                    >
                      <ion-input
                        :data-testid="`website-field-contact-${network}`"
                        type="url"
                        :label="t(`website.fields.${network}`)"
                        label-placement="stacked"
                        :helper-text="t('website.fields.socialsHelp')"
                        :placeholder="HTTPS"
                        :value="draft.content.contact.socials[network]"
                        :error-text="err(`content.contact.socials.${network}`)"
                        :class="invalid(`content.contact.socials.${network}`)"
                        @ion-input="draft.content.contact.socials[network] = text($event.detail.value)"
                      />
                    </ion-item>
                    <ion-item>
                      <ion-toggle
                        data-testid="website-show-hours"
                        :checked="draft.content.contact.hours.length > 0"
                        justify="space-between"
                        @ion-change="setHoursShown($event.detail.checked)"
                      >
                        {{ t('website.fields.showHours') }}
                      </ion-toggle>
                    </ion-item>
                    <HoursEditor
                      v-if="draft.content.contact.hours.length"
                      v-model="draft.content.contact.hours"
                      :error="err('content.contact.hours')"
                    />
                  </template>

                  <template v-else>
                    <ion-item
                      v-for="(line, index) in draft.content.location.address_lines"
                      :key="index"
                    >
                      <ion-input
                        :data-testid="`website-field-location-line-${index}`"
                        :label="t('website.fields.addressLine', { n: index + 1 })"
                        label-placement="stacked"
                        :maxlength="120"
                        :value="line"
                        :error-text="err(`content.location.address_lines.${index}`)"
                        :class="invalid(`content.location.address_lines.${index}`)"
                        @ion-input="draft.content.location.address_lines[index] = text($event.detail.value)"
                      />
                    </ion-item>
                    <ion-item>
                      <ion-input
                        data-testid="website-field-location-map_url"
                        type="url"
                        :label="t('website.fields.mapUrl')"
                        label-placement="stacked"
                        :helper-text="t('website.fields.mapUrlHelp')"
                        :placeholder="HTTPS"
                        :value="draft.content.location.map_url"
                        :error-text="err('content.location.map_url')"
                        :class="invalid('content.location.map_url')"
                        @ion-input="draft.content.location.map_url = text($event.detail.value)"
                      />
                    </ion-item>
                  </template>
                </ion-list>
              </ion-accordion>

              <!-- Footer: always there, with «Log in». -->
              <ion-accordion
                value="footer"
                data-testid="website-section-footer"
              >
                <ion-item slot="header">
                  <ion-label>
                    {{ t('website.sections.footer') }}
                    <p>{{ t('website.sections.always') }}</p>
                  </ion-label>
                </ion-item>
                <ion-list
                  slot="content"
                  inset
                >
                  <ion-item>
                    <ion-input
                      data-testid="website-field-footer-text"
                      :label="t('website.fields.footerText')"
                      label-placement="stacked"
                      :helper-text="t('website.fields.footerTextHelp')"
                      :maxlength="200"
                      :value="draft.content.footer.text"
                      :error-text="err('content.footer.text')"
                      :class="invalid('content.footer.text')"
                      @ion-input="draft.content.footer.text = text($event.detail.value)"
                    />
                  </ion-item>
                </ion-list>
              </ion-accordion>
            </ion-accordion-group>
          </section>
          <section class="we-preview">
            <PreviewFrame :reload-key="previewKey" />
          </section>
        </div>
      </template>
      <ShareDialog
        v-model:open="sharing"
        :url="site.public_url"
        :is-live="site.is_live"
      />
    </div>
    <p
      v-else
      class="we-loading"
      data-testid="website-loading"
    >
      <ion-spinner name="crescent" />
      {{ t('website.loading') }}
    </p>
  </AppPage>
</template>

<style scoped>
.we {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px 24px;
}
.we-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
}
.we-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.we-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}
.we-save-state {
  margin-inline-end: auto;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
.we-heading {
  margin: 20px 4px 8px;
  font-size: 1rem;
  font-weight: 600;
}
.we-mode {
  margin-block: 4px 8px;
}
.we-note {
  font-size: 0.8125rem;
  padding-block: 4px;
}
.we-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}
.we-preview {
  min-height: 70vh;
}
/* Tablet and phone: one of the two at a time. */
.we-grid--edit .we-preview,
.we-grid--preview .we-form {
  display: none;
}
@media (min-width: 992px) {
  .we-switch {
    display: none;
  }
  .we-grid {
    grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
    align-items: start;
  }
  .we-grid--edit .we-preview,
  .we-grid--preview .we-form {
    display: block;
  }
  .we-preview {
    position: sticky;
    top: 0;
    height: calc(100vh - 160px);
  }
}
</style>
