<script setup lang="ts">
// Time clock → Clock in (WORKBOOK «Pantallas · Fichar»; ATTENDANCE-F01, F02, F03), the old
// `erp-attendance-clock`: «Hello, <name>» and «It is <time>», the state of the day, the time since the
// clock-in (running), the one button of the moment — «Clock in», or «Start break»/«End break» and «Clock
// out» —, «Today» (Worked and Breaks, running) and «Recent days» (the last ten). Everything comes live
// (`attendance.record.current`, `attendance.settings.get`) and runs on from the server's figures with
// the page's clock. A command answers with the server's time or the server's refusal; the stream brings
// the new state. From a personal device, when the business asks for it, the position goes with the
// clock-in (the Hub measures the distance and decides); clocking out never waits for it.
import { EmptyState, StatusPill, type StatusPillTone } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useServerNow } from '../composables/useServerNow';
import { useLocale, useT } from '../composables/useT';
import { deviceMode } from '../lib/device';
import { GeoError, type GeoErrorCode, getPosition } from '../lib/geo';
import { formatDay, formatHm, formatHms, formatTime, liveSeconds } from '../lib/time';
import type { PositionIn, RecordOut, RecordStatus } from '../operations';
import { attendanceTabs } from '../tabs';

type Busy = '' | 'in' | 'out' | 'break';
type Notice = { kind: 'success' | 'error' | 'info'; text: string } | null;

const TONE: Record<RecordStatus, StatusPillTone> = { open: 'success', closed: 'neutral', needs_review: 'warning' };
const GEO_KEYS: Record<GeoErrorCode, string> = {
  denied: 'attendance.clock.locationDenied',
  unavailable: 'attendance.clock.locationUnavailable',
  timeout: 'attendance.clock.locationTimeout',
  unsupported: 'attendance.clock.locationUnsupported',
};

const t = useT();
const locale = useLocale();

const { data, status, error, refresh } = useLive('attendance.record.current', {});
// The server's clock (its `as_of`), ticking every second: never the device's own.
const now = useServerNow(() => data.value?.as_of, 1000);
const { data: settings } = useLive('attendance.settings.get', {});
const clockInCommand = useCommand('attendance.record.clock_in');
const clockOutCommand = useCommand('attendance.record.clock_out');
const breakStartCommand = useCommand('attendance.break.start');
const breakEndCommand = useCommand('attendance.break.end');

const busy = ref<Busy>('');
const notice = ref<Notice>(null);
const distance = ref<number | null>(null);

const blocked = computed(() => blockingError(error.value));
/** The open day as the last command answered it, until the stream brings the new state (a moment
 *  later): the buttons follow the server's answer at once, so a second tap never hits a stale one. */
const answered = ref<{ open: RecordOut | null } | null>(null);
watch(data, () => {
  answered.value = null;
});
const openDay = computed(() => (answered.value ? answered.value.open : (data.value?.open ?? null)));
const onBreak = computed(() => !!openDay.value?.break_started_at);
const locationChecked = computed(() => !!settings.value?.require_location && deviceMode() === 'personal');
const elapsed = computed(() => (openDay.value ? Math.max(0, Math.floor((now.value - Date.parse(openDay.value.clock_in_at)) / 1000)) : 0));
const worked = computed(() => {
  const day = data.value;
  return day ? liveSeconds(day.today.worked_seconds, day.as_of, now.value, day.today.running === 'work') : 0;
});
const breaks = computed(() => {
  const day = data.value;
  return day ? liveSeconds(day.today.break_seconds, day.as_of, now.value, day.today.running === 'break') : 0;
});
const nowText = computed(() => formatTime(new Date(now.value).toISOString()));

function geoText(failure: unknown): string {
  const code = failure instanceof GeoError ? failure.code : 'unavailable';
  return t(GEO_KEYS[code]);
}

/** Runs a command; tells the server's time of what it did, or the server's refusal. */
async function send(run: () => Promise<RecordOut>, doneKey: string, at: (day: RecordOut) => string | null): Promise<RecordOut | null> {
  try {
    const day = await run();
    notice.value = { kind: 'success', text: t(doneKey, { time: formatTime(at(day)) }) };
    return day;
  } catch (failure) {
    notice.value = { kind: 'error', text: (failure as ApiError).message || t('attendance.clock.loadError') };
    // The typical refusal means the screen was out of date (the day changed on another device).
    refresh();
    return null;
  }
}

