<!--
  DevicesCard — «se me ha perdido la tablet» (Ajustes › Hub), hub#455.

  El runtime sabía revocar un dispositivo desde hub#15 y nada en el producto podía pedírselo, ni
  siquiera listar los dispositivos para nombrar el que faltaba. Con hub#358 en producción eso tiene
  precio: un dispositivo marcado «personal» lleva una sesión de **30 días** y no pide PIN.

  Cinco cosas que no son de estilo:

    - **Recognising the device IS the task.** An opaque id decides nothing, so each row carries
      the name it was given, whether somebody is on it RIGHT NOW and how long that session has
      left. The id itself is never painted (hub#2203): it is 128 random bits nobody can read, it
      ended up in every screenshot, and two rows that look alike are told apart by the name the
      business gives them and by their dates — the way Google, Apple or Shopify list devices.
    - **De qué NO fiarse, y de qué sí.** El id y la etiqueta los elige el propio dispositivo
      (ADR-0257: el navegador se acuña su id; la etiqueta es el nombre de la persona que viajó en el
      login, reescrito en cada entrada). Sirven para reconocerlo a ojo y para nada más. Lo único de
      la fila que decide el NEGOCIO es el `name` (hub#494) — lo escribe un administrador, el login
      no lo toca jamás — y por eso es lo que titula la fila y lo que hay que mirar al cortar.
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
  <ion-card data-testid="devices-card">
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
          <ion-note class="note" data-testid="devices-admin-only">{{ t('devices.adminOnly') }}</ion-note>
        </ion-item>

        <ion-item v-if="!loading && !loadError && devices.length === 0" lines="none">
          <ion-note class="note" data-testid="devices-empty">{{ t('devices.empty') }}</ion-note>
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
              <!-- Quién entró la última vez: una PISTA, y dicha como tal. Lo elige el cliente (viaja
                   en el cuerpo del login) y cambia de turno en turno, así que no puede titular la
                   fila — que es justo lo que hacía antes de hub#494. -->
              <p v-if="device.label.trim()" class="activity">
                {{ t('devices.lastSignedInBy', { who: device.label.trim() }) }}
              </p>
            </ion-label>
            <ion-button
              v-if="isAdmin"
              slot="end"
              fill="clear"
              :disabled="busy"
              :aria-label="t('devices.rename')"
              :data-testid="`devices-rename-${device.deviceId}`"
              @click="startNaming(device)"
            >
              <HubIcon slot="icon-only" name="create-outline" />
            </ion-button>
            <ion-button
              v-if="isAdmin"
              slot="end"
              fill="clear"
              color="danger"
              :disabled="busy"
              :aria-label="t('devices.revoke')"
              :data-testid="`devices-revoke-${device.deviceId}`"
              @click="ask(device.deviceId)"
            >
              <HubIcon slot="icon-only" name="trash-outline" />
            </ion-button>
          </ion-item>

          <!-- Ponerle nombre, en la propia fila: es el gesto que hace que señalar el dispositivo
               correcto sea fácil, así que vive donde está el dispositivo. Deliberadamente lejos, en
               gesto y en color, del botón que lo corta. -->
          <ion-item v-if="naming === device.deviceId" lines="none" class="confirm">
            <ion-label>
              <p>{{ t('devices.nameLabel') }}</p>
              <ion-input
                mode="md"
                fill="outline"
                :maxlength="MAX_DEVICE_NAME"
                :aria-label="t('devices.rename')"
                :value="draftName"
                :data-testid="`devices-name-${device.deviceId}`"
                @ionInput="onType"
              />
              <div class="actions">
                <ion-button
                  size="small"
                  :disabled="busy"
                  :data-testid="`devices-save-name-${device.deviceId}`"
                  @click="rename(device)"
                >
                  {{ t('devices.save') }}
                </ion-button>
                <ion-button
                  size="small"
                  fill="clear"
                  :disabled="busy"
                  :data-testid="`devices-cancel-name-${device.deviceId}`"
                  @click="naming = ''"
                >
                  {{ t('devices.cancel') }}
                </ion-button>
              </div>
            </ion-label>
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
                  :data-testid="`devices-confirm-${device.deviceId}`"
                  @click="revoke(device)"
                >
                  {{ t('devices.revoke') }}
                </ion-button>
                <ion-button
                  size="small"
                  fill="clear"
                  :disabled="busy"
                  :data-testid="`devices-cancel-${device.deviceId}`"
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
        data-testid="devices-error"
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
  IonInput,
  IonItem,
  IonLabel,
  IonList,
  IonNote,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import {
  listDevices,
  renameDevice,
  revokeDevice,
  type HubDevice,
} from '../lib/devices';
import { localDoorSentence } from '../lib/runtime-error-sentence';
import { isAdmin, logout } from '../lib/session';
import { formatDateTime } from '../lib/format-datetime';

const { t, te, locale } = useI18n();
const router = useRouter();

const devices = ref<HubDevice[]>([]);
const loading = ref(true);
/** Motivo del último fallo, tal y como lo dio el runtime. Vacío = no hay nada que explicar. */
const loadError = ref('');
/** Id del dispositivo cuya confirmación está abierta. Vacío = ninguna. */
const asking = ref('');
/** Id del dispositivo al que se le está poniendo nombre (hub#494). Vacío = ninguno. */
const naming = ref('');
/** Lo tecleado en ese momento. */
const draftName = ref('');
const busy = ref(false);

/**
 * El mismo tope que impone la puerta (`crates/server/src/devices.rs`). Aquí no es la regla —el
 * runtime revalida— sino evitar que alguien escriba un párrafo y se lo rechacen al guardar.
 */
const MAX_DEVICE_NAME = 60;

/** Motivo REAL del fallo, o `fallback` si no hubo ninguno (red/500) — igual que `DeviceModeCard`. */
/**
 * hub#1697 — a local door's words never reach the business. The door answers a stable code next to
 * English prose meant for the log, so the code is what gets a sentence and the prose stays behind.
 * Class-agnostic on purpose: what matters is that a code arrived, not which class wrapped it.
 */
function reasonOf(error: unknown, fallback: string): string {
  return localDoorSentence(error, { t, te }, ['devices.errors', 'runtimeErrors'], fallback);
}

/**
 * El título de la fila es el nombre que puso el NEGOCIO (hub#494) — lo único de la fila que no
 * eligió el propio dispositivo. Si nadie lo ha nombrado todavía se dice así: una fila en blanco se
 * lee como un fallo de pintado, y ponerle el nombre de la persona que entró es justo la mentira que
 * hacía imposible señalar la tablet correcta.
 */
function nameOf(device: HubDevice): string {
  return device.name.trim() || t('devices.unnamed');
}

function modeOf(device: HubDevice): string {
  return device.mode === 'personal' ? t('devices.modePersonal') : t('devices.modeShared');
}

/** Una fecha como la lee una persona, en su idioma y en el RELOJ DEL NEGOCIO (hub#1212). */
function when(iso: string): string {
  return formatDateTime(iso, { locale: locale.value }) ?? iso;
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
  // Nunca las dos cosas abiertas a la vez: la confirmación de quitar y el campo del nombre en la
  // misma fila serían dos botones primarios con consecuencias muy distintas.
  naming.value = '';
  asking.value = deviceId;
}

/** Abre el campo con el nombre que ya tiene, para corregir en vez de reescribir. */
function startNaming(device: HubDevice): void {
  if (!isAdmin.value) return;
  loadError.value = '';
  asking.value = '';
  draftName.value = device.name;
  naming.value = device.deviceId;
}

function onType(event: Event): void {
  const typed = (event as CustomEvent<{ value?: string | null }>).detail?.value;
  draftName.value = typeof typed === 'string' ? typed : '';
}

/**
 * Guarda el nombre. Se recarga desde el hub en vez de parchear la fila: manda lo que el hub guardó
 * (recortado por él), igual que en la revocación. Y un fallo se DICE — un nombre que solo cambió en
 * la pantalla es exactamente la clase de mentira que esta tarjeta existe para no contar.
 */
async function rename(device: HubDevice): Promise<void> {
  if (!isAdmin.value || busy.value) return;
  busy.value = true;
  try {
    await renameDevice(device.deviceId, draftName.value);
    naming.value = '';
    await load();
  } catch (error) {
    loadError.value = reasonOf(error, t('devices.renameError'));
  } finally {
    busy.value = false;
  }
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

defineExpose({ load, ask, revoke, startNaming, rename, devices });
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
