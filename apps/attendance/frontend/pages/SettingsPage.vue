<script setup lang="ts">
// Time clock → Settings (WORKBOOK «Pantallas · Ajustes»; ATTENDANCE-F04), the old `erp-attendance-settings`:
// whether a personal device must share its location and be within a radius of the workplace to clock in,
// the radius, the workplace (typed, or read from this device with «Use my current location»; what fails is said
// under that button, and a denied location says where to allow it: the browser, or the device's settings inside
// the installed app) and after how many hours a forgotten day is flagged for review. The values come live
// (`attendance.settings.get`: the defaults until the business saves): a change saved elsewhere repaints every
// field the person has not touched. «Save» sends only what changed (`attendance.settings.update`); what the
// screen can judge it judges first and the server's 422 goes under each field. Whoever may not save reads them.
// The form is every settings page's (`useSettingsForm`, hub#867): a refusal says itself as a FormModal does,
// and the workplace's two coordinates are one value: changing either sends both and lifts both messages.
import { InlineFeedback, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, nativeBridge, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import { GeoError, type GeoErrorCode, getPosition } from '../lib/geo';
import type { Radius, SettingsOut } from '../operations';
import { attendanceTabs } from '../tabs';

const RADII: readonly Radius[] = [50, 100, 250, 500, 1000];
/** Six decimals of a degree: about 11 cm, more than any phone reads. */
const COORD_DECIMALS = 6;
const GEO_KEYS: Record<GeoErrorCode, string> = {
  denied: 'attendance.settings.locationDenied',
  unavailable: 'attendance.clock.locationUnavailable',
  timeout: 'attendance.clock.locationTimeout',
  unsupported: 'attendance.clock.locationUnsupported',
};

interface Form {
  require_location: boolean;
  geofence_radius_m: string;
  workplace_lat: string;
  workplace_lng: string;
  auto_close_after_hours: string;
}

const session = useSession();
const t = useT();
const canEdit = computed(() => session.can('attendance.manage_settings'));

const { data, status, error, refresh } = useLive('attendance.settings.get', {});
/** The form is every settings page's (`useSettingsForm`, hub#867); what is this page's is said below. */
const settingsForm = useSettingsForm(data, useCommand('attendance.settings.update'), {
  toForm,
  numbers: ['geofence_radius_m', 'auto_close_after_hours'],
  server: { workplace_lat: { value: coordinate }, workplace_lng: { value: coordinate } },
  together: [['workplace_lat', 'workplace_lng']],
  judge,
});
const { form, saved, pending, error: saveError, fieldErrors, showsError } = settingsForm;
const blocked = computed(() => blockingError(error.value));

const problem = ref('');
const accuracy = ref<number | null>(null);
const locating = ref(false);

const coord = (value: number | null): string => (value === null ? '' : String(value));

function toForm(settings: SettingsOut): Form {
  return {
    require_location: settings.require_location,
    geofence_radius_m: String(settings.geofence_radius_m),
    workplace_lat: coord(settings.workplace_lat),
    workplace_lng: coord(settings.workplace_lng),
    auto_close_after_hours: String(settings.auto_close_after_hours),
  };
}

/** A typed coordinate as the server knows it: a number, or none when it is empty. */
function coordinate(value: string): number | null {
  return value.trim() ? Number(value.trim()) : null;
}

/** The first thing the screen can tell is wrong, under its field, before sending (ATTENDANCE-F04 «Si falla»). */
function judge(now: Form): Partial<Record<keyof Form, string>> | null {
  const lat = coordinate(now.workplace_lat);
  const lng = coordinate(now.workplace_lng);
  const incomplete = t('attendance.settings.coordinatesIncomplete');
  if (lat === null && lng !== null) return { workplace_lat: incomplete };
  if (lat !== null && lng === null) return { workplace_lng: incomplete };
  if (lat !== null && !(Number.isFinite(lat) && Math.abs(lat) <= 90)) return { workplace_lat: t('attendance.settings.invalidLatitude') };
  if (lng !== null && !(Number.isFinite(lng) && Math.abs(lng) <= 180)) return { workplace_lng: t('attendance.settings.invalidLongitude') };
  const hours = now.auto_close_after_hours.trim();
  if (!/^\d+$/.test(hours) || Number(hours) < 1 || Number(hours) > 24) return { auto_close_after_hours: t('attendance.settings.invalidAutoClose') };
  return null;
}

/** A change also takes away what «Use my current location» last said. */
function set<K extends keyof Form>(field: K, value: Form[K]): void {
  if (!form.value) return;
  settingsForm.set(field, value);
  problem.value = '';
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

const workplaceMissing = computed(() => !!form.value?.require_location && (!form.value.workplace_lat.trim() || !form.value.workplace_lng.trim()));

/** Only whoever may change them saves (no one else has the button). */
async function save(): Promise<void> {
  if (canEdit.value) await settingsForm.save();
}

async function useMyLocation(): Promise<void> {
  if (locating.value || !canEdit.value) return;
  locating.value = true;
  problem.value = '';
  try {
    const position = await getPosition();
    set('workplace_lat', String(Number(position.lat.toFixed(COORD_DECIMALS))));
    set('workplace_lng', String(Number(position.lng.toFixed(COORD_DECIMALS))));
    accuracy.value = Math.round(position.accuracy_m);
  } catch (failure) {
    const code = failure instanceof GeoError ? failure.code : 'unavailable';
    // The installed app has no browser bar: there the location is allowed again in the device's settings.
    problem.value = code === 'denied' && nativeBridge() ? t('attendance.settings.locationDeniedInApp') : t(GEO_KEYS[code]);
  } finally {
    locating.value = false;
  }
}
</script>

<template>
  <AppPage
    :title="$t('attendance.title')"
    :tabs="attendanceTabs($t)"
    :tabs-label="$t('attendance.tabs.label')"
    content-layout="detail"
  >
    <PageNotices
      testid="attendance-settings"
      :status="status"
      :error="error"
    />
    <template v-if="!blocked">
      <InlineFeedback
        v-if="status === 'error' && !form"
        tone="danger"
        data-testid="attendance-settings-load-error"
        :heading="$t('attendance.settings.loadError')"
      >
        <ion-button
          size="small"
          fill="outline"
          data-testid="attendance-settings-retry"
          @click="refresh()"
        >
          {{ $t('attendance.retry') }}
        </ion-button>
      </InlineFeedback>
      <p
        v-else-if="!form"
        class="attendance-settings__loading"
        data-testid="attendance-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('attendance.loading') }}
      </p>
      <form
        v-else
        class="attendance-settings"
        data-testid="attendance-settings-form"
        @submit.prevent="save"
      >
        <header>
          <h2>{{ $t('attendance.settings.title') }}</h2>
          <p class="attendance-settings__muted">
            {{ $t('attendance.settings.intro') }}
          </p>
        </header>
        <InlineFeedback
          v-if="!canEdit"
          tone="info"
          icon="ion:lock-closed-outline"
          data-testid="attendance-settings-read-only"
        >
          {{ $t('attendance.settings.readOnly') }}
        </InlineFeedback>
        <InlineFeedback
          v-if="showsError"
          tone="danger"
          data-testid="attendance-settings-error"
        >
          {{ saveError?.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saved"
          tone="success"
          data-testid="attendance-settings-saved"
        >
          {{ $t('attendance.settings.saved') }}
        </InlineFeedback>
        <ion-toggle
          data-testid="attendance-settings-require_location"
          label-placement="start"
          justify="space-between"
          :disabled="!canEdit"
          :checked="form.require_location"
          @ion-change="set('require_location', !!$event.detail.checked)"
        >
          {{ $t('attendance.settings.requireLocation') }}
        </ion-toggle>
        <InlineFeedback
          tone="info"
          data-testid="attendance-settings-location-devices"
        >
          {{ $t('attendance.settings.locationDevices') }}
        </InlineFeedback>
        <ion-select
          data-testid="attendance-settings-geofence_radius_m"
          interface="popover"
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="$t('attendance.settings.radius')"
          :disabled="!canEdit"
          :value="form.geofence_radius_m"
          @ion-change="set('geofence_radius_m', text($event.detail.value))"
        >
          <ion-select-option
            v-for="radius in RADII"
            :key="radius"
            :value="String(radius)"
          >
            {{ $t('attendance.settings.radiusOption', { radius }) }}
          </ion-select-option>
        </ion-select>
        <section>
          <h3>{{ $t('attendance.settings.workplace') }}</h3>
          <div class="attendance-settings__pair">
            <ion-input
              data-testid="attendance-settings-workplace_lat"
              type="number"
              inputmode="decimal"
              min="-90"
              max="90"
              step="any"
              mode="md"
              fill="outline"
              label-placement="floating"
              :label="$t('attendance.settings.latitude')"
              :disabled="!canEdit"
              :value="form.workplace_lat"
              :error-text="fieldErrors.workplace_lat"
              :class="invalid(fieldErrors.workplace_lat)"
              @ion-input="set('workplace_lat', text($event.detail.value))"
            />
            <ion-input
              data-testid="attendance-settings-workplace_lng"
              type="number"
              inputmode="decimal"
              min="-180"
              max="180"
              step="any"
              mode="md"
              fill="outline"
              label-placement="floating"
              :label="$t('attendance.settings.longitude')"
              :disabled="!canEdit"
              :value="form.workplace_lng"
              :error-text="fieldErrors.workplace_lng"
              :class="invalid(fieldErrors.workplace_lng)"
              @ion-input="set('workplace_lng', text($event.detail.value))"
            />
          </div>
          <div class="attendance-settings__locate">
            <ion-button
              v-if="canEdit"
              fill="outline"
              data-testid="attendance-settings-use-location"
              :disabled="locating"
              @click="useMyLocation"
            >
              <ion-spinner
                v-if="locating"
                slot="start"
                name="crescent"
              />
              <HubIcon
                v-else
                slot="start"
                name="ion:globe-outline"
              />
              {{ locating ? $t('attendance.settings.locating') : $t('attendance.settings.useMyLocation') }}
            </ion-button>
            <span
              v-if="accuracy !== null"
              class="attendance-settings__muted"
              data-testid="attendance-settings-accuracy"
            >{{ $t('attendance.settings.accuracy', { accuracy }) }}</span>
          </div>
          <!-- Under the button that read it: on a phone the banner up top is out of sight from here. -->
          <InlineFeedback
            v-if="problem"
            class="attendance-settings__location-error"
            tone="danger"
            data-testid="attendance-settings-location-error"
          >
            {{ problem }}
          </InlineFeedback>
        </section>
        <InlineFeedback
          v-if="workplaceMissing"
          tone="warning"
          data-testid="attendance-settings-workplace-missing"
        >
          {{ $t('attendance.settings.workplaceMissing') }}
        </InlineFeedback>
        <ion-input
          data-testid="attendance-settings-auto_close_after_hours"
          type="number"
          inputmode="numeric"
          min="1"
          max="24"
          step="1"
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="$t('attendance.settings.autoClose')"
          :helper-text="$t('attendance.settings.autoCloseHelp')"
          :disabled="!canEdit"
          :value="form.auto_close_after_hours"
          :error-text="fieldErrors.auto_close_after_hours"
          :class="invalid(fieldErrors.auto_close_after_hours)"
          @ion-input="set('auto_close_after_hours', text($event.detail.value))"
        />
        <div
          v-if="canEdit"
          class="attendance-settings__actions"
        >
          <ion-button
            data-testid="attendance-settings-save"
            :disabled="pending"
            @click="save"
          >
            <ion-spinner
              v-if="pending"
              slot="start"
              name="crescent"
            />
            <HubIcon
              v-else
              slot="start"
              name="lucide:save"
            />
            {{ $t('attendance.settings.save') }}
          </ion-button>
        </div>
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.attendance-settings {
  display: grid;
  gap: 1.1rem;
}
/* The toggle's long label wraps: on one line it pushed the whole form past a phone's edge. */
.attendance-settings ion-toggle::part(label) {
  white-space: normal;
}
.attendance-settings header h2 {
  margin: 0;
  font-size: 1.15rem;
}
.attendance-settings h3 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  font-weight: 600;
}
.attendance-settings__muted {
  margin: 4px 0 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.9rem;
}
.attendance-settings__pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 14px;
}
.attendance-settings__locate {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}
.attendance-settings__location-error {
  margin-top: 12px;
}
.attendance-settings__actions {
  display: flex;
  justify-content: flex-end;
}
.attendance-settings__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
