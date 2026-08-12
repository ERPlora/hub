<template>
  <AppPage :title="t('profile.title')" back-href="/dashboard" content-layout="detail" heading-on-screen>
    <main class="profile-page">
      <section class="profile-hero" aria-labelledby="profile-name">
        <ok-avatar
          class="profile-avatar"
          :name="displayName"
          :email="displayEmail"
          :src="user?.avatarUrl || undefined"
          size="lg"
        ></ok-avatar>
        <div class="avatar-actions">
          <input
            ref="avatarInput"
            hidden
            type="file"
            accept="image/jpeg,image/png,image/webp"
            @change="onAvatarSelected"
          />
          <ion-button size="small" fill="outline" :disabled="avatarSaving" @click="avatarInput?.click()">
            <HubIcon slot="start" name="camera-outline" />
            {{ t('profile.changePhoto') }}
          </ion-button>
          <ion-button
            v-if="user?.avatarUrl"
            size="small"
            fill="clear"
            color="medium"
            :disabled="avatarSaving"
            @click="removeAvatar"
          >
            {{ t('profile.removePhoto') }}
          </ion-button>
        </div>
        <div class="profile-identity">
          <p class="profile-eyebrow">{{ t('profile.title') }}</p>
          <h1 id="profile-name">{{ displayName }}</h1>
          <p>{{ t('profile.subtitle') }}</p>
          <div class="profile-badges" aria-label="Account summary">
            <span class="profile-badge">
              <HubIcon name="shield-checkmark-outline" />
              {{ roleLabel }}
            </span>
            <span class="profile-badge profile-badge-muted">
              <HubIcon :name="cloudLinked ? 'globe-outline' : 'person-outline'" />
              {{ accountTypeLabel }}
            </span>
          </div>
        </div>
      </section>

      <div class="profile-grid">
        <ion-card class="profile-card">
          <ion-card-header>
            <div class="card-heading">
              <span class="card-icon"><HubIcon name="person-circle-outline" /></span>
              <div>
                <ion-card-title>{{ t('profile.accountTitle') }}</ion-card-title>
                <ion-card-subtitle>{{ t('profile.subtitle') }}</ion-card-subtitle>
              </div>
            </div>
          </ion-card-header>
          <ion-card-content class="profile-card-content">
            <div class="profile-form">
              <ion-input
                v-model="firstName"
                mode="md"
                fill="outline"
                :label="t('profile.firstName')"
                label-placement="stacked"
                autocomplete="given-name"
              />
              <ion-input
                v-model="lastName"
                mode="md"
                fill="outline"
                :label="t('profile.lastName')"
                label-placement="stacked"
                autocomplete="family-name"
              />
              <ion-input
                v-model="email"
                mode="md"
                fill="outline"
                type="email"
                :label="t('profile.email')"
                label-placement="stacked"
                autocomplete="email"
              />
              <div class="readonly-summary">
                <span>{{ t('profile.role') }}: <strong>{{ roleLabel }}</strong></span>
                <span>{{ accountTypeLabel }}</span>
              </div>
              <ion-button expand="block" :disabled="profileSaving || loading" @click="saveIdentity">
                {{ profileSaving ? t('profile.saving') : t('profile.saveProfile') }}
              </ion-button>
            </div>
          </ion-card-content>
        </ion-card>

        <ion-card class="profile-card">
          <ion-card-header>
            <div class="card-heading">
              <span class="card-icon"><HubIcon name="color-palette-outline" /></span>
              <ion-card-title>{{ t('profile.preferencesTitle') }}</ion-card-title>
            </div>
          </ion-card-header>
          <ion-card-content class="preferences-content">
            <div class="preference-row">
              <div class="preference-copy">
                <HubIcon name="language-outline" />
                <div>
                  <h2>{{ t('profile.language') }}</h2>
                  <p>{{ t('profile.languageDesc') }}</p>
                </div>
              </div>
              <ion-select
                v-model="selectedLocale"
                interface="popover"
                :aria-label="t('profile.language')"
                @ion-change="onLocaleChange($event.detail.value as string)"
              >
                <ion-select-option value="">{{ t('profile.useHubLanguage') }}</ion-select-option>
                <ion-select-option v-for="item in availableLocales" :key="item.code" :value="item.code">
                  {{ item.name }}
                </ion-select-option>
              </ion-select>
            </div>

            <div class="preference-divider" />

            <div class="appearance-heading">
              <div class="preference-copy">
                <HubIcon name="color-palette-outline" />
                <div>
                  <h2>{{ t('profile.appearance') }}</h2>
                  <p>{{ t('profile.appearanceDesc') }}</p>
                </div>
              </div>
            </div>
            <ok-theme-picker
              class="profile-theme-picker"
              :palette="themePalette"
              :mode="themeMode"
              :labels.prop="pickerLabels"
              @ok-change="onPickerChange"
            ></ok-theme-picker>
            <ion-button
              v-if="hasLocalPalette || personalMode"
              size="small"
              fill="clear"
              class="follow-hub-button"
              @click="followHubAppearance"
            >
              {{ t('profile.useHubAppearance') }}
            </ion-button>
          </ion-card-content>
        </ion-card>
      </div>

      <section class="management-panel">
        <span class="management-icon">
          <HubIcon :name="cloudLinked ? 'globe-outline' : 'information-circle-outline'" />
        </span>
        <div class="management-copy">
          <h2>{{ t('profile.manageTitle') }}</h2>
          <p>{{ t(cloudLinked ? 'profile.manageCloud' : 'profile.manageLocal') }}</p>
        </div>
        <ion-button v-if="cloudLinked" fill="outline" @click="manageCloudAccount">
          {{ t('profile.manageInSaas') }}
          <HubIcon slot="end" name="open-outline" />
        </ion-button>
      </section>
    </main>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonButton,
  IonCard,
  IonCardContent,
  IonCardHeader,
  IonCardSubtitle,
  IonCardTitle,
  IonInput,
  IonSelect,
  IonSelectOption,
} from '@ionic/vue';
import AppPage from '../components/AppPage.vue';
import HubIcon from '../components/HubIcon.vue';
import { availableLocales } from '../i18n';
import { getAccessToken } from '../lib/cloud';
import { config } from '../lib/config';
import { openExternal } from '../lib/open-external';
import { user } from '../lib/session';
import {
  hasLocalPalette,
  themeMode,
  themePalette,
  type ThemeMode,
  type ThemePalette,
} from '../lib/theme';
import {
  currentUserProfile,
  deleteUserAvatar,
  getUserProfile,
  updateUserPreferences,
  updateUserProfile,
  uploadUserAvatar,
  type UserPreferences,
} from '../lib/user-profile';
import { toast } from '../lib/toast';

