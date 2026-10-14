<script setup lang="ts">
// The country of the card (CUSTOMER-F01), picked by its name from a searchable list — the product's
// `ok-combo` (customers#72): ~250 countries are a scroll nobody finishes in a plain select. A
// read-only field shows the name; tapping it opens an ion-modal with a search box (name in the page
// language, without accents or case, or the code) and the list, Spain first. The value is the ISO
// code; «No country» clears it. Until `@erplora/ui` has a shared SearchSelect (UI-REQUESTS.md).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonInput, IonItem, IonLabel, IonList, IonModal, IonSearchbar, IonTitle, IonToolbar } from '@ionic/vue';
import { computed, ref } from 'vue';

import { countryName, countryOptions } from '../lib/countries';
import { useCustomerI18n } from '../lib/useCustomerI18n';

const value = defineModel<string>({ required: true });
const props = withDefaults(defineProps<{ label: string; testid: string; error?: string }>(), { error: undefined });

const { locale } = useCustomerI18n();
const open = ref(false);
const term = ref('');

const normalize = (text: string): string => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();

const shownName = computed(() => countryName(value.value, locale.value));
const options = computed(() => {
  const all = countryOptions(locale.value);
  const wanted = normalize(term.value);
  if (!wanted) return all;
  return all.filter((o) => normalize(o.label).includes(wanted) || o.value.toLowerCase() === wanted);
});

function show(): void {
  term.value = '';
  open.value = true;
}

function pick(code: string): void {
  value.value = code;
  open.value = false;
}
</script>

<template>
  <ion-input
    class="customer-country"
    :data-testid="testid"
    data-field="country"
    :model-value="shownName"
    :label="label"
    label-placement="floating"
    fill="outline"
    mode="md"
    readonly
    :error-text="error"
    :class="{ 'ion-invalid': !!error, 'ion-touched': !!error }"
    @click="show"
    @keydown.enter.prevent="show"
  >
    <HubIcon
      slot="end"
      name="ion:chevron-down-outline"
      aria-hidden="true"
    />
  </ion-input>
  <ion-modal
    :is-open="open"
    :aria-label="props.label"
    @did-dismiss="open = false"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title>{{ label }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            :data-testid="`${testid}-close`"
            :aria-label="$t('customer.common.close')"
            @click="open = false"
          >
            <HubIcon
              slot="icon-only"
              name="ion:close-outline"
            />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
      <ion-toolbar>
        <ion-searchbar
          class="ion-no-border"
          :data-testid="`${testid}-search`"
          :value="term"
          :placeholder="$t('customer.form.countrySearch')"
          @ion-input="term = String($event.detail.value ?? '')"
        />
      </ion-toolbar>
    </ion-header>
    <ion-content>
      <ion-list :data-testid="`${testid}-list`">
        <ion-item
          v-if="!term.trim()"
          button
          :detail="false"
          :data-testid="`${testid}-option-none`"
          @click="pick('')"
        >
          <ion-label>{{ $t('customer.form.countryNone') }}</ion-label>
        </ion-item>
        <ion-item
          v-for="option in options"
          :key="option.value"
          button
          :detail="false"
          :data-testid="`${testid}-option-${option.value}`"
          @click="pick(option.value)"
        >
          <ion-label>{{ option.label }}</ion-label>
          <HubIcon
            v-if="option.value === value"
            slot="end"
            name="ion:checkmark-outline"
          />
        </ion-item>
        <ion-item
          v-if="!options.length"
          lines="none"
        >
          <ion-label class="customer-country__none">
            {{ $t('customer.form.countryNoMatch') }}
          </ion-label>
        </ion-item>
      </ion-list>
    </ion-content>
  </ion-modal>
</template>

<style scoped>
.customer-country {
  cursor: pointer;
}

.customer-country__none {
  opacity: 0.7;
}
</style>
