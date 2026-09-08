<script setup lang="ts">
// The «Channel» block of the WhatsApp module's settings, provided by the shell as the custom
// element `<erp-whatsapp-connect>` (hub#1600, ADR-0452). A module cannot load Meta's SDK — no
// foreign script may run from a module bundle — so the shell owns the popup, the CSP exception
// and the runtime doors, and the module only embeds this element where its «Channel» block is.
//
// No `<style>` block here on purpose (hub#1614): this component is only ever mounted as the
// custom element `<erp-whatsapp-connect>`, and Vite would send a scoped block to the shell's
// global stylesheet — which never reaches inside the module's shadow root. Its rules live with
// the element, in `elements/whatsapp-connect.ts`, and travel with it.
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
/** The sentence for a mount that failed, and whether asking again could change it (a refusal by role cannot). */
const loadError = ref('');
const loadRefused = ref(false);

const configured = computed(() => config.value?.configured === true);
/**
 * The channel is down: Meta refused to renew the business token of at least one number and only the
 * owner can put it right, by connecting again (hub#1626, fed by saas#1887).
 *
 * Read off the list rather than kept as state of its own, so it clears itself: the sweep drops the
 * flag the moment an exchange works again, and the next `refresh()` — the one every connect and
 * disconnect already does — paints the block green with nobody touching anything.
 *
 * Explicitly `=== true`, never truthiness: a SaaS from before the field sends no key at all, and
 * `undefined` there means «we did not ask», not «broken».
 */
const needsReconnect = computed(() => numbers.value.some((n) => n.needs_reconnect === true));

async function refresh(): Promise<void> {
  try {
    const [cfg, list] = await Promise.all([fetchWhatsAppConfig(), fetchWhatsAppNumbers()]);
    config.value = cfg;
    numbers.value = list.filter((n) => n.is_active !== false);
    loadError.value = '';
    loadRefused.value = false;
  } catch (error) {
    // A runtime that cannot answer (SaaS down, no session, a cashier's session) is said out loud
    // and can be asked again: an empty block reads as «not available» and hides the failure.
    config.value = null;
    numbers.value = [];
    loadError.value = sentence(error);
    loadRefused.value = error instanceof WhatsAppConnectError && (error.status === 401 || error.status === 403);
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
  <section v-if="ready && (configured || loadError)" class="whatsapp-connect">
    <template v-if="loadError">
      <p class="whatsapp-connect__status whatsapp-connect__status--error" role="alert">{{ loadError }}</p>
      <ion-button v-if="!loadRefused" data-test="whatsapp-retry-button" fill="clear" size="small" @click="refresh">
        {{ t('whatsappConnect.retry') }}
      </ion-button>
    </template>
    <template v-else-if="numbers.length">
      <div v-for="number in numbers" :key="number.phone_number_id" class="whatsapp-connect__number">
        <div class="whatsapp-connect__identity">
          <strong class="whatsapp-connect__phone">{{ number.display_phone }}</strong>
          <span class="whatsapp-connect__badges">
            <!-- The badge marks WHICH number died; the sentence and the button below say what to do
                 about it. Ionic colours this itself, which is what makes it survive being embedded
                 in a module's shadow root, where the shell's stylesheet does not reach (hub#1614). -->
            <ion-badge
              data-test="whatsapp-status-badge"
              :color.attr="number.needs_reconnect === true ? 'danger' : 'success'"
            >
              {{ number.needs_reconnect === true ? t('whatsappConnect.reconnectBadge') : t('whatsappConnect.connected') }}
            </ion-badge>
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
      <template v-if="needsReconnect">
        <p
          data-test="whatsapp-reconnect-needed"
          class="whatsapp-connect__status whatsapp-connect__status--error"
          role="alert"
        >
          {{ t('whatsappConnect.reconnectNeeded') }}
        </p>
        <!-- The same door as the first connection: Meta's embedded signup re-issues the permission
             for the business, so there is nothing to undo first. Disconnect stays where it was, for
             an owner who would rather stop than reconnect. -->
        <ion-button
          v-if="isAdmin"
          data-test="whatsapp-reconnect-button"
          :disabled="busy"
          @click="connect"
        >
          <ion-icon slot="start" name="logo-whatsapp" aria-hidden="true" />
          {{ t('whatsappConnect.reconnect') }}
        </ion-button>
        <p v-else class="whatsapp-connect__admin-only">{{ t('whatsappConnect.adminOnly') }}</p>
      </template>
      <!-- «Your customers' messages arrive here» is false while the permission is down, and it is
           the sentence that keeps an owner from looking any further. -->
      <p v-else class="whatsapp-connect__help">{{ t('whatsappConnect.connectedHelp') }}</p>
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

