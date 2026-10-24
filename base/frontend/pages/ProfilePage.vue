<script setup lang="ts">
// «My profile» (`/profile`, BASE-G125, G126; the old hub's ProfilePage): the person heading it (photo, name, role in
// this business), «Account details» (name, surname, contact email: never the email they sign in with), the photo,
// «Preferences» (language, mode and palette: saved for them, so they follow them to any device, and applied at once)
// and «PIN» (their own: the current one when they have one, the new one twice). The profile comes live
// (`base.profile.get`): a change saved elsewhere repaints what the person has not touched. A profile that cannot be
// read offers nothing to save, only «Retry» (hub#2541).
import { ImageUpload, type ImageUploadValue, InlineFeedback, UserAvatar } from '@erplora/ui/components';
import { ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import {
  AppPage,
  applyUserThemePreferences,
  resetUserThemePreferences,
  THEME_PALETTES,
  type ThemeMode,
  type ThemePalette,
} from '@erplora/ui/shell';
import { IonButton, IonInput, IonLabel, IonSegment, IonSegmentButton, IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed, getCurrentInstance, ref, watch } from 'vue';

import { sessionChanged } from '../lib/access';
import { useBaseI18n } from '../lib/i18n';
import type { Preferences, Profile, ProfileLanguage, ProfileThemeMode } from '../operations';

type DataForm = { first_name: string; last_name: string; contact_email: string };

const { t } = useBaseI18n();
const i18n = getCurrentInstance()?.appContext.config.globalProperties as unknown as { $i18n: { locale: string } };
const { data: profile, status, error: loadError, refresh } = useLive('base.profile.get', {});
const update = useCommand('base.profile.update');
const prefsCommand = useCommand('base.profile.preferences_set');
const pinCommand = useCommand('base.pin.set');
const avatarSet = useCommand('base.profile.avatar_set');
const avatarRemove = useCommand('base.profile.avatar_remove');

const fullName = computed(() => [profile.value?.first_name, profile.value?.last_name].filter(Boolean).join(' '));
const roleLabel = computed(() => (profile.value?.role ? t(`base.profile.roles.${profile.value.role}`) : ''));

// ── Account details ──
const form = ref<DataForm | null>(null);
const dirty = ref(false);
const saved = ref(false);

function fromProfile(value: Profile): DataForm {
  return { first_name: value.first_name, last_name: value.last_name, contact_email: value.contact_email };
}

watch(
  profile,
  (value) => {
    if (value && !dirty.value) form.value = fromProfile(value);
  },
  { immediate: true },
);

function setField(field: keyof DataForm, value: unknown): void {
  if (!form.value) return;
  form.value = { ...form.value, [field]: value === null || value === undefined ? '' : String(value) };
  dirty.value = true;
  saved.value = false;
}

async function saveData(): Promise<void> {
  if (!form.value || update.pending.value) return;
  try {
    const answer = await update.run({ ...form.value });
    form.value = fromProfile(answer);
    dirty.value = false;
    saved.value = true;
    sessionChanged(); // the side menu says the new name without a reload
  } catch {
    saved.value = false; // The card paints the error; what was typed stays.
  }
}

// ── Photo ──
const photo = computed<ImageUploadValue | null>(() =>
  profile.value?.avatar_url ? { id: 'avatar', url: profile.value.avatar_url } : null,
);
const photoNote = ref('');

function asBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).replace(/^data:[^,]*,/, ''));
    reader.onerror = () => reject(reader.error ?? new Error('unreadable file'));
    reader.readAsDataURL(file);
  });
}

async function uploadPhoto(file: File): Promise<ImageUploadValue> {
  photoNote.value = '';
  try {
    const answer = await avatarSet.run({
      content_type: file.type as 'image/jpeg' | 'image/png' | 'image/webp',
      data_base64: await asBase64(file),
    });
    photoNote.value = t('base.profile.photo.saved');
    return { id: 'avatar', url: answer.avatar_url };
  } catch (reason) {
    throw new Error(reason instanceof ApiError && reason.message ? reason.message : t('base.profile.photo.failed'));
  }
}

async function onPhoto(value: ImageUploadValue | null): Promise<void> {
  if (value !== null) return;
  photoNote.value = '';
  try {
    await avatarRemove.run({});
    photoNote.value = t('base.profile.photo.removed');
  } catch {
    photoNote.value = t('base.profile.photo.failed');
  }
}

