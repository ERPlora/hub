<script setup lang="ts">
// «Your number» in Settings (WHATSAPP_INBOX-F01, F02): the number's state as erplora.com reports it, and connecting,
// reconnecting or disconnecting it here. Not connected (or to reconnect), it asks erplora.com what opens Meta's window
// (`whatsapp_inbox.channel.prepare`, door 10) and offers «Connect WhatsApp» («Reconnect») only when that window can be
// opened, saying why not otherwise; the window is followed by useMetaSignup and what it gave goes to
// `whatsapp_inbox.channel.connect` (door 11). «Disconnect» asks first (`whatsapp_inbox.channel.disconnect`, door 12).
// The state itself comes back live: the parent's `channel.get` follows erplora.com's answer and its photo.
import { ConfirmDialog, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useMetaSignup } from '../composables/useMetaSignup';
import { useT } from '../composables/useT';
import type { ChannelConnectOut, ChannelOut, ChannelPrepareOut } from '../operations';

const props = defineProps<{ channel: ChannelOut }>();

const TONES = { connected: 'success', not_connected: 'neutral', reconnect_needed: 'warning' } as const;
const LABELS = { connected: 'connected', not_connected: 'notConnected', reconnect_needed: 'reconnectNeeded' } as const;
const FAILURES = { blocked: 'blocked', closed: 'closed', meta: 'metaFailed', no_account: 'noAccount' } as const;

const t = useT();
const prepare = useCommand('whatsapp_inbox.channel.prepare');
const connect = useCommand('whatsapp_inbox.channel.connect');
const disconnect = useCommand('whatsapp_inbox.channel.disconnect');
const signup = useMetaSignup((window) => connect.run(window));

const options = ref<ChannelPrepareOut | null>(null);
const done = ref('');
const disconnectOpen = ref(false);

const connectable = computed(() => props.channel.status !== 'connected');
const label = (number: string, name: string) => (name ? `${number} (${name})` : number);

async function ask(): Promise<void> {
  options.value = null;
  try {
    options.value = await prepare.run({});
  } catch {
    // prepare.error says why (erplora.com away, a demo…), with Retry.
  }
}

// Asked when the number is (or becomes) not connected; a connected number only offers «Disconnect».
watch(connectable, (needed) => needed && !options.value && !prepare.pending.value && void ask(), { immediate: true });

const unavailable = computed(() => {
  const reason = options.value && !options.value.available ? options.value.reason : null;
  if (!reason) return '';
  return t(reason === 'not_configured' ? 'whatsapp_inbox.settings.connection.notConfigured' : 'whatsapp_inbox.settings.connection.notYet');
});

const failed = computed(() => {
  const failure = signup.failure.value;
  if (!failure) return '';
  if (failure.reason === 'connect') return failure.message;
  return t(`whatsapp_inbox.settings.connection.${FAILURES[failure.reason]}`, { reason: failure.message });
});

function start(): void {
  if (!options.value?.available) return;
  done.value = '';
  signup.open(options.value);
}

watch(signup.result, (out: ChannelConnectOut | null) => {
  if (!out) return;
  const key = out.history_requested ? 'connectedHistory' : 'connected';
  done.value = t(`whatsapp_inbox.settings.connection.${key}`, { number: label(out.phone_number, out.display_name) });
});

function askDisconnect(): void {
  disconnect.error.value = null;
  disconnectOpen.value = true;
}

async function confirmDisconnect(): Promise<void> {
  let out;
  try {
    out = await disconnect.run({});
  } catch {
    return; // The dialog says why.
  }
  disconnectOpen.value = false;
  done.value = t(out.disconnected ? 'whatsapp_inbox.settings.connection.disconnected' : 'whatsapp_inbox.settings.connection.noNumber');
}
</script>