const { t } = useI18n();
const selectedLocale = ref<string>('');
const firstName = ref('');
const lastName = ref('');
const email = ref('');
const loading = ref(true);
const profileSaving = ref(false);
const avatarSaving = ref(false);
const avatarInput = ref<HTMLInputElement | null>(null);
const personalMode = computed(() => currentUserProfile.value?.preferences.theme_mode ?? null);
const cloudLinked = computed<boolean>(() => Boolean(getAccessToken()));

const displayName = computed<string>(() => user.value?.name?.trim() || t('profile.defaultRole'));
const displayEmail = computed<string>(() => user.value?.email?.trim() || '');

const roleLabel = computed<string>(() => {
  const role = user.value?.role?.trim().toLowerCase();
  const knownRoles: Record<string, string> = {
    owner: 'profile.roleOwner',
    admin: 'profile.roleAdmin',
    manager: 'profile.roleManager',
    employee: 'profile.roleEmployee',
  };
  return role ? t(knownRoles[role] ?? 'profile.defaultRole') : t('profile.defaultRole');
});

const accountTypeLabel = computed<string>(() =>
  t(cloudLinked.value ? 'profile.cloudAccount' : 'profile.localAccount'),
);

const pickerLabels = computed(() => ({
  palette: t('settings.themePalette'),
  mode: t('settings.theme'),
  system: t('settings.themeSystem'),
  light: t('settings.themeLight'),
  dark: t('settings.themeDark'),
}));

function syncForm(): void {
  const profile = currentUserProfile.value;
  if (!profile) return;
  firstName.value = profile.first_name;
  lastName.value = profile.last_name;
  email.value = profile.email;
  selectedLocale.value = profile.preferences.language ?? '';
}