// ── Preferences ──
const prefs = ref<Preferences>({ language: '', theme_mode: '', palette: '' });
const prefsError = ref('');
watch(
  profile,
  (value) => {
    if (value && !prefsCommand.pending.value) {
      prefs.value = { language: value.language, theme_mode: value.theme_mode, palette: value.palette };
    }
  },
  { immediate: true },
);

const LANGUAGES: ProfileLanguage[] = ['', 'es', 'en'];
const MODES: Exclude<ProfileThemeMode, ''>[] = ['system', 'light', 'dark'];
const PALETTES = THEME_PALETTES as readonly ThemePalette[];

function paint(value: Preferences): void {
  if (!value.theme_mode && !value.palette) {
    resetUserThemePreferences();
    return;
  }
  applyUserThemePreferences((value.theme_mode || null) as ThemeMode | null, (value.palette || null) as ThemePalette | null);
}

async function savePrefs(change: Partial<Preferences>): Promise<void> {
  const wanted = { ...prefs.value, ...change };
  prefs.value = wanted;
  prefsError.value = '';
  try {
    const answer = await prefsCommand.run(wanted);
    if (answer.language === 'es' || answer.language === 'en') i18n.$i18n.locale = answer.language;
    if ('theme_mode' in change || 'palette' in change) paint(wanted);
  } catch (reason) {
    prefsError.value = reason instanceof ApiError && reason.message ? reason.message : t('base.profile.prefs.failed');
  }
}

// ── PIN ──
const pin = ref({ current: '', fresh: '', repeat: '' });
const pinError = ref('');
const pinSaved = ref(false);

function setPin(field: 'current' | 'fresh' | 'repeat', value: unknown): void {
  pin.value = { ...pin.value, [field]: value === null || value === undefined ? '' : String(value) };
  pinSaved.value = false;
}