async function clockIn(): Promise<void> {
  if (busy.value) return;
  busy.value = 'in';
  notice.value = null;
  distance.value = null;
  try {
    let where: PositionIn = {};
    if (locationChecked.value) {
      if (!settings.value?.workplace_set) {
        notice.value = { kind: 'error', text: t('attendance.clock.workplaceNotSet') };
        return;
      }
      notice.value = { kind: 'info', text: t('attendance.clock.locating') };
      try {
        const position = await getPosition();
        where = { lat: position.lat, lng: position.lng, accuracy_m: position.accuracy_m };
      } catch (failure) {
        notice.value = { kind: 'error', text: geoText(failure) };
        return;
      }
    }
    const day = await send(() => clockInCommand.run(where), 'attendance.clock.clockedIn', (d) => d.clock_in_at);
    if (day) answered.value = { open: day };
    if (day?.in_distance_m != null) distance.value = Math.round(day.in_distance_m);
  } finally {
    busy.value = '';
  }
}

/** Clocking out NEVER blocks: the position goes when it can be read, and that is all. */
async function clockOut(): Promise<void> {
  if (busy.value) return;
  busy.value = 'out';
  notice.value = null;
  try {
    let where: PositionIn = {};
    if (locationChecked.value) {
      notice.value = { kind: 'info', text: t('attendance.clock.locating') };
      try {
        const position = await getPosition();
        where = { lat: position.lat, lng: position.lng, accuracy_m: position.accuracy_m };
      } catch {
        where = {};
      }
    }
    const day = await send(() => clockOutCommand.run(where), 'attendance.clock.clockedOut', (d) => d.clock_out_at);
    if (day) answered.value = { open: null };
    if (day?.out_distance_m != null) distance.value = Math.round(day.out_distance_m);
  } finally {
    busy.value = '';
  }
}

async function toggleBreak(): Promise<void> {
  if (busy.value || !openDay.value) return;
  busy.value = 'break';
  notice.value = null;
  try {
    const day = onBreak.value
      ? await send(() => breakEndCommand.run({}), 'attendance.clock.breakEnded', (d) => d.as_of)
      : await send(() => breakStartCommand.run({}), 'attendance.clock.breakStarted', (d) => d.break_started_at);
    if (day) answered.value = { open: day };
  } finally {
    busy.value = '';
  }
}

function endOf(day: RecordOut): string {
  if (day.clock_out_at) return formatTime(day.clock_out_at);
  return day.status === 'open' ? '…' : t('attendance.clock.noClockOut');
}
</script>