function preferences(partial: Partial<UserPreferences> = {}): UserPreferences {
  const existing = currentUserProfile.value?.preferences ?? {
    language: null,
    theme_mode: null,
    theme_palette: null,
  };
  return { ...existing, ...partial };
}

async function onLocaleChange(value: string): Promise<void> {
  selectedLocale.value = value;
  try {
    await updateUserPreferences(preferences({ language: value || null }));
  } catch {
    syncForm();
    await toast(t('profile.saveError'), 'danger');
  }
}

async function onPickerChange(event: Event): Promise<void> {
  const { palette, mode } = (
    event as CustomEvent<{ palette: ThemePalette; mode: ThemeMode }>
  ).detail;
  try {
    await updateUserPreferences(preferences({ theme_mode: mode, theme_palette: palette }));
  } catch {
    await getUserProfile().catch(() => null);
    await toast(t('profile.saveError'), 'danger');
  }
}

async function followHubAppearance(): Promise<void> {
  try {
    await updateUserPreferences(preferences({ theme_mode: null, theme_palette: null }));
  } catch {
    await toast(t('profile.saveError'), 'danger');
  }
}

async function saveIdentity(): Promise<void> {
  const profile = currentUserProfile.value;
  if (!profile) return;
  profileSaving.value = true;
  try {
    await updateUserProfile({
      first_name: firstName.value,
      last_name: lastName.value,
      email: email.value,
      preferences: profile.preferences,
    });
    syncForm();
    await toast(t('profile.saved'), 'success');
  } catch {
    await toast(t('profile.saveError'), 'danger');
  } finally {
    profileSaving.value = false;
  }
}

async function onAvatarSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  avatarSaving.value = true;
  try {
    await uploadUserAvatar(file);
    await toast(t('profile.photoSaved'), 'success');
  } catch {
    await toast(t('profile.photoError'), 'danger');
  } finally {
    avatarSaving.value = false;
  }
}

async function removeAvatar(): Promise<void> {
  avatarSaving.value = true;
  try {
    await deleteUserAvatar();
  } catch {
    await toast(t('profile.photoError'), 'danger');
  } finally {
    avatarSaving.value = false;
  }
}

// The account lives in the SaaS, so this is a trip to the user's own browser. It used to be fired
// and forgotten (`void`), which inside the installed app meant pressing it did nothing at all and
// said nothing either (hub#475).
async function manageCloudAccount(): Promise<void> {
  const base = config.cloudApiUrl.replace(/\/+$/, '');
  try {
    await openExternal(`${base}/dashboard/profile/`);
  } catch {
    await toast(t('profile.cloudAccountError'), 'danger');
  }
}

