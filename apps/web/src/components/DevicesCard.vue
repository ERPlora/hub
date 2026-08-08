<!--
  DevicesCard — «se me ha perdido la tablet» (Ajustes › Hub), hub#455.

  El runtime sabía revocar un dispositivo desde hub#15 y nada en el producto podía pedírselo, ni
  siquiera listar los dispositivos para nombrar el que faltaba. Con hub#358 en producción eso tiene
  precio: un dispositivo marcado «personal» lleva una sesión de **30 días** y no pide PIN.

  Cinco cosas que no son de estilo:

    - **Reconocer el dispositivo ES la tarea.** Un id opaco no decide nada, así que cada fila lleva
      el nombre con el que entró, si hay alguien dentro AHORA y cuánto le queda a esa sesión. Y el
      id también: dos cajas pueden llamarse igual.
    - **De qué NO fiarse.** El id y el nombre los elige el propio dispositivo (ADR-0257: el
      navegador se acuña su id; el nombre es el que viajó en el login). Sirven para reconocerlo a
      ojo y para nada más — aquí no se decide nada a partir de ellos.
    - **Nada destructivo con un solo toque.** La confirmación es en la propia fila (no un overlay:
      Ionic los reparenta a `body` y esto se lee mejor donde está la fila) y dice la consecuencia.
    - **La consecuencia REAL, sin prometer de más.** La sesión muere al momento; quitar un
      dispositivo NO es un veto: quien tenga cuenta puede volver a entrar en él. Decir lo contrario
      sería una promesa que el runtime no cumple.
    - **Quitarte a ti mismo se puede** —devolver una tablet, venderla— pero se avisa con otras
      palabras y, al confirmar, se cierra sesión y se va al login: la sesión ya no existe en el
      servidor y quedarse en la pantalla sería fallar en cada toque siguiente.

  Solo un administrador escribe (espejo del gate del runtime, ADR-0248); el runtime revalida SIEMPRE.