async function savePin(): Promise<void> {
  const current = profile.value;
  if (!current || pinCommand.pending.value) return;
  pinError.value = '';
  if (!new RegExp(`^\\d{${current.pin_length}}$`).test(pin.value.fresh)) {
    pinError.value = t('base.profile.pin.length', { n: current.pin_length });
    return;
  }
  if (pin.value.fresh !== pin.value.repeat) {
    pinError.value = t('base.profile.pin.mismatch');
    return;
  }
  try {
    await pinCommand.run(current.has_pin ? { pin: pin.value.fresh, current: pin.value.current } : { pin: pin.value.fresh });
    pin.value = { current: '', fresh: '', repeat: '' };
    pinSaved.value = true;
  } catch (reason) {
    pinError.value = reason instanceof ApiError && reason.message ? reason.message : t('base.profile.data.failed');
  }
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <AppPage
    :title="t('base.profile.title')"
    back-href="/"
    content-layout="detail"
  >
    <p
      v-if="!profile && status !== 'error'"
      class="profile__loading"
      data-testid="profile-loading"
    >
      <ion-spinner name="crescent" />
      {{ t('base.profile.loading') }}
    </p>
    <InlineFeedback
      v-else-if="!profile"
      tone="danger"
      data-testid="profile-load-error"
      :heading="t('base.profile.loadErrorTitle')"
    >
      {{ t('base.profile.loadError') }}
      <ion-button
        size="small"
        fill="outline"
        data-testid="profile-retry"
        @click="refresh()"
      >
        {{ t('base.profile.retry') }}
      </ion-button>
    </InlineFeedback>
    <template v-else>
      <section
        class="profile__summary"
        data-testid="profile-summary"
        :aria-label="t('base.profile.summary')"
      >
        <UserAvatar
          :name="fullName || '?'"
          :src="profile.avatar_url || null"
          size="xl"
          decorative
        />
        <div class="profile__who">
          <h1 class="profile__name">
            {{ fullName }}
          </h1>
          <p class="profile__subtitle">
            {{ t('base.profile.subtitle') }}
          </p>
          <span
            v-if="roleLabel"
            class="profile__role"
          >{{ roleLabel }}</span>
        </div>
      </section>

      <div class="profile__grid">
        <section class="profile__card">
          <h2 class="profile__card-title">
            {{ t('base.profile.data.title') }}
          </h2>
          <form
            v-if="form"
            class="profile__form"
            @submit.prevent="saveData"
          >
            <ion-input
              data-testid="profile-first-name"
              :value="form.first_name"
              :label="t('base.profile.data.firstName')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :maxlength="150"
              autocomplete="given-name"
              @ion-input="setField('first_name', $event.detail.value)"
            />
            <ion-input
              data-testid="profile-last-name"
              :value="form.last_name"
              :label="t('base.profile.data.lastName')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :maxlength="150"
              autocomplete="family-name"
              @ion-input="setField('last_name', $event.detail.value)"
            />
            <ion-input
              data-testid="profile-email"
              type="email"
              :value="form.contact_email"
              :label="t('base.profile.data.email')"
              :helper-text="t('base.profile.data.emailHelp')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :maxlength="254"
              autocomplete="email"
              @ion-input="setField('contact_email', $event.detail.value)"
            />
            <p
              v-if="roleLabel"
              class="profile__note"
            >
              {{ t('base.profile.data.role', { role: roleLabel }) }}
            </p>
            <InlineFeedback
              v-if="update.error.value"
              tone="danger"
              data-testid="profile-save-error"
              :heading="t('base.profile.data.failed')"
            >
              {{ update.error.value.message }}
            </InlineFeedback>
            <InlineFeedback
              v-if="saved"
              tone="success"
              data-testid="profile-saved"
            >
              {{ t('base.profile.data.saved') }}
            </InlineFeedback>
            <ion-button
              type="submit"
              expand="block"
              data-testid="profile-save"
              :disabled="update.pending.value"
              @click="saveData"
            >
              {{ t('base.profile.data.save') }}
            </ion-button>
          </form>
          <ImageUpload
            :model-value="photo"
            :label="t('base.profile.photo.label')"
            :upload="uploadPhoto"
            :max-bytes="2 * 1024 * 1024"
            testid="profile-photo"
            @update:model-value="onPhoto"
          />
          <p
            v-if="photoNote"
            class="profile__note"
            role="status"
            data-testid="profile-photo-note"
          >
            {{ photoNote }}
          </p>
        </section>

        <section class="profile__card">
          <h2 class="profile__card-title">
            {{ t('base.profile.prefs.title') }}
          </h2>
          <ion-select
            data-testid="profile-language"
            :value="prefs.language"
            :label="t('base.profile.prefs.language')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="savePrefs({ language: text($event.detail.value) as ProfileLanguage })"
          >
            <ion-select-option
              v-for="language in LANGUAGES"
              :key="language || 'business'"
              :value="language"
            >
              {{ language === '' ? t('base.profile.prefs.businessLanguage') : language === 'es' ? 'Español' : 'English' }}
            </ion-select-option>
          </ion-select>
          <p class="profile__note">
            {{ t('base.profile.prefs.languageHelp') }}
          </p>
          <h3 class="profile__label">
            {{ t('base.profile.prefs.appearance') }}
          </h3>
          <p class="profile__note">
            {{ t('base.profile.prefs.appearanceHelp') }}
          </p>
          <h4 class="profile__eyebrow">
            {{ t('base.profile.prefs.palette') }}
          </h4>
          <div
            class="profile__palettes"
            role="radiogroup"
            :aria-label="t('base.profile.prefs.palette')"
          >
            <button
              v-for="palette in PALETTES"
              :key="palette"
              type="button"
              role="radio"
              class="profile__palette"
              :class="{ 'is-chosen': prefs.palette === palette }"
              :aria-checked="prefs.palette === palette"
              :data-testid="`profile-palette-${palette}`"
              :data-ep-palette-swatch="palette"
              @click="savePrefs({ palette })"
            >
              <span
                class="profile__swatch"
                :class="`profile__swatch--${palette}`"
                aria-hidden="true"
              />
              <span class="profile__palette-name">{{ palette.charAt(0).toUpperCase() + palette.slice(1) }}</span>
            </button>
          </div>
          <h4 class="profile__eyebrow">
            {{ t('base.profile.prefs.mode') }}
          </h4>
          <ion-segment
            class="profile__mode"
            data-testid="profile-mode"
            :value="prefs.theme_mode || 'system'"
            :aria-label="t('base.profile.prefs.mode')"
            @ion-change="savePrefs({ theme_mode: text($event.detail.value) as ProfileThemeMode })"
          >
            <ion-segment-button
              v-for="mode in MODES"
              :key="mode"
              :value="mode"
            >
              <ion-label>{{ t(`base.profile.prefs.modes.${mode}`) }}</ion-label>
            </ion-segment-button>
          </ion-segment>
          <ion-button
            fill="clear"
            size="small"
            data-testid="profile-appearance-business"
            :disabled="!prefs.theme_mode && !prefs.palette"
            @click="savePrefs({ theme_mode: '', palette: '' })"
          >
            {{ t('base.profile.prefs.business') }}
          </ion-button>
          <InlineFeedback
            v-if="prefsError"
            tone="danger"
            data-testid="profile-prefs-error"
            :heading="prefsError"
          />
        </section>
      </div>

      <section
        class="profile__card"
        data-testid="profile-pin"
      >
        <h2 class="profile__card-title">
          {{ t('base.profile.pin.title') }}
        </h2>
        <p class="profile__note">
          {{ profile.has_pin ? t('base.profile.pin.intro') : t('base.profile.pin.introNone') }}
        </p>
        <form
          class="profile__form profile__form--pin"
          @submit.prevent="savePin"
        >
          <ion-input
            v-if="profile.has_pin"
            data-testid="profile-pin-current"
            type="password"
            inputmode="numeric"
            autocomplete="current-password"
            :value="pin.current"
            :label="t('base.profile.pin.current')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="profile.pin_length"
            @ion-input="setPin('current', $event.detail.value)"
          />
          <ion-input
            data-testid="profile-pin-new"
            type="password"
            inputmode="numeric"
            autocomplete="new-password"
            :value="pin.fresh"
            :label="t('base.profile.pin.new')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="profile.pin_length"
            @ion-input="setPin('fresh', $event.detail.value)"
          />
          <ion-input
            data-testid="profile-pin-repeat"
            type="password"
            inputmode="numeric"
            autocomplete="new-password"
            :value="pin.repeat"
            :label="t('base.profile.pin.repeat')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="profile.pin_length"
            @ion-input="setPin('repeat', $event.detail.value)"
          />
          <p
            v-if="pinError"
            class="profile__error"
            role="alert"
            data-testid="profile-pin-error"
          >
            {{ pinError }}
          </p>
          <InlineFeedback
            v-if="pinSaved"
            tone="success"
            data-testid="profile-pin-saved"
          >
            {{ t('base.profile.pin.saved') }}
          </InlineFeedback>
          <ion-button
            type="submit"
            data-testid="profile-pin-save"
            :disabled="pinCommand.pending.value"
            @click="savePin"
          >
            {{ profile.has_pin ? t('base.profile.pin.change') : t('base.profile.pin.set') }}
          </ion-button>
        </form>
      </section>
      <p
        v-if="loadError && status === 'error'"
        class="profile__note"
      >
        {{ loadError.message }}
      </p>
    </template>
  </AppPage>
</template>

<style scoped>
.profile__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ion-color-medium);
}

