<!--
  NotFoundPage — the screen for an address this hub does not have (hub#1723).

  It did not exist before: the router's catch-all redirected ANY unknown route to `/dashboard`, and
  a redirect is silent by definition — it rewrites the address bar, so it destroys on the way in
  the evidence that the link was wrong. QA pasted `/tpv` or `/sales`, saw Home with its menu and
  its content, and believed they were where they had asked for. The real screens live under
  `/m/<module>/<nav>`, but nothing suggested so.

  The answer is the one the market has settled on, not one of our own: Shopify admin, Square
  Dashboard, Stripe, Odoo and Business Central answer an address they do not have with a page that
  says so and ONE way out. Here that way out is Home, and the screen is painted INSIDE the shell's
  layout (AppPage) so the menu stays at hand: a full-screen 404 would leave the browser's Back
  button as the only exit.

  No alias map (`/tpv` → `/m/sales/pos`): the shell is the kernel and does not know the ids of the
  modules — which are installed at runtime besides, so the alias would be false on a hub that does
  not have that module. Guessing the intent of a broken link hides the error instead of showing it.
-->
<template>
  <AppPage :title="t('notFound.title')" content-layout="detail">
    <ok-empty-state
      icon="help-circle-outline"
      :heading="t('notFound.title')"
      :message="t('notFound.body')"
      data-testid="not-found"
    >
      <ion-button slot="action" router-link="/dashboard" data-testid="not-found-home">
        {{ t('notFound.action') }}
      </ion-button>
    </ok-empty-state>
  </AppPage>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

import AppPage from '../components/AppPage.vue';

const { t } = useI18n();
</script>