<template>
  <AppPage
    :title="$t('attendance.title')"
    :tabs="attendanceTabs($t)"
    :tabs-label="$t('attendance.tabs.label')"
  >
    <PageNotices
      testid="attendance-clock"
      :status="status"
      :error="error"
    />
    <template v-if="!blocked">
      <div
        v-if="status === 'error' && !data"
        class="attendance-clock__center"
        role="alert"
        data-testid="attendance-clock-error"
      >
        <HubIcon
          class="attendance-clock__big-icon"
          name="ion:cloud-offline-outline"
        />
        <p>{{ $t('attendance.clock.loadError') }}</p>
        <ion-button
          data-testid="attendance-clock-retry"
          @click="refresh()"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
          />
          {{ $t('attendance.retry') }}
        </ion-button>
      </div>
      <div
        v-else-if="!data"
        class="attendance-clock__center"
        data-testid="attendance-clock-loading"
      >
        <ion-spinner name="crescent" />
        <span class="attendance-clock__muted">{{ $t('attendance.loading') }}</span>
      </div>
      <EmptyState
        v-else-if="!data.member"
        data-testid="attendance-clock-unlinked"
        icon="person-outline"
        :heading="$t('attendance.clock.unlinked.title')"
        :message="$t('attendance.clock.unlinked.message')"
      />
      <div
        v-else
        class="attendance-clock"
      >
        <section class="attendance-clock__card attendance-clock__main">
          <header>
            <h2 data-testid="attendance-clock-greeting">
              {{ $t('attendance.clock.greeting', { name: data.member.name }) }}
            </h2>
            <p
              class="attendance-clock__muted"
              data-testid="attendance-clock-now"
            >
              {{ $t('attendance.clock.now', { time: nowText }) }}
            </p>
          </header>
          <p
            class="attendance-clock__status"
            data-testid="attendance-clock-status"
          >
            <template v-if="!openDay">
              {{ $t('attendance.clock.statusOut') }}
            </template>
            <template v-else-if="onBreak">
              {{ $t('attendance.clock.statusOnBreak', { time: formatTime(openDay.break_started_at) }) }}
            </template>
            <template v-else>
              {{ $t('attendance.clock.statusIn', { time: formatTime(openDay.clock_in_at) }) }}
            </template>
          </p>
          <div v-if="openDay">
            <div class="attendance-clock__muted">
              {{ $t('attendance.clock.elapsed') }}
            </div>
            <div
              class="attendance-clock__timer"
              data-testid="attendance-clock-timer"
            >
              {{ formatHms(elapsed) }}
            </div>
          </div>
          <div class="attendance-clock__actions">
            <template v-if="openDay">
              <ion-button
                v-if="onBreak"
                expand="block"
                data-testid="attendance-break-end"
                :disabled="busy !== ''"
                @click="toggleBreak"
              >
                <HubIcon
                  slot="start"
                  name="ion:arrow-undo-outline"
                />
                {{ $t('attendance.clock.breakEnd') }}
              </ion-button>
              <ion-button
                v-else
                expand="block"
                fill="outline"
                data-testid="attendance-break-start"
                :disabled="busy !== ''"
                @click="toggleBreak"
              >
                <HubIcon
                  slot="start"
                  name="ion:time-outline"
                />
                {{ $t('attendance.clock.breakStart') }}
              </ion-button>
              <ion-button
                expand="block"
                color="danger"
                class="attendance-clock__primary"
                data-testid="attendance-clock-out"
                :disabled="busy !== ''"
                @click="clockOut"
              >
                <ion-spinner
                  v-if="busy === 'out'"
                  slot="start"
                  name="crescent"
                />
                <HubIcon
                  v-else
                  slot="start"
                  name="ion:log-out-outline"
                />
                {{ $t('attendance.clock.clockOut') }}
              </ion-button>
            </template>
            <ion-button
              v-else
              expand="block"
              color="success"
              class="attendance-clock__primary"
              data-testid="attendance-clock-in"
              :disabled="busy !== ''"
              @click="clockIn"
            >
              <ion-spinner
                v-if="busy === 'in'"
                slot="start"
                name="crescent"
              />
              <HubIcon
                v-else
                slot="start"
                name="ion:log-in-outline"
              />
              {{ $t('attendance.clock.clockIn') }}
            </ion-button>
          </div>
          <p
            v-if="locationChecked"
            class="attendance-clock__note"
            data-testid="attendance-clock-location-note"
          >
            <HubIcon name="ion:information-circle-outline" />
            {{ $t('attendance.clock.locationRequired') }}
          </p>
          <p
            v-if="distance !== null"
            class="attendance-clock__note"
            data-testid="attendance-clock-distance"
          >
            {{ $t('attendance.clock.distance', { distance }) }}
          </p>
          <p
            v-if="notice"
            :class="['attendance-clock__message', `attendance-clock__message--${notice.kind}`]"
            :role="notice.kind === 'error' ? 'alert' : 'status'"
            data-testid="attendance-clock-message"
          >
            {{ notice.text }}
          </p>
        </section>
        <div class="attendance-clock__side">
          <section class="attendance-clock__card">
            <h3>{{ $t('attendance.clock.today') }}</h3>
            <div class="attendance-clock__stats">
              <div
                class="attendance-clock__stat"
                data-testid="attendance-clock-today-worked"
              >
                <div class="attendance-clock__label">
                  {{ $t('attendance.clock.workedToday') }}
                </div>
                <div class="attendance-clock__value">
                  {{ formatHm(worked) }}
                </div>
              </div>
              <div
                class="attendance-clock__stat"
                data-testid="attendance-clock-today-breaks"
              >
                <div class="attendance-clock__label">
                  {{ $t('attendance.clock.breaksToday') }}
                </div>
                <div class="attendance-clock__value">
                  {{ formatHm(breaks) }}
                </div>
              </div>
            </div>
          </section>
          <section class="attendance-clock__card">
            <h3>{{ $t('attendance.clock.recent') }}</h3>
            <ul
              v-if="data.recent.length"
              class="attendance-clock__recent"
              data-testid="attendance-clock-recent"
            >
              <li
                v-for="day in data.recent"
                :key="day.id"
                class="attendance-clock__day"
                data-testid="attendance-clock-recent-row"
              >
                <div class="attendance-clock__day-text">
                  <strong>{{ formatDay(day.work_date, locale) }}</strong>
                  <span>{{ formatTime(day.clock_in_at) }} – {{ endOf(day) }}</span>
                </div>
                <div class="attendance-clock__day-end">
                  <span v-if="day.clock_out_at && day.worked_seconds !== null">{{ formatHm(day.worked_seconds) }}</span>
                  <StatusPill
                    size="sm"
                    :tone="TONE[day.status]"
                    :label="t(`attendance.status.${day.status}`)"
                  />
                </div>
              </li>
            </ul>
            <p
              v-else
              class="attendance-clock__empty"
              data-testid="attendance-clock-empty"
            >
              {{ $t('attendance.clock.empty') }}
            </p>
          </section>
        </div>
      </div>
    </template>
  </AppPage>
