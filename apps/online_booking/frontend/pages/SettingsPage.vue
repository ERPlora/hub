<script setup lang="ts">
// Online booking → Settings (WORKBOOK «Ajustes»; ONLINE_BOOKING-F07), only for whoever may save them. The values
// come live (`online_booking.settings.get`: the factory ones until the business saves, and the diary's booking
// rules); a change saved elsewhere repaints every field the person has not touched, and «Save» sends only the
// fields touched and changed (`online_booking.settings.update`: the page's and the diary's, all or nothing).
// Below, the offered services with their «Online booking» switch, saved at once in Services.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner, IonTextarea, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import type { SettingsIn, SettingsOut } from '../operations';
import { onlineBookingTabs } from '../tabs';

const TEXTS = ['page_title', 'primary_color', 'logo_url'] as const;
const LONG_TEXTS = ['welcome_message', 'confirmation_message', 'cancellation_policy'] as const;
const PAGE_SWITCHES = ['is_enabled', 'require_email', 'allow_staff_selection', 'allow_notes'] as const;
const PAGE_NUMBERS = ['max_upcoming_per_customer'] as const;
const RULE_NUMBERS = ['min_booking_notice', 'max_advance_booking', 'slot_interval', 'cancellation_notice_hours'] as const;
const RULE_SWITCHES = ['auto_confirm_online', 'allow_customer_cancellation'] as const;
const NUMBERS = [...PAGE_NUMBERS, ...RULE_NUMBERS] as const;
const SWITCHES = [...PAGE_SWITCHES, ...RULE_SWITCHES] as const;
const STRINGS = [...TEXTS, ...LONG_TEXTS] as const;
/** The most services the section lists at once (the server's cap on a page). */
const SERVICE_WINDOW = 100;

type Form = Record<(typeof STRINGS)[number] | (typeof NUMBERS)[number], string> & Record<(typeof SWITCHES)[number], boolean>;
type Field = keyof Form;

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('online_booking.manage_settings'));

const { data, status, error } = useLive('online_booking.settings.get', {});
const { run, pending, error: saveError } = useCommand('online_booking.settings.update');

const form = ref<Form | null>(null);
const original = ref<Form | null>(null);
const touched = ref<ReadonlySet<Field>>(new Set());
const saved = ref(false);

function toForm(settings: SettingsOut): Form {
  return {
    ...(Object.fromEntries(STRINGS.map((field) => [field, settings[field]])) as Record<(typeof STRINGS)[number], string>),
    ...(Object.fromEntries(NUMBERS.map((field) => [field, String(settings[field])])) as Record<(typeof NUMBERS)[number], string>),
    ...(Object.fromEntries(SWITCHES.map((field) => [field, settings[field]])) as Record<(typeof SWITCHES)[number], boolean>),
  };
}

const changes = computed<SettingsIn>(() => {
  const now = form.value;
  const was = original.value;
  if (!now || !was) return {};
  const out: Record<string, unknown> = {};
  for (const key of touched.value) {
    const value = now[key];
    const text = typeof value === 'string' ? value.trim() : value;
    if (text === was[key]) continue;
    out[key] = (NUMBERS as readonly string[]).includes(key) && typeof text === 'string' && /^\d+$/.test(text) ? Number(text) : text;
  }
  return out as SettingsIn;
});
const dirty = computed(() => Object.keys(changes.value).length > 0);

watch(
  data,
  (settings) => {
    if (!settings) return;
    const fresh = toForm(settings);
    const current = form.value;
    original.value = fresh;
    form.value = current
      ? (Object.fromEntries(
          (Object.keys(fresh) as Field[]).map((key) => [key, touched.value.has(key) ? current[key] : fresh[key]]),
        ) as Form)
      : { ...fresh };
  },
  { immediate: true },
);

