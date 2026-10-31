<script setup lang="ts">
// SERVICE-F01, F02, F03: the old table's side panel as a dialog. «New service» asks for Name, Pricing
// (Fixed price by default), «Price (PLN)» (in the business's currency, its country's, with its decimals; just
// «Price» until the business answers; service-business-currency), Duration (min; empty = the settings'), Category (searched; empty =
// «No category») and Tax category (searched in Taxes; the settings' default comes chosen; no empty
// option). «Create service» needs a name and a tax category; with no tax category in Taxes at all it
// says where to make them. A row opens «Editing service — {name}»: «Save changes» sends only what
// changed (no category = `category_id: null`), and below the form who performs the service. «Photo» (SERVICE-F34/F35,
// for who may edit services): a library image (Hair and Beauty first) or a photo of its own, sent once the service is
// saved (`set_image`, `upload_image`, «Uploading photo…»); if the service saved and the photo did not, the form says so
// with «Retry» (only the photo goes again) and the service keeps the photo it had.
import { Combo, type ComboOption, FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import ImageField from '../../../../base/frontend/components/ImageField.vue';
import { draftOf, type ImageDraft, useImageSave } from '../../../../base/frontend/lib/item-image';
import { useLocale, useT } from '../composables/useT';
import { useBusinessMoney } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchServiceCategories, searchTaxCategories } from '../lib/pickers';
import type { PricingType, ServiceOut, ServicePatchIn } from '../operations';
import MoneyInput from './MoneyInput.vue';
import ServiceProfessionals from './ServiceProfessionals.vue';

const PRICING: readonly PricingType[] = ['fixed', 'hourly', 'from', 'variable', 'free'];
/** The library's sectors a service's photo is looked for in first. */
const PHOTO_FOLDERS = ['beauty_hair', 'beauty_body'] as const;

const props = withDefaults(
  defineProps<{
    /** The service being edited; `null` = «New service». */
    service: ServiceOut | null;
    /** May edit services: the professionals section changes them. */
    canChange?: boolean;
  }>(),
  { canChange: false },
);

const open = defineModel<boolean>('open', { default: false });

interface Form {
  name: string;
  pricing: PricingType;
  price: string;
  duration: string;
  category: ComboOption | null;
  tax: ComboOption | null;
}

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const money = useBusinessMoney();
const searchCategories = searchServiceCategories(client);
const searchTaxes = computed(() => searchTaxCategories(client, t, locale.value));

const { data: settings } = useLive('service.settings.get', {});
// Whether Taxes has any category at all (one is enough to know).
const { data: taxes } = useLive('tax.category.list', { limit: 1 });
const noTaxes = computed(() => taxes.value !== undefined && taxes.value.total === 0);

const creation = useCommand('service.service.create');
const update = useCommand('service.service.update');
const setImage = useCommand('service.service.set_image');
const uploadImage = useCommand('service.service.upload_image');
const photo = useImageSave({
  set: (id, image) => setImage.run({ id, image }),
  upload: (id, data) => uploadImage.run({ id, data_base64: data }),
});
const pending = computed(() => creation.pending.value || update.pending.value || photo.pending.value);
const error = computed(() => (props.service ? update.error.value : creation.error.value));
const title = computed(() =>
  props.service ? t('service.services.form.titleEdit', { name: props.service.name }) : t('service.services.form.titleNew'),
);

const form = ref<Form>(blank());
const image = ref<ImageDraft>(draftOf(props.service));
const taxTouched = ref(false);
const tried = ref(false);

function defaultTax(): ComboOption | null {
  const now = settings.value;
  return now?.default_tax_category_key ? { id: now.default_tax_category_key, label: now.default_tax_category_name ?? now.default_tax_category_key } : null;
}

function blank(): Form {
  return { name: '', pricing: 'fixed', price: '', duration: '', category: null, tax: null };
}

function fromService(service: ServiceOut): Form {
  return {
    name: service.name,
    pricing: service.pricing_type,
    price: moneyFieldText(service.price, locale.value, money.value),
    duration: String(service.duration_minutes),
    category: service.category_id ? { id: service.category_id, label: service.category_name ?? '' } : null,
    tax: service.tax_category_key ? { id: service.tax_category_key, label: service.tax_category_name ?? service.tax_category_key } : null,
  };
}