-->
<template>
  <ion-card>
    <ion-card-content class="p-0">
      <ion-list lines="none">
        <ion-item lines="none">
          <HubIcon slot="start" name="phone-portrait-outline" />
          <ion-label>
            <h2>{{ t('devices.title') }}</h2>
            <p>{{ t('devices.intro') }}</p>
          </ion-label>
        </ion-item>

        <!-- Un botón que no está y no se explica se lee como una avería; con el motivo es una regla. -->
        <ion-item v-if="!isAdmin" lines="none">
          <ion-note class="note">{{ t('devices.adminOnly') }}</ion-note>
        </ion-item>

        <ion-item v-if="!loading && !loadError && devices.length === 0" lines="none">
          <ion-note class="note">{{ t('devices.empty') }}</ion-note>
        </ion-item>

        <template v-for="device in devices" :key="device.deviceId">
          <ion-item lines="none">
            <ion-label>
              <h3 class="name">
                {{ nameOf(device) }}
                <ion-badge v-if="device.current" color="medium">{{ t('devices.thisDevice') }}</ion-badge>
                <ion-badge color="light">{{ modeOf(device) }}</ion-badge>
              </h3>
              <p class="activity">{{ activityOf(device) }}</p>
              <p v-if="device.signedInUntil" class="activity">
                {{ t('devices.openUntil', { when: when(device.signedInUntil) }) }}
              </p>
              <p class="id">{{ device.deviceId }}</p>
            </ion-label>
            <ion-button
              v-if="isAdmin"
              slot="end"
              fill="clear"
              color="danger"
              :disabled="busy"
              :aria-label="t('devices.revoke')"
              :data-test="`revoke-${device.deviceId}`"
              @click="ask(device.deviceId)"
            >
              <HubIcon slot="icon-only" name="trash-outline" />
            </ion-button>
          </ion-item>

          <!-- La confirmación, en la fila: qué se va a hacer, qué pasa después y —si es este mismo
               dispositivo— que quien confirma se echa a sí mismo. -->
          <ion-item v-if="asking === device.deviceId" lines="none" class="confirm">
            <ion-label>
              <h3>{{ t('devices.confirm') }}</h3>
              <p v-if="device.current" class="warn">{{ t('devices.confirmCurrent') }}</p>
              <p>{{ t('devices.consequence') }}</p>
              <div class="actions">
                <ion-button
                  size="small"
                  color="danger"
                  :disabled="busy"
                  :data-test="`confirm-${device.deviceId}`"
                  @click="revoke(device)"
                >
                  {{ t('devices.revoke') }}
                </ion-button>
                <ion-button
                  size="small"
                  fill="clear"
                  :disabled="busy"
                  :data-test="`cancel-${device.deviceId}`"
                  @click="asking = ''"
                >
                  {{ t('devices.cancel') }}
                </ion-button>
              </div>
            </ion-label>
          </ion-item>
        </template>
      </ion-list>

      <!-- El motivo REAL del último fallo. Banner y no toast: hay que poder releerlo, y confundir
           «no se pudo leer» con «no hay dispositivos» es justo lo que no puede pasar aquí. -->
      <ok-inline-feedback
        v-if="loadError"
        class="feedback"
        tone="danger"
        icon="alert-circle-outline"
      >
        {{ loadError }}
      </ok-inline-feedback>
    </ion-card-content>
  </ion-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import {
  IonBadge,
  IonButton,
  IonCard,
  IonCardContent,
  IonItem,
  IonLabel,
  IonList,
  IonNote,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { DevicesError, listDevices, revokeDevice, type HubDevice } from '../lib/devices';
import { isAdmin, logout } from '../lib/session';

const { t, locale } = useI18n();
const router = useRouter();

const devices = ref<HubDevice[]>([]);
const loading = ref(true);
/** Motivo del último fallo, tal y como lo dio el runtime. Vacío = no hay nada que explicar. */
const loadError = ref('');
/** Id del dispositivo cuya confirmación está abierta. Vacío = ninguna. */
const asking = ref('');
const busy = ref(false);

/** Motivo REAL del fallo, o `fallback` si no hubo ninguno (red/500) — igual que `DeviceModeCard`. */
function reasonOf(error: unknown, fallback: string): string {
  return error instanceof DevicesError && error.message ? error.message : fallback;
}

/**
 * Un dispositivo que nunca dijo cómo se llama sigue teniendo que ser tocable: una fila en blanco se
 * lee como un fallo de pintado, y es la que hay que quitar.
 */
function nameOf(device: HubDevice): string {
  return device.label.trim() || t('devices.unnamed');
}

function modeOf(device: HubDevice): string {
  return device.mode === 'personal' ? t('devices.modePersonal') : t('devices.modeShared');
}

/** Una fecha como la lee una persona, en su idioma. Un ISO crudo no es una señal, es ruido. */
function when(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : at.toLocaleString(locale.value);
}

/**
 * La línea que decide: «hay alguien dentro ahora» es lo que convierte «creo que me lo dejé en algún
 * sitio» en «córtalo». Si no hay nadie, cuándo se usó por última vez.
 */
function activityOf(device: HubDevice): string {
  if (device.openSessions > 0) return t('devices.inUse');
  if (device.lastSignIn) return t('devices.lastUsed', { when: when(device.lastSignIn) });
  return t('devices.neverUsed', { when: when(device.trustedAt) });
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    devices.value = await listDevices();
    loadError.value = '';
  } catch (error) {
    // La lista NO se vacía en un fallo: dejarla vacía diría «no hay dispositivos» a quien está
    // buscando el que le han robado.
    loadError.value = reasonOf(error, t('devices.loadError'));
  } finally {
    loading.value = false;
  }
}

function ask(deviceId: string): void {
  if (!isAdmin.value) return;
  loadError.value = '';
  asking.value = deviceId;
}

async function revoke(device: HubDevice): Promise<void> {
  if (!isAdmin.value || busy.value) return;
  busy.value = true;
  try {
    const outcome = await revokeDevice(device.deviceId);
    asking.value = '';
    if (outcome.wasCurrent) {
      // La sesión que usaba esta pantalla ya no existe en el servidor: quedarse aquí sería fallar
      // en cada toque siguiente con un error de autenticación que nadie puede accionar.
      logout();
      await router.replace('/login');
      return;
    }
    // Se recarga, no se parchea en local: manda lo que dice el hub, y los contadores de las otras
    // filas también han podido moverse.
    await load();
  } catch (error) {
    loadError.value = reasonOf(error, t('devices.revokeError'));
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  void load();
});

defineExpose({ load, revoke, devices });
</script>

<style scoped>
.name {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-wrap: wrap;
}
.activity {
  font-size: 0.8125rem;
}
.id {
  font-size: 0.75rem;
  color: var(--ion-color-medium);
  word-break: break-all;
}
.note {
  font-size: 0.8125rem;
}
.warn {
  color: var(--ion-color-danger);
}
.actions {
  display: flex;
  gap: 0.25rem;
  margin-top: 0.25rem;
}
.feedback {
  display: block;
  margin: 0.5rem 0.75rem 0.75rem;
}
</style>