onMounted(async () => {
  try {
    await getUserProfile();
    syncForm();
  } catch {
    await toast(t('profile.loadError'), 'danger');
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.profile-page {
  padding: 4px 0 28px;
  container-type: inline-size;
}

.profile-hero {
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 20px 22px 24px;
}

.avatar-actions {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.avatar-actions ion-button {
  margin: 0;
}

.profile-avatar {
  --ok-avatar-size: 76px;
  flex: 0 0 auto;
}

.profile-identity {
  min-width: 0;
}

.profile-eyebrow {
  margin: 0 0 4px;
  color: var(--ion-color-primary);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.profile-identity h1 {
  margin: 0;
  color: var(--ion-text-color);
  font-size: clamp(1.55rem, 3vw, 2.05rem);
  font-weight: 700;
  letter-spacing: -0.025em;
}

.profile-identity > p:not(.profile-eyebrow) {
  margin: 5px 0 0;
  color: var(--ion-color-medium);
  font-size: 0.95rem;
}

.profile-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.profile-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(var(--ion-color-primary-rgb), 0.11);
  color: var(--ion-color-primary-shade);
  font-size: 0.78rem;
  font-weight: 650;
}

.profile-badge-muted {
  background: rgba(var(--ion-color-medium-rgb), 0.12);
  color: var(--ion-color-medium-shade);
}

.profile-badge :deep(.hub-icon),
.preference-copy :deep(.hub-icon),
.card-icon :deep(.hub-icon),
.management-icon :deep(.hub-icon) {
  width: 18px;
  height: 18px;
}

.profile-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 16px;
}

.profile-card {
  height: 100%;
  margin: 0;
}

.profile-card ion-card-header {
  padding: 20px 20px 14px;
}

.card-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-icon,
.management-icon {
  display: grid;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 12px;
  background: rgba(var(--ion-color-primary-rgb), 0.11);
  color: var(--ion-color-primary);
}

.card-heading ion-card-title {
  font-size: 1rem;
  font-weight: 700;
}

.card-heading ion-card-subtitle {
  margin-top: 3px;
  color: var(--ion-color-medium);
  font-size: 0.76rem;
  font-weight: 400;
  letter-spacing: 0;
  line-height: 1.35;
  text-transform: none;
}

.profile-card-content {
  padding: 0 20px 20px;
}

.profile-form {
  display: grid;
  gap: 14px;
}

/* No hand-drawn border here: `fill="outline"` + mode="md" draws the real one (hub#760). This used
   to paint its own box because the Ionic outline was a silent no-op in `ios` mode — keeping it now
   would stack a second border, and its hardcoded light background ignores the dark palette. */
.profile-form ion-input {
  --highlight-color-focused: var(--ion-color-primary);
}

.readonly-summary {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px 16px;
  color: var(--ion-color-medium);
  font-size: 0.78rem;
}

.preferences-content {
  padding: 0 20px 20px;
}

.preference-row {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-content: space-between;
}

.preference-copy {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.preference-copy > :deep(.hub-icon) {
  flex: 0 0 auto;
  margin-top: 2px;
  color: var(--ion-color-primary);
}

.preference-copy h2,
.management-copy h2 {
  margin: 0;
  color: var(--ion-text-color);
  font-size: 0.9rem;
  font-weight: 700;
}

.preference-copy p,
.management-copy p {
  margin: 3px 0 0;
  color: var(--ion-color-medium);
  font-size: 0.78rem;
  line-height: 1.45;
}

.preference-row ion-select {
  flex: 0 0 auto;
  max-width: 150px;
}

.preference-divider {
  height: 1px;
  margin: 18px 0;
  background: var(--ion-color-light-shade);
}

.appearance-heading {
  margin-bottom: 14px;
}

.profile-theme-picker {
  display: block;
}

.follow-hub-button {
  margin: 8px 0 0;
}

.management-panel {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 16px;
  padding: 18px 20px;
  border: 1px solid rgba(var(--ion-color-primary-rgb), 0.14);
  border-radius: 16px;
  background: rgba(var(--ion-color-primary-rgb), 0.045);
}

.management-copy {
  min-width: 0;
  flex: 1;
}

.management-panel ion-button {
  flex: 0 0 auto;
  margin: 0;
}

/* El asistente reduce el CONTENEDOR sin cambiar el viewport. Esta query hace que Perfil refluyera
   también en ese caso, no solo al estrechar físicamente la ventana. */
@container (max-width: 620px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}

@container (max-width: 720px) {
  .profile-hero {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: start;
  }

  .profile-avatar {
    grid-column: 1;
    grid-row: 1;
  }

  .profile-identity {
    grid-column: 2;
    grid-row: 1;
  }

  .avatar-actions {
    grid-column: 2;
    grid-row: 2;
    flex-direction: row;
    flex-wrap: wrap;
    margin-top: 10px;
  }
}

@media (max-width: 560px) {
  .profile-page {
    padding-top: 0;
  }

  .profile-hero {
    align-items: flex-start;
    gap: 14px;
    padding: 14px 4px 20px;
  }

  .profile-avatar {
    --ok-avatar-size: 56px;
  }

  .profile-badges {
    gap: 6px;
  }

  .profile-badge {
    font-size: 0.72rem;
  }

  .profile-card ion-card-header,
  .profile-card-content,
  .preferences-content {
    padding-left: 16px;
    padding-right: 16px;
  }

  .preference-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .preference-row ion-select {
    width: 100%;
    max-width: none;
  }

  .management-panel {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .management-panel ion-button {
    width: 100%;
  }
}
</style>