watch(
  () => [open.value, props.service?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = props.service ? fromService(props.service) : { ...blank(), tax: defaultTax() };
    image.value = draftOf(props.service);
    photo.reset();
    taxTouched.value = false;
    tried.value = false;
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

// The business answers (or its currency changes) with the dialog open: a price the person has not touched is
// rewritten from the service with the currency's decimals («15.00» → «1500» in yen); what they typed stays as
// typed, read in the new currency when they save (the field says so when it cannot be).
watch(money, (now, before) => {
  if (!open.value || !props.service) return;
  if (form.value.price !== moneyFieldText(props.service.price, locale.value, before)) return;
  form.value = { ...form.value, price: moneyFieldText(props.service.price, locale.value, now) };
});

// The settings may arrive after the dialog opened: a new service takes their tax category until one is picked.
watch(settings, () => {
  if (!props.service && !taxTouched.value) form.value = { ...form.value, tax: defaultTax() };
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
/** Whole minutes as the server takes them; anything else as typed, for the server to refuse. */
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));

function pickTax(option: ComboOption | null): void {
  taxTouched.value = true;
  form.value = { ...form.value, tax: option };
}

function patch(service: ServiceOut, price: number): ServicePatchIn {
  const f = form.value;
  const out: ServicePatchIn = { id: service.id };
  if (f.name.trim() !== service.name) out.name = f.name.trim();
  if (f.pricing !== service.pricing_type) out.pricing_type = f.pricing;
  if (price !== service.price) out.price = price;
  if (f.duration.trim() !== String(service.duration_minutes)) out.duration_minutes = whole(f.duration);
  if ((f.category?.id ?? null) !== service.category_id) out.category_id = f.category?.id ?? null;
  if (f.tax && f.tax.id !== service.tax_category_key) out.tax_category_key = f.tax.id;
  return out;
}

async function save(): Promise<void> {
  tried.value = true;
  const f = form.value;
  const read = parseMoney(f.price, money.value);
  if (!read.ok || !f.tax) return;
  const price = read.cents ?? 0;
  let saved: { id: string };
  try {
    if (props.service) saved = await update.run(patch(props.service, price));
    else
      saved = await creation.run({
        name: f.name.trim(),
        pricing_type: f.pricing,
        price,
        ...(f.duration.trim() ? { duration_minutes: whole(f.duration) } : {}),
        category_id: f.category?.id ?? null,
        tax_category_key: f.tax.id,
      });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  await savePhoto(saved.id);
}

/** The photo's step for the saved service; the dialog closes once the photo is as the form says. */
async function savePhoto(id: string): Promise<void> {
  if (await photo.save(id, props.service?.image ?? '', image.value)) open.value = false;
}

function retryPhoto(): void {
  const failed = photo.failure.value;
  if (failed) void savePhoto(failed.id);
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="service-form"
    :title="title"
    :submit-label="photo.uploading.value ? $t('base.imageField.uploading') : service ? $t('service.services.form.save') : $t('service.services.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim() || !form.tax || (!service && noTaxes) || !!photo.failure.value"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="service-form">
        <InlineFeedback
          v-if="photo.failure.value"
          tone="warning"
          data-testid="service-form-photo-failed"
        >
          {{ t('service.services.form.photoNotSaved', { reason: photo.failure.value.reason || $t('base.imageField.notSaved') }) }}
          <template #actions>
            <ion-button
              data-testid="service-form-photo-retry"
              fill="outline"
              size="small"
              :disabled="photo.pending.value"
              @click="retryPhoto"
            >
              {{ $t('base.imageField.retry') }}
            </ion-button>
          </template>
        </InlineFeedback>
        <ion-input
          data-testid="service-form-name"
          :value="form.name"
          :label="$t('service.services.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-select
          data-testid="service-form-pricing_type"
          :value="form.pricing"
          :label="$t('service.services.form.pricingType')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.pricing_type"
          @ion-change="form = { ...form, pricing: $event.detail.value as PricingType }"
        >
          <ion-select-option
            v-for="type in PRICING"
            :key="type"
            :value="type"
          >
            {{ t(`service.pricing.${type}`) }}
          </ion-select-option>
        </ion-select>
        <MoneyInput
          testid="service-form-price"
          :model-value="form.price"
          :label="money ? t('service.services.form.priceIn', { currency: money.currency }) : t('service.services.form.price')"
          :error-text="fieldErrors.price"
          :show-error="tried"
          @update:model-value="form = { ...form, price: $event }"
        />
        <ion-input
          data-testid="service-form-duration"
          type="number"
          inputmode="numeric"
          min="1"
          :value="form.duration"
          :label="$t('service.services.form.duration')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.duration_minutes"
          :class="invalid(fieldErrors.duration_minutes)"
          @ion-input="form = { ...form, duration: text($event.detail.value) }"
        />
        <Combo
          testid="service-form-category"
          :model-value="form.category"
          :search="searchCategories"
          :label="t('service.services.form.category')"
          :placeholder="t('service.services.form.noCategory')"
          :error-text="fieldErrors.category_id || fieldErrors.category"
          @update:model-value="form = { ...form, category: $event }"
        />
        <Combo
          testid="service-form-tax"
          :model-value="form.tax"
          :search="searchTaxes"
          :clearable="false"
          :label="t('service.services.form.tax')"
          :error-text="fieldErrors.tax_category_key"
          @update:model-value="pickTax"
        />
        <InlineFeedback
          v-if="!service && noTaxes"
          tone="warning"
          data-testid="service-form-tax-missing"
        >
          {{ t('service.services.form.taxMissing') }}
        </InlineFeedback>
        <ImageField
          v-if="canChange"
          v-model="image"
          testid="service-form-image"
          :name="form.name.trim()"
          :folders="PHOTO_FOLDERS"
          :disabled="pending"
        />
        <ServiceProfessionals
          v-if="service"
          :service-id="service.id"
          :can-change="canChange"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.service-form {
  display: grid;
  gap: 14px;
}
</style>
