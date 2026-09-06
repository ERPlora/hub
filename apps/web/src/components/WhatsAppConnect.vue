<script setup lang="ts">
// The «Channel» block of the WhatsApp module's settings, provided by the shell as the custom
// element `<erp-whatsapp-connect>` (hub#1600, ADR-0452). A module cannot load Meta's SDK — no
// foreign script may run from a module bundle — so the shell owns the popup, the CSP exception
// and the runtime doors, and the module only embeds this element where its «Channel» block is.
//
// Three states, one sentence each: no Meta app configured on the SaaS → nothing at all (a button
// that opens nothing is worse than none); no number → the button; a number → the number, its
// origin (the WhatsApp Business app, when it came from there) and «Disconnect». A refusal from
// the SaaS becomes the sentence its code maps to, never the code.
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonBadge, IonButton, IonIcon } from '@ionic/vue';
import { isAdmin } from '../lib/session';
import {
  WhatsAppConnectError,
  connectWhatsApp,
  disconnectWhatsApp,
  fetchWhatsAppConfig,
  fetchWhatsAppNumbers,
  loadMetaSdk,
  openEmbeddedSignup,
  type WhatsAppConnectConfig,
  type WhatsAppNumber,
} from '../lib/whatsapp-connect';

const { t, te, locale } = useI18n();

const config = ref<WhatsAppConnectConfig | null>(null);
const numbers = ref<WhatsAppNumber[]>([]);
const ready = ref(false);
const busy = ref(false);
const status = ref('');
const statusIsError = ref(false);

const configured = computed(() => config.value?.configured === true);

async function refresh(): Promise<void> {
  try {
    const [cfg, list] = await Promise.all([fetchWhatsAppConfig(), fetchWhatsAppNumbers()]);
    config.value = cfg;
    numbers.value = list.filter((n) => n.is_active !== false);
  } catch {
    // A runtime that cannot answer (no session yet, SaaS down) renders nothing rather than a
    // button that would fail on click; the next mount asks again.
    config.value = null;
    numbers.value = [];
  } finally {
    ready.value = true;
  }
}

onMounted(refresh);

function sentence(error: unknown): string {
  const code = error instanceof WhatsAppConnectError ? error.code : 'default';
  const key = `whatsappConnect.errors.${code}`;
  return te(key) ? t(key) : t('whatsappConnect.errors.default');
}

function say(text: string, isError: boolean): void {
  status.value = text;
  statusIsError.value = isError;
}

async function connect(): Promise<void> {
  const cfg = config.value;
  if (!cfg || busy.value) return;
  busy.value = true;
  say(t('whatsappConnect.loading'), false);
  try {
    const FB = await loadMetaSdk({ appId: cfg.app_id, graphVersion: cfg.graph_version, locale: String(locale.value) });
    const result = await openEmbeddedSignup(FB, cfg.config_id);
    say(t('whatsappConnect.connecting'), false);
    await connectWhatsApp(result);
    say('', false);
    await refresh();
  } catch (error) {
    say(sentence(error), true);
  } finally {
    busy.value = false;
  }
}

async function disconnect(number: WhatsAppNumber): Promise<void> {
  if (busy.value) return;
  if (typeof window !== 'undefined' && typeof window.confirm === 'function' && !window.confirm(t('whatsappConnect.disconnectConfirm'))) {
    return;
  }
  busy.value = true;
  say('', false);
  try {
    await disconnectWhatsApp(number.phone_number_id);
    await refresh();
  } catch (error) {
    say(sentence(error), true);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section v-if="ready && configured" class="whatsapp-connect">
    <template v-if="numbers.length">
      <div v-for="number in numbers" :key="number.phone_number_id" class="whatsapp-connect__number">
        <div class="whatsapp-connect__identity">
          <strong class="whatsapp-connect__phone">{{ number.display_phone }}</strong>
          <span class="whatsapp-connect__badges">
            <ion-badge color="success">{{ t('whatsappConnect.connected') }}</ion-badge>
            <ion-badge v-if="number.is_on_biz_app" color="medium">{{ t('whatsappConnect.businessApp') }}</ion-badge>
          </span>
        </div>
        <ion-button
          v-if="isAdmin"
          data-test="whatsapp-disconnect-button"
          fill="clear"
          size="small"
          color="danger"
          :disabled="busy"
          @click="disconnect(number)"
        >
          {{ t('whatsappConnect.disconnect') }}
        </ion-button>
      </div>
      <p class="whatsapp-connect__help">{{ t('whatsappConnect.connectedHelp') }}</p>
    </template>
    <template v-else>
      <p class="whatsapp-connect__intro">{{ t('whatsappConnect.intro') }}</p>
      <ion-button v-if="isAdmin" data-test="whatsapp-connect-button" :disabled="busy" @click="connect">
        <ion-icon slot="start" name="logo-whatsapp" aria-hidden="true" />
        {{ t('whatsappConnect.connect') }}
      </ion-button>
      <p v-else class="whatsapp-connect__admin-only">{{ t('whatsappConnect.adminOnly') }}</p>
    </template>
    <p
      v-if="status"
      class="whatsapp-connect__status"
      :class="{ 'whatsapp-connect__status--error': statusIsError }"
      role="status"
      aria-live="polite"
    >
      {{ status }}
    </p>
  </section>
</template>

<style scoped>
.whatsapp-connect {
  display: grid;
  gap: 0.5rem;
}
.whatsapp-connect__number {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.whatsapp-connect__identity {
  display: grid;
  gap: 0.25rem;
}
.whatsapp-connect__phone {
  font-variant-numeric: tabular-nums;
}
.whatsapp-connect__badges {
  display: inline-flex;
  gap: 0.375rem;
}
.whatsapp-connect__intro,
.whatsapp-connect__help,
.whatsapp-connect__admin-only,
.whatsapp-connect__status {
  margin: 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium, #6b7280);
}
.whatsapp-connect__status--error {
  color: var(--ion-color-danger, #b91c1c);
}
</style>
