<template>
  <div class="grant-panel">
    <!-- Estado primero: lo que la persona necesita saber antes de decidir si tiene que firmar. -->
    <ion-item lines="none" class="grant-state" :data-testid="`grant-state-${status || 'unknown'}`">
      <HubIcon slot="start" :name="stateIcon" />
      <ion-label>
        <p v-if="status === 'vigente'">{{ t('grant.stateVigente', { date: atLabel }) }}</p>
        <p v-else-if="status === 'revocado'">{{ t('grant.stateRevoked', { date: atLabel }) }}</p>
        <p v-else-if="status === 'absent'">{{ t('grant.stateAbsent') }}</p>
        <p v-else>{{ t('grant.stateUnknown') }}</p>
      </ion-label>
    </ion-item>

    <ion-note class="grant-intro">{{ t('grant.intro') }}</ion-note>

    <!-- 🔴 El texto ENTERO, no un enlace. La FAQ de la AEAT (v1.3 §16.4) admite el formulario web
         pero exige «la cumplimentación y firma» del otorgamiento: quien firma tiene que poder leer
         lo que firma sin salir de aquí. Lo sirve el runtime, que es quien lo archiva. -->
    <div class="grant-anexo" data-testid="grant-anexo">
      <pre v-if="anexoText">{{ filledAnexo }}</pre>
      <ion-spinner v-else />
    </div>

    <template v-if="isAdmin">
      <!-- El obligado sale del perfil fiscal del Hub y se lee, no se escribe: es lo que ancla la
           cadena y viaja como `IDEmisorFactura`. Se cambia en la identidad fiscal, no aquí. -->
      <ion-input
        class="mt-2"
        mode="md"
        fill="outline"
        label-placement="floating"
        readonly
        data-testid="grant-obligado-nif"
        :label="t('grant.obligadoNif')"
        :value="obligadoNif"
      />
      <ion-input
        class="mt-2"
        mode="md"
        fill="outline"
        label-placement="floating"
        readonly
        data-testid="grant-obligado-name"
        :label="t('grant.obligadoName')"
        :value="obligadoName"
      />

      <!-- El FIRMANTE es una persona: en una empresa, su representante legal. La copia del DNI
           que se pide abajo es la SUYA, no la de la sociedad. -->
      <ion-input
        class="mt-3"
        mode="md"
        fill="outline"
        label-placement="floating"
        :label="t('grant.signerNif')"
        data-testid="grant-signer-nif"
        v-model="signerNif"
        placeholder="12345678Z"
      />
      <ion-input
        class="mt-2"
        mode="md"
        fill="outline"
        label-placement="floating"
        :label="t('grant.signerName')"
        data-testid="grant-signer-name"
        v-model="signerName"
      />

      <!-- La FIRMA: un trazo, no una casilla. -->
      <ion-label class="grant-label">
        <h3>{{ t('grant.signatureTitle') }}</h3>
        <p>{{ t('grant.signatureHint') }}</p>
      </ion-label>
      <canvas
        ref="canvasEl"
        class="grant-canvas"
        data-testid="grant-canvas"
        width="600"
        height="200"
        @pointerdown="startStroke"
        @pointermove="moveStroke"
        @pointerup="endStroke"
        @pointerleave="endStroke"
      ></canvas>
      <ion-button fill="clear" size="small" data-testid="grant-clear" @click="clearSignature">
        <HubIcon slot="start" name="refresh-outline" />
        {{ t('grant.signatureClear') }}
      </ion-button>

      <!-- Copia del DNI/NIE del firmante: ERPlora responde de su autenticidad. -->
      <input
        ref="dniInput"
        type="file"
        accept="image/*,.pdf"
        class="grant-file-input"
        data-testid="grant-dni-input"
        @change="onDniChange"
      />
      <ion-button
        expand="block"
        fill="outline"
        class="mt-2"
        data-testid="grant-dni-pick"
        @click="pickDni"
      >
        <HubIcon slot="start" name="document-attach-outline" />
        {{ dniFile?.name || t('grant.dniChoose') }}
      </ion-button>

      <!-- Confirmación explícita. NO sustituye a la firma: la acompaña. -->
      <ion-item lines="none" class="mt-2">
        <ion-checkbox
          justify="start"
          label-placement="end"
          data-testid="grant-confirm"
          :checked="confirmed"
          @ionChange="confirmed = $event.detail.checked"
        >
          {{ t('grant.confirm') }}
        </ion-checkbox>
      </ion-item>

      <ion-button
        expand="block"
        class="mt-3"
        data-testid="grant-submit"
        :disabled="!canSubmit || busy"
        @click="submit()"
      >
        <HubIcon slot="start" name="create-outline" />
        {{ t('grant.submit') }}
      </ion-button>

      <ion-note v-if="error" color="danger" class="grant-error" data-testid="grant-error">
        {{ error }}
      </ion-note>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * **Donde el cliente FIRMA el otorgamiento de representación** (hub#817).
 *
 * ERPlora remite los registros VERI\*FACTU **en nombre del** obligado, y para eso hace falta su
 * consentimiento firmado (Anexo I de la Resolución DG AEAT de 18/12/2024). Hasta ahora la única
 * forma de crearlo era llamar a la API a mano: un mecanismo sin puerta.
 *
 * Tres cosas que este componente NO hace, y son el diseño:
 *
 * 1. **No habla con el SaaS.** Llama a una ruta del runtime, y es el runtime quien pone el
 *    `X-Hub-Token` — que es secreto suyo y nunca cruza a este navegador (ADR-0003).
 * 2. **No compone el documento.** Manda el TRAZO; el otorgamiento cumplimentado lo monta el
 *    runtime, así que lo que se archiva contiene siempre el texto del Anexo I de verdad.
 * 3. **No se queda nada.** Trazo y DNI se olvidan en cuanto salen — la custodia es del SaaS
 *    (RGPD), y una copia aquí sería una copia en cada backup y en cada blueprint exportado.
 */
import { ref, computed, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
// hub#797 — los `ion-*` se IMPORTAN. Este componente no importaba ninguno: funcionaba solo porque
// otra pantalla ya montada los había registrado antes, así que abrirlo el primero (deep-link,
// recarga en esta ruta) lo dejaba pintando etiquetas desconocidas. En una pantalla donde se FIRMA
// el otorgamiento del certificado fiscal, eso no es un detalle de estilo.
import {
  IonButton,
  IonCheckbox,
  IonInput,
  IonItem,
  IonLabel,
  IonNote,
  IonSpinner,
} from '@ionic/vue';
import { getRepresentationGrant, postRepresentationGrant } from '../lib/runtime';
import { isAdmin } from '../lib/session';
import HubIcon from './HubIcon.vue';
import { formatDate } from '../lib/format-datetime';

const props = defineProps<{ obligadoNif: string; obligadoName: string }>();
const emit = defineEmits<{ (e: 'signed'): void }>();
const { t, locale } = useI18n();

/** `''` = todavía no se sabe (cargando, o el runtime no contestó). Nunca se inventa. */
const status = ref('');
const at = ref('');
const anexoText = ref('');

const signerNif = ref('');
const signerName = ref('');
/** El trazo, como data-URL PNG. `''` = sin firmar. */
const signature = ref('');
const dniFile = ref<File | null>(null);
const confirmed = ref(false);
const busy = ref(false);
const error = ref('');

const canvasEl = ref<HTMLCanvasElement | null>(null);
const dniInput = ref<HTMLInputElement | null>(null);
let drawing = false;

const stateIcon = computed(() =>
  status.value === 'vigente' ? 'shield-checkmark-outline' : 'shield-outline',
);

const atLabel = computed(() => {
  if (!at.value) return '';
  return formatDate(at.value, { locale: locale.value }) ?? at.value;
});

/** El texto tal y como lo va a archivar el runtime, con las partes ya puestas. */
const filledAnexo = computed(() =>
  anexoText.value
    .replace('{signer_name}', signerName.value || '…')
    .replace('{signer_nif}', signerNif.value || '…')
    .replace('{obligado_name}', props.obligadoName || '…')
    .replace('{obligado_nif}', props.obligadoNif || '…'),
);

/**
 * 🔴 **Los cuatro a la vez, y una casilla no sustituye a ninguno.** La FAQ v1.3 §16.4 prohíbe la
 * aceptación de condiciones SIN firma, así que el trazo es obligatorio; y el representante responde
 * de la copia del DNI, así que también.
 */
const canSubmit = computed(
  () =>
    // Las dos mitades del obligado: el Anexo I lo identifica por NIF **y** por razón social, así
    // que con el nombre vacío se archivaría una prueba legal a medio rellenar.
    !!props.obligadoNif.trim() &&
    !!props.obligadoName.trim() &&
    !!signerNif.value.trim() &&
    !!signerName.value.trim() &&
    !!signature.value &&
    !!dniFile.value &&
    confirmed.value,
);

async function load() {
  try {
    const state = await getRepresentationGrant();
    status.value = state.status;
    at.value = state.at;
    anexoText.value = state.anexo_text;
  } catch {
    // Sin respuesta no se pinta un estado: «no lo sé» y «no has firmado» no son lo mismo, y
    // enseñar el segundo cuando pasa el primero manda a alguien a firmar dos veces.
    status.value = '';
  }
}

onMounted(load);

// ── La firma ──────────────────────────────────────────────────────────────────────────────────

function ctx(): CanvasRenderingContext2D | null {
  const canvas = canvasEl.value;
  return canvas ? canvas.getContext('2d') : null;
}

function pointAt(event: PointerEvent): [number, number] {
  const canvas = canvasEl.value!;
  const box = canvas.getBoundingClientRect();
  return [
    ((event.clientX - box.left) / box.width) * canvas.width,
    ((event.clientY - box.top) / box.height) * canvas.height,
  ];
}

function startStroke(event: PointerEvent) {
  const context = ctx();
  if (!context) return;
  drawing = true;
  context.lineWidth = 2;
  context.lineCap = 'round';
  context.strokeStyle = '#000';
  context.beginPath();
  context.moveTo(...pointAt(event));
}

function moveStroke(event: PointerEvent) {
  const context = ctx();
  if (!drawing || !context) return;
  context.lineTo(...pointAt(event));
  context.stroke();
}

function endStroke() {
  if (!drawing) return;
  drawing = false;
  signature.value = canvasEl.value?.toDataURL('image/png') ?? '';
}

function clearSignature() {
  const canvas = canvasEl.value;
  ctx()?.clearRect(0, 0, canvas?.width ?? 0, canvas?.height ?? 0);
  signature.value = '';
}

// ── La copia del DNI ──────────────────────────────────────────────────────────────────────────

function pickDni() {
  dniInput.value?.click();
}

function onDniChange(event: Event) {
  dniFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

// ── El envío ──────────────────────────────────────────────────────────────────────────────────

/** El data-URL del canvas, como bytes. Lo que viaja es la imagen, no la cadena. */
function signatureBlob(): Blob {
  const [, base64] = signature.value.split(',');
  const binary = atob(base64 ?? '');
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: 'image/png' });
}

async function submit() {
  if (!canSubmit.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const state = await postRepresentationGrant({
      obligado_nif: props.obligadoNif,
      obligado_name: props.obligadoName,
      signer_nif: signerNif.value.trim(),
      signer_name: signerName.value.trim(),
      signature: signatureBlob(),
      dni_copy: dniFile.value!,
    });
    status.value = state.status;
    at.value = state.at;
    // 🔒 Se olvidan AQUÍ, en el camino de éxito y solo en él: si el envío falla, lo que la persona
    // acaba de rellenar sigue en pantalla en vez de obligarla a firmar otra vez.
    clearSignature();
    dniFile.value = null;
    if (dniInput.value) dniInput.value.value = '';
    confirmed.value = false;
    emit('signed');
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

// El canvas se dimensiona con CSS; si el panel se muestra después de montarse, hay que limpiarlo
// para que el trazo no herede una escala vieja.
watch(canvasEl, (canvas) => {
  if (canvas) clearSignature();
});

defineExpose({ status, at, anexoText, signerNif, signerName, signature, dniFile, confirmed, canSubmit, submit });
</script>

<style scoped>
.grant-intro {
  display: block;
  margin: 0.5rem 0;
}

/* El documento se lee: ancho contenido, scroll propio y monoespaciado no — es prosa legal. */
.grant-anexo {
  max-height: 18rem;
  overflow-y: auto;
  padding: 0.75rem;
  border: 1px solid var(--ion-color-step-150, #e0e0e0);
  border-radius: 8px;
  background: var(--ion-color-step-50, #fafafa);
}

.grant-anexo pre {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: inherit;
  font-size: 0.85rem;
  line-height: 1.5;
}

.grant-label {
  display: block;
  margin-top: 1rem;
}

/* El lienzo de firma: ancho completo y alto fijo, para que quepa el trazo en móvil y en escritorio.
   `touch-action: none` es lo que impide que arrastrar el dedo haga scroll en vez de firmar. */
.grant-canvas {
  display: block;
  width: 100%;
  height: 10rem;
  margin-top: 0.5rem;
  border: 1px dashed var(--ion-color-step-250, #c0c0c0);
  border-radius: 8px;
  background: #fff;
  touch-action: none;
  cursor: crosshair;
}

.grant-file-input {
  display: none;
}

/* 🔴 La confirmación se LEE ENTERA o no es una confirmación. `ion-checkbox` trunca su etiqueta con
   ellipsis por defecto, y a 390 px eso dejaba «He leído el otorgamiento de arrib…» — la mitad de la
   frase que la persona está declarando haber leído. Detectado en la QA visual de los 3 viewports. */
.grant-panel ion-checkbox::part(label) {
  white-space: normal;
  overflow: visible;
  text-overflow: unset;
}

.grant-error {
  display: block;
  margin-top: 0.5rem;
}
</style>