.profile__summary {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 8px 0 20px;
}

.profile__who {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.profile__name {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.profile__subtitle {
  margin: 0;
  color: var(--ion-color-medium);
}

.profile__role {
  align-self: flex-start;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(var(--ion-color-primary-rgb, 22, 151, 213), 0.12);
  color: var(--ion-color-primary);
  font-size: 0.8125rem;
  font-weight: 600;
}

.profile__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.profile__card {
  box-sizing: border-box;
  padding: 20px;
  border-radius: var(--ep-radius-lg, 16px);
  border: 1px solid var(--ion-color-step-150, #d7d8da);
  background: var(--ion-card-background, var(--ion-background-color));
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.profile__card-title {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
}

.profile__form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.profile__form--pin {
  max-width: 420px;
}

.profile__label {
  margin: 8px 0 0;
  font-size: 1rem;
  font-weight: 600;
}

/* Each button as wide as its words, as in the old hub: Ionic's segment is a grid of equal columns (`1fr`), which cut
   «System (auto)» into «System (au…» on a narrow card. The three fit side by side down to 375 px. */
.profile__mode {
  grid-auto-columns: auto;
  justify-content: start;
}

.profile__eyebrow {
  margin: 4px 0 0;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ion-color-medium);
}

.profile__note {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
}

.profile__error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}

.profile__palettes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.profile__palette {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px;
  min-width: 64px;
  border: 1px solid transparent;
  border-radius: var(--ep-radius, 12px);
  background: transparent;
  color: var(--ion-text-color);
  font: inherit;
  cursor: pointer;
}

.profile__palette.is-chosen {
  border-color: var(--ion-color-primary);
}

.profile__palette:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}

.profile__swatch {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid var(--ion-background-color, #fff);
  box-shadow: 0 0 0 1px var(--ion-color-step-150, #d7d8da);
}

.profile__swatch--erplora {
  background: #1496d6;
}

.profile__swatch--terracotta {
  background: #e8552a;
}

.profile__swatch--corporate {
  background: #0f3f9c;
}

.profile__swatch--minimal {
  background: #111111;
}

.profile__swatch--forest {
  background: #1f542a;
}

.profile__swatch--ocean {
  background: #008cbd;
}

.profile__swatch--violet {
  background: #742ad9;
}

.profile__palette-name {
  font-size: 0.8125rem;
}
</style>
