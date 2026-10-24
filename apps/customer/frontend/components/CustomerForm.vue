<script setup lang="ts">
// The card's form (CUSTOMER-F01, F04, F11), one for «Add» and «Edit» (WORKBOOK «Un solo formulario
// de ficha»): name, phone, email, tax id and company in sight; the rest behind «More details» (a
// native <details>, closed, as in the product) when adding; in «Edit» everything at once, then the
// business's custom fields, each with its own control, and «Active». The parent owns the model
// (`v-model`, `v-model:field-values`) and the submit; the server validates and its 422 comes back in
// `errors`, painted under its field («More details» opens when the field is in there). A number or a
// date the browser cannot read (31/02, «tres») reaches the page as "", so saving would empty the field:
// `readable()` tells it under its field, worded as the server's refusal, and the parent does not save.
// The country is the shared Combo (the product's `ok-combo`, customers#72): typing its name, or its code, filters
// the ~250 countries; the card keeps the ISO code, and clearing the field leaves it without one.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { IonCheckbox, IonInput, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, ref, useTemplateRef, watch } from 'vue';

import { countryName, countryOptions } from '../lib/countries';
import {
  CHANNELS,
  type CustomerField,
  type CustomerFields,
  ESSENTIAL_FIELDS,
  MORE_FIELDS,
  PICKABLE_SOURCES,
  STAGES,
} from '../lib/customerForm';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomFieldValueOut } from '../operations';

const form = defineModel<CustomerFields>({ required: true });
const fieldValues = defineModel<Record<string, string>>('fieldValues', { default: () => ({}) });
const props = withDefaults(
  defineProps<{
    mode: 'create' | 'edit';
    /** Per-field messages of the last refusal (`phone`, `field_values.<id>`…). */
    errors?: Record<string, string>;
    /** The business's active custom fields (edit only). */
    customFields?: CustomFieldValueOut[];
  }>(),
  { errors: () => ({}), customFields: () => [] },
);

const { t, locale } = useCustomerI18n();

const LABELS: Record<Exclude<CustomerField, 'is_active'>, string> = {
  name: 'customer.form.name',
  phone: 'customer.form.phone',
  email: 'customer.form.email',
  tax_id: 'customer.form.taxId',
  company_name: 'customer.form.company',
  address: 'customer.form.address',
  city: 'customer.form.city',
  postal_code: 'customer.form.postalCode',
  country: 'customer.form.country',
  avatar: 'customer.form.avatar',
  birthday: 'customer.form.birthday',
  anniversary: 'customer.form.anniversary',
  source: 'customer.form.source',
  lifecycle_stage: 'customer.form.stage',
  preferred_channel: 'customer.form.preferredChannel',
  notes: 'customer.form.notes',
};

/** The longest each text takes (schemas.py). */
const MAX_LENGTH: Partial<Record<CustomerField, number>> = {
  name: 200,
  email: 254,
  phone: 60,
  tax_id: 32,
  company_name: 200,
  address: 255,
  city: 100,
  postal_code: 20,
  avatar: 500,
  notes: 10000,
};

/** The native kinds of input the form uses (a subset of Ionic's `TextFieldTypes`). */
type InputType = 'text' | 'email' | 'tel' | 'date' | 'url' | 'number';

const INPUT_TYPES: Partial<Record<CustomerField, InputType>> = {
  email: 'email',
  phone: 'tel',
  birthday: 'date',
  anniversary: 'date',
  avatar: 'url',
};

type Kind = 'input' | 'select' | 'country' | 'textarea';
const kindOf = (field: CustomerField): Kind =>
  field === 'country'
    ? 'country'
    : field === 'notes'
      ? 'textarea'
      : field === 'source' || field === 'lifecycle_stage' || field === 'preferred_channel'
        ? 'select'
        : 'input';

type TextField = Exclude<CustomerField, 'is_active'>;

const sections = computed(() =>
  props.mode === 'create'
    ? [
        { id: 'essentials', more: false, fields: ESSENTIAL_FIELDS as TextField[] },
        { id: 'more', more: true, fields: MORE_FIELDS as TextField[] },
      ]
    : [{ id: 'all', more: false, fields: [...ESSENTIAL_FIELDS, ...MORE_FIELDS] as TextField[] }],
);

/** What the browser could not read at the last «Save», by the key the server would refuse it under. */
const unread = ref<Record<string, string>>({});
/** What is painted under each field: the server's last refusal and what the browser could not read. */
const shown = computed<Record<string, string>>(() => ({ ...props.errors, ...unread.value }));

const moreOpen = ref(false);
// A refusal of a field behind «More details» must be seen: the section opens.
watch(
  shown,
  (errors) => {
    if (MORE_FIELDS.some((field) => errors[field])) moreOpen.value = true;
  },
  { immediate: true },
);
function onToggle(event: Event): void {
  moreOpen.value = (event.target as HTMLDetailsElement).open;
}

