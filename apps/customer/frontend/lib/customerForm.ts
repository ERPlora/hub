// The card's form, one shape for «Add» (CUSTOMER-F01) and «Edit» (F04): the product's split (name,
// phone, email, tax id and company in sight; the rest behind «More details»), what «Add» sends in one
// call and what «Save» sends (only what changed). Every rule on the values is the server's.
import type { CustomerDetailOut, CustomerIn, CustomerPatchIn, CustomerSource, CustomerStage, PreferredChannel } from '../operations';

/** Everything the form edits; dates as `YYYY-MM-DD` or `''`. */
export interface CustomerFields {
  name: string;
  email: string;
  phone: string;
  tax_id: string;
  company_name: string;
  address: string;
  city: string;
  postal_code: string;
  country: string;
  avatar: string;
  birthday: string;
  anniversary: string;
  source: CustomerSource;
  lifecycle_stage: CustomerStage;
  preferred_channel: PreferredChannel;
  notes: string;
  is_active: boolean;
}

export type CustomerField = keyof CustomerFields;

/** In sight in «Add»: identity and the tax id (the market's split, product customers#51). */
export const ESSENTIAL_FIELDS: readonly CustomerField[] = ['name', 'phone', 'email', 'tax_id', 'company_name'];

/** Behind «More details» in «Add»; right after the essentials in «Edit». */
export const MORE_FIELDS: readonly CustomerField[] = [
  'address',
  'city',
  'postal_code',
  'country',
  'avatar',
  'birthday',
  'anniversary',
  'source',
  'lifecycle_stage',
  'preferred_channel',
  'notes',
];

export const STAGES: readonly CustomerStage[] = [
  'lead',
  'prospect',
  'first_purchase',
  'active',
  'at_risk',
  'dormant',
  'churned',
  'vip',
];

/** The sources a person picks; `import` is written by the import only. */
export const PICKABLE_SOURCES: readonly CustomerSource[] = ['walk_in', 'phone', 'whatsapp', 'website', 'social', 'referral', 'other'];

export const CHANNELS: readonly PreferredChannel[] = ['none', 'email', 'sms', 'whatsapp', 'phone'];

const DATE_FIELDS = new Set<CustomerField>(['birthday', 'anniversary']);

export function blankCustomer(): CustomerFields {
  return {
    name: '',
    email: '',
    phone: '',
    tax_id: '',
    company_name: '',
    address: '',
    city: '',
    postal_code: '',
    country: '',
    avatar: '',
    birthday: '',
    anniversary: '',
    source: 'walk_in',
    lifecycle_stage: 'lead',
    preferred_channel: 'none',
    notes: '',
    is_active: true,
  };
}

/** «Add» sends the whole card in one call; a new card is always active. */
export function createInput(form: CustomerFields): CustomerIn {
  const input: CustomerIn & { is_active?: boolean } = {
    ...form,
    birthday: form.birthday || null,
    anniversary: form.anniversary || null,
  };
  delete input.is_active;
  return input;
}

/** The form of a saved card. */
export function fieldsFromDetail(detail: CustomerDetailOut): CustomerFields {
  return {
    name: detail.name,
    email: detail.email,
    phone: detail.phone,
    tax_id: detail.tax_id,
    company_name: detail.company_name,
    address: detail.address,
    city: detail.city,
    postal_code: detail.postal_code,
    country: detail.country,
    avatar: detail.avatar,
    birthday: detail.birthday ?? '',
    anniversary: detail.anniversary ?? '',
    source: detail.source,
    lifecycle_stage: detail.lifecycle_stage,
    preferred_channel: detail.preferred_channel,
    notes: detail.notes,
    is_active: detail.is_active,
  };
}

/** What «Save» sends: the fields that changed (an emptied date as `null`, which clears it). */
export function patchInput(original: CustomerFields, form: CustomerFields): Partial<CustomerPatchIn> {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(form) as CustomerField[]) {
    if (form[key] === original[key]) continue;
    out[key] = DATE_FIELDS.has(key) ? form[key] || null : form[key];
  }
  return out as Partial<CustomerPatchIn>;
}
