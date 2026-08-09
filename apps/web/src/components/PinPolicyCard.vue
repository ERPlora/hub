<!--
  PinPolicyCard — «Show PIN pad» (Ajustes › Hub). hub#628, rediseño de la tarjeta de hub#359.

  Dos controles sobre el MISMO wire cerrado (`pin_policy`, más `pin_inactivity_minutes`):

    - **Toggle «Show PIN pad»** — ¿este negocio identifica a quien vende? OFF = `never`; volverlo
      a encender escribe `per_shift` (el default del runtime), nunca una adivinanza de los minutos
      que hubiera antes.
    - **Range de inactividad** (solo con el toggle ON) — 1 · 5 · 10 · 15 · 30 · «hasta cerrar
      sesión». Una parada de minutos escribe `always` + los minutos: una caja que nadie toca ese
      tiempo cierra la sesión y vuelve al pinpad (el detector vive en lib/idle-logout, solo en
      dispositivos `shared`). La última parada escribe `per_shift`: sin bloqueo por inactividad.

  El mapping control↔wire es lib/pinpad-dial (puro, testeado aparte). Lo que esta tarjeta conserva
  del diseño anterior no es estilo:

    - **La consecuencia, siempre visible.** Un toggle OFF a secas no le dice nada al dueño de un
      minimercado; «quien abriera la caja por la mañana es el nombre de todas las ventas» sí — y
      también lo caro de descubrir un sábado: el personal que solo tiene PIN no podrá entrar.
    - **Solo un administrador escribe**: el handler se planta antes de llamar al runtime (mismo
      espejo que `DeviceModeCard`). El runtime revalida SIEMPRE (`PUT /api/settings`).
    - **Se pinta lo que confirma el servidor.** Sin optimismo local: un rechazo dejaría la tarjeta
      diciendo lo contrario de lo que va a hacer el hub.
    - **Este dial NO alarga nada**: la sesión sigue componiéndose con el modo del dispositivo por
      el lado restrictivo, en el runtime.
-->
<template>
  <ion-card>
    <ion-card-content class="p-0">
      <ion-list lines="none">
        <ion-item lines="none">
          <HubIcon slot="start" name="keypad-outline" />
          <ion-label>
            <h2>{{ t('pinPolicy.showPinpad') }}</h2>
            <p>{{ t('pinPolicy.intro') }}</p>
          </ion-label>
          <ion-toggle
            slot="end"
            :checked="pinpadOn"
            :disabled="!isAdmin || saving"
            :aria-label="t('pinPolicy.showPinpad')"
            @ion-change="onToggle($event)"
          />
        </ion-item>

        <!-- La consecuencia de la posición EN VIGOR, no un tooltip: siempre visible. -->
        <ion-item lines="none">
          <ion-note class="note">
            {{ pinpadOn ? t('pinPolicy.onConsequence') : t('pinPolicy.offConsequence') }}
          </ion-note>
        </ion-item>

        <template v-if="pinpadOn">
          <ion-item lines="none">
            <ion-label>
              <h2>{{ t('pinPolicy.idleTitle') }}</h2>
              <p>{{ idleValueLabel }}</p>
            </ion-label>
          </ion-item>
          <ion-item lines="none">
            <ion-range
              :min="0"
              :max="UNTIL_SIGN_OUT_STOP"
              :step="1"
              :snaps="true"
              :ticks="true"
              :value="stop"
              :disabled="!isAdmin || saving"
              :aria-label="t('pinPolicy.idleTitle')"
              @ion-change="onRange($event)"
            />
          </ion-item>
          <ion-item lines="none">
            <ion-note class="note">{{ idleConsequence }}</ion-note>
          </ion-item>
        </template>

        <!-- Un control deshabilitado y mudo se lee como una avería; con el motivo es una regla. -->
        <ion-item v-if="!isAdmin" lines="none">
          <ion-note class="note">{{ t('pinPolicy.adminOnly') }}</ion-note>
        </ion-item>
      </ion-list>

      <ok-inline-feedback
        v-if="rejection"
        class="feedback"
        tone="danger"
        icon="alert-circle-outline"
      >
        {{ rejection }}
      </ok-inline-feedback>
    </ion-card-content>
  </ion-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonCard,
  IonCardContent,
  IonItem,
  IonLabel,
  IonList,
  IonNote,
  IonRange,
  IonToggle,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { getHubSettings, hubSettings, updateHubSettings } from '../lib/hub-settings';