</template>

<style scoped>
.attendance-clock {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(0, 1fr);
  max-width: 1100px;
  margin: 0 auto;
  container-type: inline-size;
}
@media (min-width: 900px) {
  .attendance-clock {
    grid-template-columns: minmax(320px, 5fr) minmax(0, 6fr);
    align-items: start;
  }
}
.attendance-clock__card {
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.12));
  border-radius: 16px;
  padding: 20px;
}
.attendance-clock__main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  text-align: center;
}
.attendance-clock__main h2 {
  margin: 0;
  font-size: 1.25rem;
}
.attendance-clock__muted {
  margin: 4px 0 0;
  color: var(--ion-color-medium, #6b6b6b);
  font-size: 0.95rem;
}
.attendance-clock__status {
  margin: 8px 0 0;
  font-weight: 600;
  font-size: 1.05rem;
}
.attendance-clock__timer {
  font-size: clamp(2.25rem, 9cqi, 3.25rem);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.attendance-clock__actions {
  display: grid;
  gap: 10px;
}
.attendance-clock__actions ion-button {
  margin: 0;
  min-height: 56px;
  font-size: 1.05rem;
}
.attendance-clock__actions ion-button.attendance-clock__primary {
  min-height: 72px;
  font-size: 1.2rem;
}
.attendance-clock__note {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  margin: 0;
  font-size: 0.9rem;
  color: var(--ion-color-medium, #6b6b6b);
}
.attendance-clock__message {
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  font-weight: 600;
  text-align: left;
}
.attendance-clock__message--error {
  color: var(--ion-color-danger, #c5000f);
  background: color-mix(in srgb, var(--ion-color-danger, #c5000f) 10%, transparent);
}
.attendance-clock__message--success {
  color: var(--ion-color-success-shade, #1f7a3a);
  background: color-mix(in srgb, var(--ion-color-success, #2dd36f) 12%, transparent);
}
.attendance-clock__message--info {
  color: var(--ion-color-medium-shade, #555);
  background: color-mix(in srgb, var(--ion-color-medium, #92949c) 12%, transparent);
}
.attendance-clock__side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.attendance-clock__side h3 {
  margin: 0 0 12px;
  font-size: 1.05rem;
}
.attendance-clock__stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.attendance-clock__stat {
  border-radius: 12px;
  padding: 12px;
  background: color-mix(in srgb, var(--ion-color-primary, #3880ff) 7%, transparent);
}
.attendance-clock__label {
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b6b6b);
}
.attendance-clock__value {
  font-size: 1.6rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.attendance-clock__recent {
  list-style: none;
  margin: 0;
  padding: 0;
}
.attendance-clock__day {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
}
.attendance-clock__day-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-variant-numeric: tabular-nums;
}
.attendance-clock__day-end {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-variant-numeric: tabular-nums;
}
.attendance-clock__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 16px;
  text-align: center;
}
.attendance-clock__big-icon {
  font-size: 40px;
}
.attendance-clock__empty {
  margin: 0;
  padding: 16px 0;
  text-align: center;
  color: var(--ion-color-medium, #6b6b6b);
}
</style>