function set<K extends Field>(field: K, value: Form[K]): void {
  if (!form.value) return;
  form.value = { ...form.value, [field]: value };
  touched.value = new Set([...touched.value, field]);
  saved.value = false;
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const fieldErrors = computed<Readonly<Record<string, string>>>(() => saveError.value?.fields ?? {});
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function save(): Promise<void> {
  if (!dirty.value || pending.value) return;
  try {
    const answer = await run(changes.value);
    original.value = toForm(answer);
    form.value = toForm(answer);
    touched.value = new Set();
    saved.value = true;
  } catch {
    saved.value = false; // The page paints the error; what was typed stays.
  }
}

// Services booked online (Services' own list and switch).
const serviceSearch = ref('');
const services = useLive('service.service.list', () => ({
  limit: SERVICE_WINDOW,
  ...(serviceSearch.value.trim() ? { search: serviceSearch.value.trim() } : {}),
}));
const updateService = useCommand('service.service.update');
const serviceError = ref<ApiError | null>(null);

async function toggleService(event: Event, id: string, online: boolean): Promise<void> {
  serviceError.value = null;
  try {
    await updateService.run({ id, allow_online_booking: online });
  } catch {
    serviceError.value = updateService.error.value;
    // The switch keeps its own state: back to what Services still says.
    (event.target as HTMLIonToggleElement).checked = !online;
  }
}
</script>

<template>
  <AppPage
    :title="$t('online_booking.title')"
    :tabs="onlineBookingTabs(t, { settings: canManage })"
    :tabs-label="$t('online_booking.tabs.label')"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canManage"
      tone="warning"
      data-testid="ob-settings-forbidden"
      :heading="$t('online_booking.noPermission')"
    />
    <template v-else>
      <PageNotices
        testid="ob-settings"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="status === 'error' && error && error.code !== 'app_inactive' && error.code !== 'permission_denied'"
        tone="danger"
        data-testid="ob-settings-load-error"
        :heading="$t('online_booking.settings.loadError')"
      >
        {{ error.message }}
      </InlineFeedback>
      <p
        v-if="!form && status !== 'error'"
        class="ob-settings__loading"
        data-testid="ob-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('online_booking.settings.loading') }}
      </p>
      <form
        v-else-if="form"
        class="ob-settings"
        data-testid="ob-settings"
        @submit.prevent="save"
      >
        <h2 class="ob-settings__title">
          {{ $t('online_booking.settings.title') }}
        </h2>

        <h3 class="ob-settings__section">
          {{ $t('online_booking.settings.sections.page') }}
        </h3>
        <ion-toggle
          data-testid="ob-settings-is_enabled"
          label-placement="end"
          justify="start"
          :checked="form.is_enabled"
          @ion-change="set('is_enabled', $event.detail.checked)"
        >
          {{ t('online_booking.settings.fields.is_enabled') }}
        </ion-toggle>
        <ion-input
          v-for="field in TEXTS"
          :key="field"
          :data-testid="`ob-settings-${field}`"
          :value="form[field]"
          :label="t(`online_booking.settings.fields.${field}`)"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
        />
        <ion-textarea
          v-for="field in LONG_TEXTS"
          :key="field"
          :data-testid="`ob-settings-${field}`"
          :value="form[field]"
          :label="t(`online_booking.settings.fields.${field}`)"
          label-placement="floating"
          fill="outline"
          mode="md"
          auto-grow
          :maxlength="2000"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
        />
        <ion-input
          v-for="field in PAGE_NUMBERS"
          :key="field"
          :data-testid="`ob-settings-${field}`"
          type="number"
          inputmode="numeric"
          min="1"
          max="50"
          :value="form[field]"
          :label="t(`online_booking.settings.fields.${field}`)"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
        />
        <ion-toggle
          v-for="field in PAGE_SWITCHES.filter((name) => name !== 'is_enabled')"
          :key="field"
          :data-testid="`ob-settings-${field}`"
          label-placement="end"
          justify="start"
          :checked="form[field]"
          @ion-change="set(field, $event.detail.checked)"
        >
          {{ t(`online_booking.settings.fields.${field}`) }}
        </ion-toggle>

        <h3 class="ob-settings__section">
          {{ $t('online_booking.settings.sections.rules') }}
        </h3>
        <p class="ob-settings__help">
          {{ $t('online_booking.settings.sections.rulesHelp') }}
        </p>
        <ion-input
          v-for="field in RULE_NUMBERS"
          :key="field"
          :data-testid="`ob-settings-${field}`"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form[field]"
          :label="t(`online_booking.settings.fields.${field}`)"
          :helper-text="field === 'max_advance_booking' ? t('online_booking.settings.fields.max_advance_booking_help') : undefined"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
        />
        <ion-toggle
          v-for="field in RULE_SWITCHES"
          :key="field"
          :data-testid="`ob-settings-${field}`"
          label-placement="end"
          justify="start"
          :checked="form[field]"
          @ion-change="set(field, $event.detail.checked)"
        >
          {{ t(`online_booking.settings.fields.${field}`) }}
        </ion-toggle>

        <InlineFeedback
          v-if="saveError"
          tone="danger"
          data-testid="ob-settings-save-error"
          :heading="$t('online_booking.settings.saveError')"
        >
          {{ saveError.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saved"
          tone="success"
          data-testid="ob-settings-saved"
        >
          {{ $t('online_booking.settings.saved') }}
        </InlineFeedback>
        <ion-button
          type="submit"
          data-testid="ob-settings-save"
          :disabled="!dirty || pending"
          @click="save"
        >
          {{ $t('online_booking.settings.save') }}
        </ion-button>
      </form>

      <section
        v-if="form"
        class="ob-settings"
        data-testid="ob-settings-services"
      >
        <h3 class="ob-settings__section">
          {{ $t('online_booking.settings.sections.services') }}
        </h3>
        <p class="ob-settings__help">
          {{ $t('online_booking.settings.sections.servicesHelp') }}
        </p>
        <ion-input
          data-testid="ob-settings-services-search"
          type="search"
          :value="serviceSearch"
          :label="$t('online_booking.settings.services.search')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :debounce="300"
          @ion-input="serviceSearch = text($event.detail.value)"
        />
        <InlineFeedback
          v-if="serviceError"
          tone="danger"
          dismissible
          data-testid="ob-settings-services-error"
          :heading="$t('online_booking.settings.services.saveError')"
          @dismiss="serviceError = null"
        >
          {{ serviceError.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="services.status.value === 'error'"
          tone="danger"
          data-testid="ob-settings-services-load-error"
          :heading="$t('online_booking.settings.services.loadError')"
        >
          {{ services.error.value?.message }}
        </InlineFeedback>
        <p
          v-else-if="!services.data.value"
          class="ob-settings__loading"
        >
          <ion-spinner name="crescent" />
        </p>
        <EmptyState
          v-else-if="services.data.value.rows.length === 0"
          data-testid="ob-settings-services-empty"
          icon="pricetag-outline"
          :heading="$t('online_booking.settings.services.empty')"
        />
        <template v-else>
          <ion-toggle
            v-for="item in services.data.value.rows"
            :key="item.id"
            :data-testid="`ob-settings-service-${item.id}`"
            label-placement="end"
            justify="start"
            :checked="item.allow_online_booking"
            :disabled="updateService.pending.value"
            @ion-change="toggleService($event, item.id, $event.detail.checked)"
          >
            {{ item.name }}
            <small
              v-if="!item.is_bookable"
              class="ob-settings__note"
            >{{ $t('online_booking.settings.services.notBookable') }}</small>
          </ion-toggle>
          <p
            v-if="services.data.value.total > services.data.value.rows.length"
            class="ob-settings__help"
            data-testid="ob-settings-services-more"
          >
            {{ $t('online_booking.settings.services.more', { shown: services.data.value.rows.length, total: services.data.value.total }) }}
          </p>
        </template>
      </section>
    </template>
  </AppPage>
</template>

<style scoped>
.ob-settings {
  display: grid;
  /* The column never grows past the page: a one-line switch label widened it to 409 px on a 375 px phone. */
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  max-width: 560px;
  margin-bottom: 24px;
}
/* The switch's long label wraps (ion-toggle keeps it on one line): the same defect Attendance had (hub#94). */
.ob-settings ion-toggle::part(label) {
  white-space: normal;
}
.ob-settings__title {
  font-size: 1.1rem;
  margin: 0;
}
.ob-settings__section {
  font-size: 1rem;
  margin: 8px 0 0;
}
.ob-settings__help {
  margin: 0;
  font-size: 0.85rem;
  opacity: 0.75;
}
.ob-settings__note {
  display: block;
  font-size: 0.75rem;
  opacity: 0.7;
}
.ob-settings__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