/** The options of a select field, keeping a stored value outside the list (a card from an import). */
function optionsOf(field: TextField): { value: string; label: string }[] {
  if (field === 'lifecycle_stage') return STAGES.map((value) => ({ value, label: t(`customer.stage.${value}`) }));
  if (field === 'preferred_channel') return CHANNELS.map((value) => ({ value, label: t(`customer.channel.${value}`) }));
  const values: string[] = [...PICKABLE_SOURCES];
  if (form.value.source && !values.includes(form.value.source)) values.push(form.value.source);
  return values.map((value) => ({ value, label: t(`customer.source.${value}`) }));
}

/** The countries by their name in the page language, Spain first; the code is also searched. */
const countries = computed<ComboOption[]>(() =>
  countryOptions(locale.value).map((o) => ({ id: o.value, label: o.label, hint: o.value })),
);
/** The stored country; a code the list does not know is shown as stored and kept until changed. */
const country = computed<ComboOption | null>(() => {
  const code = form.value.country.trim();
  if (!code) return null;
  return countries.value.find((o) => o.id === code) ?? { id: code, label: countryName(code, locale.value) };
});

function set(field: CustomerField, value: unknown): void {
  form.value = { ...form.value, [field]: field === 'is_active' ? value === true : String(value ?? '') };
}

const invalid = (key: string) => ({ 'ion-invalid': !!shown.value[key], 'ion-touched': !!shown.value[key] });

function setFieldValue(fieldId: string, value: unknown): void {
  fieldValues.value = { ...fieldValues.value, [fieldId]: String(value ?? '') };
}

const fieldLabel = (field: CustomFieldValueOut): string =>
  field.is_required ? t('customer.form.required', { name: field.name }) : field.name;
const fieldError = (field: CustomFieldValueOut): string | undefined => shown.value[`field_values.${field.field_id}`];
const fieldInputType = (field: CustomFieldValueOut): InputType =>
  field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text';

const root = useTemplateRef<HTMLElement>('root');
const UNREADABLE = { number: 'customer.form.invalidNumber', date: 'customer.form.invalidDate' } as const;

/** Whether the browser read every number and date typed; if not, each one is told under its field. */
function readable(): boolean {
  const typed = [
    ...sections.value
      .flatMap((section) => section.fields)
      .filter((field) => INPUT_TYPES[field] === 'date')
      .map((field) => ({ key: field, testid: `customer-form-${field}`, type: 'date' as const })),
    ...(props.mode === 'edit' ? props.customFields : []).flatMap((field) =>
      field.field_type === 'number' || field.field_type === 'date'
        ? [{ key: `field_values.${field.field_id}`, testid: `customer-form-field-${field.field_id}`, type: field.field_type }]
        : [],
    ),
  ];
  unread.value = Object.fromEntries(
    typed
      .filter(({ testid }) => root.value?.querySelector<HTMLInputElement>(`[data-testid="${testid}"] input`)?.validity.badInput)
      .map(({ key, type }) => [key, t(UNREADABLE[type])]),
  );
  return Object.keys(unread.value).length === 0;
}

defineExpose({ readable });
</script>