<template>
  <section
    class="wa-number"
    data-testid="whatsapp-inbox-number"
  >
    <p class="wa-number__line">
      <StatusPill
        size="sm"
        :tone="TONES[channel.status]"
        :label="t(`whatsapp_inbox.settings.${LABELS[channel.status]}`)"
      />
      <strong v-if="channel.phone_number">{{ channel.phone_number }}</strong>
      <span v-if="channel.display_name">{{ channel.display_name }}</span>
    </p>
    <p
      v-if="channel.status === 'not_connected'"
      class="wa-number__hint"
    >
      {{ $t('whatsapp_inbox.settings.notConnectedHint') }}
    </p>
    <p
      v-else-if="channel.status === 'reconnect_needed'"
      class="wa-number__hint"
    >
      {{ $t('whatsapp_inbox.settings.reconnectHint') }}
    </p>

    <template v-if="connectable">
      <p
        v-if="prepare.pending.value"
        class="wa-number__hint"
        data-testid="whatsapp-inbox-number-checking"
      >
        <IonSpinner name="crescent" />
        {{ $t('whatsapp_inbox.settings.connection.checking') }}
      </p>
      <InlineFeedback
        v-else-if="prepare.error.value"
        tone="danger"
        data-testid="whatsapp-inbox-number-error"
      >
        {{ prepare.error.value.message }}
        <template #actions>
          <IonButton
            size="small"
            fill="clear"
            data-testid="whatsapp-inbox-number-retry"
            @click="ask"
          >
            {{ $t('whatsapp_inbox.settings.connection.retry') }}
          </IonButton>
        </template>
      </InlineFeedback>
      <p
        v-else-if="unavailable"
        class="wa-number__hint"
        data-testid="whatsapp-inbox-number-unavailable"
      >
        {{ unavailable }}
      </p>
      <template v-else-if="options?.available">
        <p class="wa-number__hint">
          {{ $t('whatsapp_inbox.settings.connection.hint') }}
        </p>
        <div class="wa-number__actions">
          <IonButton
            data-testid="whatsapp-inbox-number-connect"
            :disabled="signup.step.value !== 'idle'"
            @click="start"
          >
            {{ channel.status === 'reconnect_needed' ? $t('whatsapp_inbox.settings.connection.reconnect') : $t('whatsapp_inbox.settings.connection.connect') }}
          </IonButton>
          <span
            v-if="signup.step.value !== 'idle'"
            class="wa-number__hint"
            data-testid="whatsapp-inbox-number-waiting"
          >{{ signup.step.value === 'waiting' ? $t('whatsapp_inbox.settings.connection.waiting') : $t('whatsapp_inbox.settings.connection.connecting') }}</span>
        </div>
      </template>
    </template>

    <InlineFeedback
      v-if="failed"
      tone="danger"
      data-testid="whatsapp-inbox-number-failed"
    >
      {{ failed }}
    </InlineFeedback>
    <InlineFeedback
      v-if="done"
      tone="success"
      data-testid="whatsapp-inbox-number-done"
    >
      {{ done }}
    </InlineFeedback>

    <div
      v-if="channel.status !== 'not_connected'"
      class="wa-number__actions"
    >
      <IonButton
        color="danger"
        fill="outline"
        data-testid="whatsapp-inbox-number-disconnect"
        @click="askDisconnect"
      >
        {{ $t('whatsapp_inbox.settings.connection.disconnect') }}
      </IonButton>
    </div>
    <ConfirmDialog
      v-model:open="disconnectOpen"
      testid="whatsapp-inbox-number-disconnect-dialog"
      tone="danger"
      :title="t('whatsapp_inbox.settings.connection.disconnectTitle')"
      :message="t('whatsapp_inbox.settings.connection.disconnectMessage', { number: label(channel.phone_number, channel.display_name) })"
      :consequences="[t('whatsapp_inbox.settings.connection.disconnectStays')]"
      :confirm-label="t('whatsapp_inbox.settings.connection.disconnect')"
      :cancel-label="t('whatsapp_inbox.cancel')"
      :pending="disconnect.pending.value"
      :error="disconnect.error.value"
      @confirm="confirmDisconnect"
      @cancel="disconnectOpen = false"
    />
  </section>
</template>

<style scoped>
.wa-number {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.wa-number__line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0;
}
.wa-number__hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-medium-shade);
  margin: 0;
}
.wa-number__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}
</style>