import { idleMinutesOf } from '../lib/idle-logout';
import { asksForPin, pinPolicy } from '../lib/pin-policy';
import {
  IDLE_STOPS,
  UNTIL_SIGN_OUT_STOP,
  stopFromWire,
  wireFromStop,
  wireFromToggle,
  type PinpadWire,
} from '../lib/pinpad-dial';
import { isAdmin } from '../lib/session';

const { t } = useI18n();

/** El dial EN VIGOR según el hub. Fuente compartida con la pantalla de login (lib/pin-policy). */
const policy = pinPolicy;
const saving = ref(false);
/** Motivo del último rechazo. Vacío = no hay nada que explicar. */
const rejection = ref('');

/** ¿Se ofrece el pinpad? (`never` es la única posición que dice que no.) */
const pinpadOn = computed(() => asksForPin(policy.value));

/** Dónde está el mango del range para lo que el hub CONFIRMÓ (nunca para lo que se pidió). */
const stop = computed(() => stopFromWire(policy.value, idleMinutesOf(hubSettings.value)));

const idleValueLabel = computed(() =>
  stop.value === UNTIL_SIGN_OUT_STOP
    ? t('pinPolicy.idleUntilSignOut')
    : t('pinPolicy.idleMinutes', { n: IDLE_STOPS[stop.value] }),
);

const idleConsequence = computed(() =>
  stop.value === UNTIL_SIGN_OUT_STOP
    ? t('pinPolicy.idleUntilSignOutConsequence')
    : t('pinPolicy.idleMinutesConsequence', { n: IDLE_STOPS[stop.value] }),
);

/**
 * Registra un cambio. Manda SOLO las claves del dial: `PUT /api/settings` es parcial, y reenviar
 * el objeto entero desde una tarjeta convertiría cualquier lectura obsoleta en una escritura de
 * todo lo demás. `updateHubSettings` publica lo que CONFIRMA el servidor; aquí no se adivina.
 */
async function apply(wire: PinpadWire): Promise<void> {
  if (!isAdmin.value || saving.value) return;
  rejection.value = '';
  saving.value = true;
  try {
    await updateHubSettings(wire);
  } catch {
    rejection.value = t('pinPolicy.saveError');
  } finally {
    saving.value = false;
  }
}

/** El toggle: OFF = `never`; ON = el default del runtime (`per_shift`). */
async function setPinpad(on: boolean): Promise<void> {
  if (on === pinpadOn.value) return;
  await apply(wireFromToggle(on));
}

/** Una parada del range: minutos → `always` + minutos; la última → `per_shift`. */
async function chooseStop(next: number): Promise<void> {
  if (next === stop.value) return;
  await apply(wireFromStop(next));
}

function onToggle(event: Event): void {
  void setPinpad((event as CustomEvent<{ checked: boolean }>).detail.checked);
}

function onRange(event: Event): void {
  const value = (event as CustomEvent<{ value?: number | { lower: number; upper: number } }>)
    .detail?.value;
  if (typeof value === 'number') void chooseStop(value);
}

onMounted(() => {
  // Se relee al abrir Ajustes: el dial es del hub y puede haberlo movido otro administrador desde
  // otro dispositivo mientras esta pestaña estaba abierta.
  void getHubSettings().catch(() => undefined);
});

defineExpose({ setPinpad, chooseStop, policy, stop });
</script>

<style scoped>
.note {
  font-size: 0.8125rem;
  line-height: 1.35;
  white-space: normal;
}
.feedback {
  display: block;
  margin: 0.5rem 0.75rem 0.75rem;
}
</style>