<template>
  <div
    ref="root"
    class="customer-form"
    :class="`customer-form--${mode}`"
  >
    <component
      :is="section.more ? 'details' : 'div'"
      v-for="section in sections"
      :key="section.id"
      :class="section.more ? 'customer-form__more' : 'customer-form__section'"
      :open="section.more ? moreOpen : undefined"
      :data-testid="section.more ? 'customer-form-more' : undefined"
      @toggle="section.more && onToggle($event)"
    >
      <summary v-if="section.more">
        {{ $t('customer.form.moreDetails') }}
      </summary>
      <div class="customer-form__fields">
        <template
          v-for="field in section.fields"
          :key="field"
        >
          <Combo
            v-if="kindOf(field) === 'country'"
            testid="customer-form-country"
            data-field="country"
            :model-value="country"
            :options="countries"
            :label="t(LABELS.country)"
            :error-text="shown.country"
            @update:model-value="set('country', $event?.id ?? '')"
          />
          <ion-select
            v-else-if="kindOf(field) === 'select'"
            :data-testid="`customer-form-${field}`"
            :data-field="field"
            :model-value="form[field]"
            :label="t(LABELS[field])"
            label-placement="floating"
            interface="popover"
            fill="outline"
            mode="md"
            :error-text="shown[field]"
            :class="invalid(field)"
            @update:model-value="set(field, $event)"
          >
            <ion-select-option
              v-for="option in optionsOf(field)"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </ion-select-option>
          </ion-select>
          <ion-textarea
            v-else-if="kindOf(field) === 'textarea'"
            :data-testid="`customer-form-${field}`"
            :data-field="field"
            class="customer-form__wide"
            :model-value="form.notes"
            :label="t(LABELS.notes)"
            label-placement="floating"
            fill="outline"
            mode="md"
            :auto-grow="true"
            :maxlength="MAX_LENGTH.notes"
            :error-text="shown.notes"
            :class="invalid('notes')"
            @update:model-value="set('notes', $event)"
          />
          <ion-input
            v-else
            :data-testid="`customer-form-${field}`"
            :data-field="field"
            :model-value="form[field]"
            :type="INPUT_TYPES[field] ?? 'text'"
            :inputmode="field === 'phone' ? 'tel' : field === 'email' ? 'email' : undefined"
            :autocomplete="field === 'name' ? 'off' : undefined"
            :label="t(LABELS[field])"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="MAX_LENGTH[field]"
            :helper-text="field === 'phone' ? t('customer.form.phoneHint') : undefined"
            :error-text="shown[field]"
            :class="invalid(field)"
            :data-autofocus="field === 'name' ? '' : undefined"
            @update:model-value="set(field, $event)"
          />
        </template>
      </div>
    </component>

    <section
      v-if="mode === 'edit' && customFields.length"
      class="customer-form__custom"
      data-testid="customer-form-custom-fields"
    >
      <h3>{{ $t('customer.form.customFields') }}</h3>
      <div class="customer-form__fields">
        <template
          v-for="field in customFields"
          :key="field.field_id"
        >
          <ion-select
            v-if="field.field_type === 'select'"
            :data-testid="`customer-form-field-${field.field_id}`"
            :model-value="fieldValues[field.field_id] ?? ''"
            :label="fieldLabel(field)"
            label-placement="floating"
            interface="popover"
            fill="outline"
            mode="md"
            :error-text="fieldError(field)"
            :class="invalid(`field_values.${field.field_id}`)"
            @update:model-value="setFieldValue(field.field_id, $event)"
          >
            <ion-select-option
              v-for="option in field.options"
              :key="option"
              :value="option"
            >
              {{ option }}
            </ion-select-option>
          </ion-select>
          <ion-textarea
            v-else-if="field.field_type === 'textarea'"
            :data-testid="`customer-form-field-${field.field_id}`"
            :model-value="fieldValues[field.field_id] ?? ''"
            :label="fieldLabel(field)"
            label-placement="floating"
            fill="outline"
            mode="md"
            :auto-grow="true"
            :error-text="fieldError(field)"
            :class="invalid(`field_values.${field.field_id}`)"
            @update:model-value="setFieldValue(field.field_id, $event)"
          />
          <div
            v-else-if="field.field_type === 'boolean'"
            class="customer-form__check"
          >
            <ion-checkbox
              :data-testid="`customer-form-field-${field.field_id}`"
              label-placement="end"
              justify="start"
              :checked="fieldValues[field.field_id] === 'true'"
              @ion-change="setFieldValue(field.field_id, $event.detail.checked ? 'true' : 'false')"
            >
              {{ fieldLabel(field) }}
            </ion-checkbox>
            <p
              v-if="fieldError(field)"
              class="customer-form__error"
              role="alert"
            >
              {{ fieldError(field) }}
            </p>
          </div>
          <ion-input
            v-else
            :data-testid="`customer-form-field-${field.field_id}`"
            :model-value="fieldValues[field.field_id] ?? ''"
            :type="fieldInputType(field)"
            :label="fieldLabel(field)"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldError(field)"
            :class="invalid(`field_values.${field.field_id}`)"
            @update:model-value="setFieldValue(field.field_id, $event)"
          />
        </template>
      </div>
    </section>

    <ion-checkbox
      v-if="mode === 'edit'"
      class="customer-form__active"
      data-testid="customer-form-active"
      label-placement="end"
      justify="start"
      :checked="form.is_active"
      @ion-change="set('is_active', $event.detail.checked)"
    >
      {{ $t('customer.form.active') }}
    </ion-checkbox>
  </div>
</template>

<style scoped>
.customer-form {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.customer-form__fields {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

/* «Edit» lays the card out in a grid, as the product's sheet did; «Add» stacks the fields. */
.customer-form--edit .customer-form__fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
  gap: 0.75rem;
}

.customer-form--edit .customer-form__wide {
  grid-column: 1 / -1;
}

/* 44 px of touch target on the summary: «Add» is used standing, with one hand. */
.customer-form__more > summary {
  cursor: pointer;
  padding: 0.6rem 0.25rem;
  min-height: 44px;
  display: flex;
  align-items: center;
  font-weight: 600;
  font-size: 0.9rem;
}

.customer-form__more > .customer-form__fields {
  margin-top: 0.7rem;
}

.customer-form__custom h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-form__check {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.customer-form__error {
  margin: 0.25rem 0 0;
  color: var(--ion-color-danger);
  font-size: 0.75rem;
}

.customer-form__active {
  margin: 0.15rem 0.9rem 0.15rem 0;
}
</style>
