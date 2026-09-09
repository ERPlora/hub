<!--
  DeviceModeCard — «este dispositivo» (Ajustes › Hub), hub#358.

  Dónde vive la decisión de si la caja pide PIN. El modo es del DISPOSITIVO, no del hub (hub#357):
  el mismo negocio tiene el TPV del mostrador —donde varias personas se turnan— y el portátil del
  despacho, y la misma persona usa los dos.

  Tres cosas que no son de estilo:

    - **La consecuencia, no el nombre del modo.** «Personal» no le dice nada al dueño de un bar;
      «la sesión se queda abierta: quien coja este dispositivo ya eres tú» sí. Cada opción lleva su
      frase debajo, siempre visible — no en un tooltip ni en un modal de confirmación que nadie lee.
    - **Solo un administrador escribe**, y no por ocultar el control: `choose` se planta antes de
      llamar al runtime (mismo espejo que `RolesPanel.setActive`). El runtime revalida SIEMPRE.
    - **Se pinta lo que confirma el servidor.** Sin optimismo local: un rechazo dejaría la tarjeta
      diciendo lo contrario de lo que va a hacer el dispositivo que tienes delante.

  Reutiliza ion-card/ion-radio-group/ion-radio + ok-inline-feedback (mismo patrón que RolesPanel).
-->
<template>
  <ion-card>
    <ion-card-content class="p-0">
      <ion-list lines="none">
        <ion-item lines="none">
          <HubIcon slot="start" name="tablet-portrait-outline" />
          <ion-label>
            <h2>{{ t('deviceMode.title') }}</h2>
            <p>{{ t('deviceMode.intro') }}</p>
          </ion-label>
        </ion-item>

        <ion-radio-group
          :value="mode"
          :allow-empty-selection="false"
          @ion-change="onPick($event)"
        >
          <ion-item lines="none">
            <ion-radio :value="'shared'" :disabled="!isAdmin || saving" justify="start" label-placement="end">
              <span class="option">
                <span class="option-title">{{ t('deviceMode.shared') }}</span>
                <span class="option-consequence">{{ t('deviceMode.sharedConsequence') }}</span>
              </span>
            </ion-radio>
          </ion-item>
          <ion-item lines="none">
            <ion-radio :value="'personal'" :disabled="!isAdmin || saving" justify="start" label-placement="end">
              <span class="option">
                <span class="option-title">{{ t('deviceMode.personal') }}</span>
                <span class="option-consequence">{{ t('deviceMode.personalConsequence') }}</span>
              </span>
            </ion-radio>
          </ion-item>
        </ion-radio-group>

        <!-- Un control deshabilitado y mudo se lee como una avería; con el motivo es una regla. -->
        <ion-item v-if="!isAdmin" lines="none">
          <ion-note class="note">{{ t('deviceMode.adminOnly') }}</ion-note>
        </ion-item>
      </ion-list>

      <!-- El motivo REAL del último rechazo. Banner y no toast: es accionable («entra online una
           vez en ese dispositivo») y hay que poder releerlo. -->
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
import {
  DeviceModeError,
  deviceMode,
  loadDeviceMode,
  setDeviceMode,
  type DeviceMode,
} from '../lib/device-mode';
import { isAdmin } from '../lib/session';

const { t } = useI18n();

/** El modo EN VIGOR según el hub. Fuente compartida con la pantalla de login (lib/device-mode). */
const mode = deviceMode;
const saving = ref(false);
/** Motivo del último rechazo, tal y como lo dio el runtime. Vacío = no hay nada que explicar. */
const rejection = ref('');

/** Motivo REAL del rechazo, o `fallback` si no hubo ninguno (red/500) — igual que `RolesPanel`. */
function reasonOf(error: unknown, fallback: string): string {
  return error instanceof DeviceModeError && error.code && error.message ? error.message : fallback;
}

/**
 * Registra qué clase de dispositivo es este. Sin `device_id`: describe el dispositivo que hace la
 * petición («este dispositivo es mío», desde el propio dispositivo). Nombrar otro desde aquí sería
 * poder apagarle el pinpad a una caja que no tienes delante.
 */
async function choose(next: DeviceMode): Promise<void> {
  if (!isAdmin.value || saving.value || next === mode.value) return;
  rejection.value = '';
  saving.value = true;
  try {
    // `setDeviceMode` publica el modo que CONFIRMA el servidor en `deviceMode`; aquí no se adivina.
    await setDeviceMode(next);
  } catch (error) {
    rejection.value = reasonOf(error, t('deviceMode.saveError'));
  } finally {
    saving.value = false;
  }
}

function onPick(event: Event): void {
  const value = (event as CustomEvent<{ value?: string }>).detail?.value;
  if (value === 'shared' || value === 'personal') void choose(value);
}

onMounted(() => {
  void loadDeviceMode();
});

defineExpose({ choose, mode });
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
