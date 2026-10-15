<script setup lang="ts">
// CART_CHECKOUT-F01 «Crear un carrito»: «New cart» asks for Session (required), Email and Name, with the
// old panel's placeholders, and «Save» sends `cart_checkout.cart.create` without a currency: the server
// gives the business's one. Refusals stay in the dialog, under their field, with what was typed; the new
// cart comes back through the list's stream.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { ref, watch } from 'vue';

import type { CartOut } from '../operations';

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ created: [cart: CartOut] }>();

interface Form {
  session: string;
  email: string;
  name: string;
}

const EMPTY: Form = { session: '', email: '', name: '' };
const creation = useCommand('cart_checkout.cart.create');
const form = ref<Form>({ ...EMPTY });

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    form.value = { ...EMPTY };
    creation.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function save(): Promise<void> {
  const f = form.value;
  let cart: CartOut;
  try {
    cart = await creation.run({
      session_token: f.session.trim(),
      customer_email: f.email.trim(),
      customer_name: f.name.trim(),
    });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  emit('created', cart);
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="cart-checkout-cart-form"
    :title="$t('cart_checkout.carts.form.title')"
    :submit-label="$t('cart_checkout.carts.form.submit')"
    :pending="creation.pending.value"
    :error="creation.error.value"
    :submit-disabled="!form.session.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="cart-checkout-cart-form">
        <ion-input
          data-testid="cart-checkout-cart-form-session"
          :value="form.session"
          :label="$t('cart_checkout.carts.form.session')"
          :placeholder="$t('cart_checkout.carts.form.sessionPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="128"
          data-autofocus
          :error-text="fieldErrors.session_token"
          :class="invalid(fieldErrors.session_token)"
          @ion-input="form = { ...form, session: text($event.detail.value) }"
        />
        <ion-input
          data-testid="cart-checkout-cart-form-email"
          :value="form.email"
          type="email"
          inputmode="email"
          :label="$t('cart_checkout.carts.form.email')"
          :placeholder="$t('cart_checkout.carts.form.emailPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="254"
          :error-text="fieldErrors.customer_email"
          :class="invalid(fieldErrors.customer_email)"
          @ion-input="form = { ...form, email: text($event.detail.value) }"
        />
        <ion-input
          data-testid="cart-checkout-cart-form-name"
          :value="form.name"
          :label="$t('cart_checkout.carts.form.name')"
          :placeholder="$t('cart_checkout.carts.form.namePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.customer_name"
          :class="invalid(fieldErrors.customer_name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.cart-checkout-cart-form {
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}
</style>
