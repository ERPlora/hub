<script setup lang="ts">
// The «Professional» field of the booking and series panels (APPOINTMENT-F01, F12): a search of the active, bookable
// professionals (Staff) who do every service chosen (Services), or, for a person who books only for themselves, their
// own record, fixed (`own`). It hands its `name` to its field, so the window tells that a professional chosen corrects
// a refusal of the professional, though another field was refused with the same words (hub#888).
import { Combo, type ComboOption } from '@erplora/ui/components';
import { useLiveClient } from '@erplora/ui/sdk';

import { useT } from '../composables/useT';
import { eligibleStaff } from '../lib/pickers';

const props = withDefaults(
  defineProps<{
    /** The services chosen: the professionals offered do all of them. */
    serviceIds: readonly string[];
    /** Prefix of the field's `data-testid` (`<testid>-staff`). */
    testid: string;
    /** The form's key for the professional, handed to the field. */
    name?: string;
    errorText?: string;
    /** The person's own record: shown, never cleared nor changed. */
    own?: boolean;
    disabled?: boolean;
  }>(),
  { name: undefined, errorText: undefined, own: false, disabled: false },
);
const staff = defineModel<ComboOption | null>({ required: true });

const t = useT();
const client = useLiveClient();
const search = (query: string) => eligibleStaff(client, props.serviceIds, query);
</script>

<template>
  <Combo
    :testid="`${testid}-staff`"
    :name="name"
    :model-value="staff"
    :search="search"
    :label="t('appointment.form.staff')"
    :placeholder="t('appointment.form.pickStaff')"
    :empty-label="t('appointment.form.staffNone')"
    :error-text="errorText"
    :clearable="!own"
    :disabled="own || disabled"
    @update:model-value="staff = $event"
  />
</template>
