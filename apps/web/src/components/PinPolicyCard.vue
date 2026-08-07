<!--
  PinPolicyCard — «preguntar quién vende» (Ajustes › Hub), hub#359.

  El segundo control sobre la misma decisión que el modo del dispositivo (hub#358). El modo es del
  DISPOSITIVO —el mostrador y el portátil del despacho conviven en el mismo negocio—; este dial es
  del HUB: una afirmación sobre el negocio entero («aquí se identifica quien vende / aquí no»).
  Existe por el caso que el modo no sabe expresar: la tienda de una sola persona cuyo TPV es
  genuinamente el del mostrador y que aun así no quiere teclear cuatro dígitos para vender.

  Cuatro cosas que no son de estilo:

    - **La consecuencia, no el nombre de la posición.** «Nunca» no le dice nada al dueño de un
      minimercado; «quien abriera la caja por la mañana es el nombre de todas las ventas hasta que
      acabe el turno» sí — y también lo que es fácil omitir y caro descubrir un sábado: el personal
      que solo tiene PIN no podrá entrar. Cada opción lleva su frase debajo, siempre visible.
    - **Solo un administrador escribe**, y no por ocultar el control: `choose` se planta antes de
      llamar al runtime (mismo espejo que `DeviceModeCard`/`RolesPanel`). El runtime revalida
      SIEMPRE (`PUT /api/settings` → `require_admin_session`).
    - **Se pinta lo que confirma el servidor.** Sin optimismo local: un rechazo dejaría la tarjeta
      diciendo lo contrario de lo que va a hacer el hub.
    - **Este dial NO alarga nada.** Cuánto dura la sesión lo compone el runtime con el modo del
      dispositivo y gana el más restrictivo, así que «nunca» renuncia a la ATRIBUCIÓN, jamás al
      candado: la sesión sigue caducando cuando lo dice el dispositivo.

  Reutiliza ion-card/ion-radio-group/ion-radio + ok-inline-feedback (mismo patrón que DeviceModeCard).
-->
<template>
  <ion-card>
    <ion-card-content class="p-0">
      <ion-list lines="none">
        <ion-item lines="none">
          <HubIcon slot="start" name="keypad-outline" />
          <ion-label>
            <h2>{{ t('pinPolicy.title') }}</h2>
            <p>{{ t('pinPolicy.intro') }}</p>
          </ion-label>
        </ion-item>

        <ion-radio-group
          :value="policy"
          :allow-empty-selection="false"
          @ion-change="onPick($event)"
        >
          <ion-item v-for="option in OPTIONS" :key="option.value" lines="none">
            <ion-radio
              :value="option.value"
              :disabled="!isAdmin || saving"
              justify="start"
              label-placement="end"
            >
              <span class="option">
                <span class="option-title">{{ t(option.label) }}</span>
                <span class="option-consequence">{{ t(option.consequence) }}</span>
              </span>
            </ion-radio>
          </ion-item>
        </ion-radio-group>

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
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonCard, IonCardContent, IonItem, IonLabel, IonList, IonNote, IonRadio, IonRadioGroup } from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { getHubSettings, updateHubSettings } from '../lib/hub-settings';
import { parsePinPolicy, pinPolicy, type PinPolicy } from '../lib/pin-policy';
import { isAdmin } from '../lib/session';

const { t } = useI18n();

/**
 * Las tres posiciones, en orden de fricción decreciente. Como lista y no como tres bloques
 * copiados: añadir una cuarta sin su frase de consecuencia sería añadir una opción muda, que es
 * justo lo que esta tarjeta existe para impedir.
 */
const OPTIONS: ReadonlyArray<{ value: PinPolicy; label: string; consequence: string }> = [
  { value: 'always', label: 'pinPolicy.always', consequence: 'pinPolicy.alwaysConsequence' },
  { value: 'per_shift', label: 'pinPolicy.perShift', consequence: 'pinPolicy.perShiftConsequence' },
  { value: 'never', label: 'pinPolicy.never', consequence: 'pinPolicy.neverConsequence' },
];

/** El dial EN VIGOR según el hub. Fuente compartida con la pantalla de login (lib/pin-policy). */
const policy = pinPolicy;
const saving = ref(false);
/** Motivo del último rechazo. Vacío = no hay nada que explicar. */
const rejection = ref('');

/**
 * Registra cada cuánto pregunta el hub. Manda SOLO esta clave: `PUT /api/settings` es parcial, y
 * reenviar el objeto entero desde una tarjeta convertiría cualquier lectura obsoleta en una
 * escritura de todo lo demás.
 */
async function choose(next: PinPolicy): Promise<void> {
  if (!isAdmin.value || saving.value || next === policy.value) return;
  rejection.value = '';
  saving.value = true;
  try {
    // `updateHubSettings` publica en `pinPolicy` lo que CONFIRMA el servidor; aquí no se adivina.
    await updateHubSettings({ pin_policy: next });
  } catch {
    rejection.value = t('pinPolicy.saveError');
  } finally {
    saving.value = false;
  }
}

function onPick(event: Event): void {
  const value = parsePinPolicy((event as CustomEvent<{ value?: string }>).detail?.value);
  if (value) void choose(value);
}

onMounted(() => {
  // Se relee al abrir Ajustes: el dial es del hub y puede haberlo movido otro administrador desde
  // otro dispositivo mientras esta pestaña estaba abierta.
  void getHubSettings().catch(() => undefined);
});

defineExpose({ choose, policy });
</script>

<style scoped>
.option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  white-space: normal;
}
.option-title {
  font-size: 0.9375rem;
  font-weight: 600;
}
.option-consequence {
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
  line-height: 1.35;
}
.note {
  font-size: 0.8125rem;
}
.feedback {
  display: block;
  margin: 0.5rem 0.75rem 0.75rem;
}
</style>
