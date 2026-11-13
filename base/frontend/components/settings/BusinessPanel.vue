<script setup lang="ts">
// Settings › Business: the business as erplora.com registered it, read only because erplora.com owns it and pushes
// every change. «Change on erplora.com» leaves the Hub by `openExternalLink` (the installed app opens nothing on a
// `_blank` link) and is never offered in the Google Play copy (`managementOffered`).
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon, openExternalLink, useSession } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, ref } from 'vue';

import { useBaseI18n } from '../../lib/i18n';
import { managementOffered } from '../../lib/management';
import SettingsRow from './SettingsRow.vue';

/** How often the time of the business's zone moves on while the screen is open. */
const CLOCK_TICK_MS = 30_000;

const { t, locale } = useBaseI18n();
const session = useSession();
const { data, status, refresh } = useLive('base.business.get', {});

const failed = computed(() => data.value === undefined && status.value === 'error');
const loading = computed(() => data.value === undefined && !failed.value);
const admin = computed(() => session.can('base.administer_hub'));

const now = ref(Date.now());
const clock = setInterval(() => {
  now.value = Date.now();
}, CLOCK_TICK_MS);
onBeforeUnmount(() => clearInterval(clock));

/** «Atlantic/Canary · 10:30»: the zone and the time it is there; a zone this browser does not know, as it is. */
const zone = computed(() => {
  const name = data.value?.timezone ?? '';
  try {
    const time = new Intl.DateTimeFormat(locale.value, {
      timeZone: name,
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(now.value);
    return `${name} · ${time}`;
  } catch {
    return name;
  }
});

const where = computed(() => {
  if (data.value?.demo) return t('base.settingsBusiness.whereDemo');
  return admin.value ? t('base.settingsBusiness.whereAdmin') : t('base.settingsBusiness.whereOthers');
});
const offered = managementOffered();
const changeUrl = computed(() => (admin.value && offered.value && !data.value?.demo ? (data.value?.settings_url ?? '') : ''));

const invoiceOn = computed(() => session.me.value?.apps.some((app) => app.label === 'invoice' && app.state === 'on'));
/** Invoicing's issuer for whoever may write it; Apps to install it while it is not on; nothing otherwise. */
const fiscal = computed(() => {
  if (invoiceOn.value) return session.can('invoice.manage_issuer') ? { to: '/invoice/issuer', hint: 'fiscalHint' } : null;
  return { to: '/apps', hint: 'fiscalInstall' };
});

const shown = (text: string | undefined) => text || t('base.settingsBusiness.none');
</script>

<template>
  <div class="settings-business">
    <ion-list
      v-if="loading"
      inset
      data-testid="business-loading"
    >
      <ion-item lines="none">
        <ion-spinner
          slot="start"
          name="crescent"
        />
        <ion-label>
          <span data-testid="business-loading-text">{{ t('base.settingsBusiness.loading') }}</span>
        </ion-label>
      </ion-item>
    </ion-list>

    <InlineFeedback
      v-else-if="failed"
      tone="warning"
      data-testid="business-error"
      :heading="t('base.settingsBusiness.loadError')"
    >
      {{ t('base.settingsBusiness.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="business-retry"
          @click="refresh"
        >
          {{ t('base.settingsBusiness.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <template v-else-if="data">
      <section class="settings-business__card">
        <h2 class="settings-business__title">
          {{ t('base.settingsBusiness.title') }}
        </h2>
        <ion-list lines="none">
          <SettingsRow
            data-testid="business-name"
            icon="ion:storefront-outline"
            :title="t('base.settingsBusiness.name')"
            :hint="t('base.settingsBusiness.nameHint')"
            :value="shown(data.name)"
          />
          <SettingsRow
            data-testid="business-country"
            icon="ion:globe-outline"
            :title="t('base.settingsBusiness.country')"
            :hint="t('base.settingsBusiness.countryHint')"
            :value="shown(data.country_name)"
          />
          <SettingsRow
            data-testid="business-timezone"
            icon="ion:time-outline"
            :title="t('base.settingsBusiness.timezone')"
            :hint="t('base.settingsBusiness.timezoneHint')"
            :value="zone"
          />
          <SettingsRow
            data-testid="business-currency"
            icon="ion:cash-outline"
            :title="t('base.settingsBusiness.currency')"
            :hint="t('base.settingsBusiness.currencyHint')"
            :value="data.currency_label"
          />
          <SettingsRow
            data-testid="business-language"
            icon="ion:language-outline"
            :title="t('base.settingsBusiness.language')"
            :hint="t('base.settingsBusiness.languageHint')"
            :value="data.language_name"
          />
        </ion-list>
        <footer class="settings-business__footer">
          <p
            class="settings-business__where"
            data-testid="business-where"
          >
            {{ where }}
          </p>
          <ion-button
            v-if="changeUrl"
            fill="outline"
            size="small"
            :href="changeUrl"
            target="_blank"
            rel="noopener"
            data-testid="business-change"
            @click="openExternalLink(changeUrl, $event)"
          >
            <HubIcon
              slot="start"
              name="ion:open-outline"
            />
            <span data-testid="business-change-label">{{ t('base.settingsBusiness.change') }}</span>
          </ion-button>
        </footer>
      </section>

      <section
        v-if="fiscal"
        class="settings-business__card"
      >
        <ion-list lines="none">
          <SettingsRow
            data-testid="business-fiscal"
            icon="ion:receipt-outline"
            :title="t('base.settingsBusiness.fiscal')"
            :hint="t(`base.settingsBusiness.${fiscal.hint}`)"
            :to="fiscal.to"
          />
        </ion-list>
      </section>
    </template>
  </div>
</template>

<style scoped>
.settings-business {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-business__card {
  box-sizing: border-box;
  min-width: 0;
  padding: 16px 8px 8px;
  border: 1px solid var(--ion-color-step-150, #e4e7ec);
  border-radius: var(--ep-radius-lg, 16px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}

.settings-business__card ion-list {
  padding: 0;
  background: transparent;
}

.settings-business__title {
  margin: 0 0 4px;
  padding: 0 12px;
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--ion-text-color);
}

.settings-business__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 8px 12px;
}

.settings-business__where {
  flex: 1 1 260px;
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}
</style>
