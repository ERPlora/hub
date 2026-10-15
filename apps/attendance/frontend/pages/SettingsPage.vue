<script setup lang="ts">
// Time clock → Settings (WORKBOOK «Pantallas · Ajustes»; ATTENDANCE-F04), the old `erp-attendance-settings`:
// whether a personal device must share its location and be within a radius of the workplace to clock in,
// the radius, the workplace (typed, or read from this device with «Use my current location») and after how
// many hours a forgotten day is flagged for review. The values come live (`attendance.settings.get`: the
// defaults until the business saves): a change saved elsewhere repaints every field the person has not
// touched. «Save» sends only what changed (`attendance.settings.update`); what the screen can judge it
// judges first and the server's 422 goes under each field. Whoever may not save reads them.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import { deviceModesKnown } from '../lib/device';
import { GeoError, type GeoErrorCode, getPosition } from '../lib/geo';
import type { Radius, SettingsIn, SettingsOut } from '../operations';
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
const { run, pending, error: saveError } = useCommand('attendance.settings.update');
const blocked = computed(() => blockingError(error.value));

const form = ref<Form | null>(null);
const original = ref<Form | null>(null);
const touched = ref<ReadonlySet<keyof Form>>(new Set());
const saved = ref(false);
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

// What the server says repaints every field the person has not touched.
watch(
  data,
  (settings) => {
    if (!settings) return;
    const fresh = toForm(settings);
    const current = form.value;
    original.value = fresh;
    form.value = current
      ? (Object.fromEntries(
          (Object.keys(fresh) as (keyof Form)[]).map((key) => [key, touched.value.has(key) ? current[key] : fresh[key]]),
        ) as unknown as Form)
      : { ...fresh };
  },
  { immediate: true },
);

function set<K extends keyof Form>(field: K, value: Form[K]): void {
  if (!form.value) return;
  form.value = { ...form.value, [field]: value };
  touched.value = new Set([...touched.value, field]);
  saved.value = false;
  problem.value = '';
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const fieldErrors = computed<Readonly<Record<string, string>>>(() => saveError.value?.fields ?? {});
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

const workplaceMissing = computed(() => !!form.value?.require_location && (!form.value.workplace_lat.trim() || !form.value.workplace_lng.trim()));

/** The changes to send, or the key of the first thing wrong with the form. */
function changes(): { ok: true; value: SettingsIn } | { ok: false; key: string } {
  const now = form.value!;
  const was = original.value!;
  const lat = now.workplace_lat.trim();
  const lng = now.workplace_lng.trim();
  if (!!lat !== !!lng) return { ok: false, key: 'attendance.settings.coordinatesIncomplete' };
  const latN = lat ? Number(lat) : null;
  const lngN = lng ? Number(lng) : null;
  if (latN !== null && !(Number.isFinite(latN) && Math.abs(latN) <= 90)) return { ok: false, key: 'attendance.settings.invalidLatitude' };
  if (lngN !== null && !(Number.isFinite(lngN) && Math.abs(lngN) <= 180)) return { ok: false, key: 'attendance.settings.invalidLongitude' };
  const hoursText = now.auto_close_after_hours.trim();
  const hours = Number(hoursText);
  if (!/^\d+$/.test(hoursText) || hours < 1 || hours > 24) return { ok: false, key: 'attendance.settings.invalidAutoClose' };
  const out: SettingsIn = {};
  if (now.require_location !== was.require_location) out.require_location = now.require_location;
  if (now.geofence_radius_m !== was.geofence_radius_m) out.geofence_radius_m = Number(now.geofence_radius_m) as Radius;
  if (lat !== was.workplace_lat || lng !== was.workplace_lng) {
    out.workplace_lat = latN;
    out.workplace_lng = lngN;
  }
  if (hoursText !== was.auto_close_after_hours) out.auto_close_after_hours = hours;
  return { ok: true, value: out };
}

async function save(): Promise<void> {
  if (!canEdit.value || !form.value || pending.value) return;
  saved.value = false;
  const next = changes();
  if (!next.ok) {
    problem.value = t(next.key);
    return;
  }
  if (Object.keys(next.value).length === 0) {
    saved.value = true;
    return;
  }
  try {
    const answer = await run(next.value);
    original.value = toForm(answer);
    form.value = toForm(answer);
    touched.value = new Set();
    saved.value = true;
  } catch {
    saved.value = false; // The page paints the error; what was typed stays.
  }
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
    problem.value = t(GEO_KEYS[code]);
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
          v-if="problem || saveError"
          tone="danger"
          data-testid="attendance-settings-error"
        >
          {{ problem || saveError?.message }}
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
          :disabled="!canEdit || !deviceModesKnown()"
          :checked="form.require_location"
          @ion-change="set('require_location', !!$event.detail.checked)"
        >
          {{ $t('attendance.settings.requireLocation') }}
        </ion-toggle>
        <InlineFeedback
          v-if="!deviceModesKnown()"
          tone="info"
          data-testid="attendance-settings-location-pending"
        >
          {{ $t('attendance.settings.locationPending') }}
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
