<template>
  <div class="grant-panel">
    <!-- Estado primero: lo que la persona necesita saber antes de decidir si tiene que hacer nada. -->
    <ion-item lines="none" class="grant-state" :data-testid="`grant-state-${status || 'unknown'}`">
      <HubIcon slot="start" :name="stateIcon" />
      <ion-label class="grant-state-label">
        <p v-if="status === 'vigente'">{{ t('grant.stateVigente', { date: atLabel }) }}</p>
        <p v-else-if="status === 'pendiente'">{{ t('grant.statePendiente', { date: atLabel }) }}</p>
        <p v-else-if="status === 'rechazado'">{{ t('grant.stateRejected', { date: atLabel }) }}</p>
        <p v-else-if="status === 'revocado'">{{ t('grant.stateRevoked', { date: atLabel }) }}</p>
        <p v-else-if="status === 'absent'">{{ t('grant.stateAbsent') }}</p>
        <p v-else-if="loading">{{ t('grant.stateUnknown') }}</p>
        <p v-else>{{ t('grant.stateUnreachable') }}</p>
      </ion-label>
      <ion-spinner v-if="loading" slot="end" />
    </ion-item>

    <!-- 🔴 El motivo del rechazo es lo ÚNICO accionable de un «rechazado»: sin él, «vuelve a
         subirlo» no le dice al cliente qué cambiar. -->
    <ion-note
      v-if="status === 'rechazado' && rejectedReason"
      color="danger"
      class="grant-block"
      data-testid="grant-rejected-reason"
    >
      {{ rejectedReason }}
    </ion-note>

    <!-- La invitación a hacerlo solo cuando hay algo que hacer: debajo de «lo estamos revisando»,
         «descárgalo, fírmalo y súbelo» es lo que produce el segundo envío que alguien desempata. -->
    <ion-note v-if="showForm" class="grant-block" data-testid="grant-intro">
      {{ t('grant.intro') }}
    </ion-note>

    <template v-if="isAdmin && showForm">
      <!-- ── Paso 1: el modelo oficial ─────────────────────────────────────────────────────── -->
      <ion-label class="grant-step">
        <h3>{{ t('grant.step1Title') }}</h3>
        <p>{{ t('grant.step1Hint') }}</p>
      </ion-label>

      <!-- 🔴 Las dos partes van ROTULADAS. El modelo pide la dirección del negocio y la de quien
           firma, y los dos bloques llevan los mismos tres campos: sin un rótulo encima, dos bloques
           idénticos seguidos es exactamente cómo se rellena el segundo con los datos del primero.
           Visto mirando la pantalla a 390/768/1280. -->
      <ion-label class="grant-party" data-testid="grant-party-obligado">
        <h4>{{ t('grant.partyObligado') }}</h4>
      </ion-label>

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
      <div class="grant-row">
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="t('grant.municipio')"
          data-testid="grant-obligado-municipio"
          v-model="obligadoMunicipio"
        />
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="t('grant.via')"
          data-testid="grant-obligado-via"
          v-model="obligadoVia"
        />
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="t('grant.numero')"
          data-testid="grant-obligado-numero"
          v-model="obligadoNumero"
        />
      </div>

      <!-- El FIRMANTE es una persona: en una sociedad, quien la representa. La copia del documento
           de identidad que se pide en el paso 2 es la SUYA, no la de la sociedad. -->
      <ion-label class="grant-party" data-testid="grant-party-signer">
        <h4>{{ t('grant.partySigner') }}</h4>
      </ion-label>

      <ion-input
        class="mt-2"
        mode="md"
        fill="outline"
        label-placement="floating"
        :label="t('grant.signerName')"
        data-testid="grant-signer-name"
        v-model="signerName"
      />
      <ion-input
        class="mt-2"
        mode="md"
        fill="outline"
        label-placement="floating"
        :label="t('grant.signerNif')"
        data-testid="grant-signer-nif"
        v-model="signerNif"
        placeholder="12345678Z"
      />
      <div class="grant-row">
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="t('grant.municipio')"
          data-testid="grant-signer-municipio"
          v-model="signerMunicipio"
        />
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="t('grant.via')"
          data-testid="grant-signer-via"
          v-model="signerVia"
        />
        <ion-input
          mode="md"
          fill="outline"
          label-placement="floating"
          :label="t('grant.numero')"
          data-testid="grant-signer-numero"
          v-model="signerNumero"
        />
      </div>

      <ion-button
        expand="block"
        class="mt-3"
        data-testid="grant-download-model"
        :disabled="!canDownloadModel || downloading"
        @click="downloadModel()"
      >
        <ion-spinner v-if="downloading" slot="start" name="dots" />
        <HubIcon v-else slot="start" name="download-outline" />
        {{ t('grant.downloadModel') }}
      </ion-button>
      <ion-note v-if="savedPath" class="grant-block" data-testid="grant-saved-path">
        {{ t('download.savedTo', { path: savedPath }) }}
      </ion-note>

      <ion-label class="grant-step">
        <p>{{ t('grant.howToByHand') }}</p>
        <p>{{ t('grant.howToElectronic') }}</p>
      </ion-label>

      <!-- Capa de información básica del art. 13 RGPD: quién trata los datos y para qué. Va aquí,
           antes de que nadie suba un documento de identidad, no en un enlace al final. -->
      <div class="grant-privacy" data-testid="grant-privacy">
        <p class="grant-privacy-title">{{ t('grant.privacyTitle') }}</p>
        <p>{{ t('grant.privacyController') }}</p>
        <p>{{ t('grant.privacyPurpose') }}</p>
        <p>{{ t('grant.privacyRights') }}</p>
      </div>

      <!-- ── Paso 2: la subida ─────────────────────────────────────────────────────────────── -->
      <ion-label class="grant-step">
        <h3>{{ t('grant.step2Title') }}</h3>
        <p>{{ t('grant.step2Hint') }}</p>
      </ion-label>

      <GrantFilePicker
        class="mt-2"
        accept=".pdf,application/pdf"
        testid="grant-signed-document"
        :label="signedDocument?.name || t('grant.signedDocumentChoose')"
        @picked="signedDocument = $event"
      />

      <ion-select
        class="mt-3"
        mode="md"
        fill="outline"
        label-placement="floating"
        interface="popover"
        data-testid="grant-document-type"
        :label="t('grant.documentType')"
        :value="documentType"
        @ionChange="documentType = $event.detail.value"
      >
        <ion-select-option value="dni">{{ t('grant.documentTypeDni') }}</ion-select-option>
        <ion-select-option value="nie">{{ t('grant.documentTypeNie') }}</ion-select-option>
      </ion-select>

      <GrantFilePicker
        class="mt-2"
        accept="image/*,.pdf"
        testid="grant-dni-copy"
        :label="dniFile?.name || t('grant.dniChoose')"
        @picked="dniFile = $event"
      />

      <!-- Muestra de firma: solo con NIE, porque muchos documentos extranjeros no llevan firma. -->
      <template v-if="needsSignatureSample">
        <ion-note class="grant-block">{{ t('grant.signatureSampleWhy') }}</ion-note>
        <GrantFilePicker
          accept="image/*,.pdf"
          testid="grant-signature-sample"
          :label="signatureSample?.name || t('grant.signatureSampleChoose')"
          @picked="signatureSample = $event"
        />
      </template>

      <!-- Justificante de representación: solo si el obligado es una sociedad. -->
      <template v-if="needsRepresentationProof">
        <ion-note class="grant-block">{{ t('grant.representationProofWhy') }}</ion-note>
        <GrantFilePicker
          accept="image/*,.pdf"
          testid="grant-representation-proof"
          :label="representationProof?.name || t('grant.representationProofChoose')"
          @picked="representationProof = $event"
        />
      </template>

      <ion-button
        expand="block"
        class="mt-3"
        data-testid="grant-submit"
        :disabled="!canSubmit || busy"
        @click="submit()"
      >
        <ion-spinner v-if="busy" slot="start" name="dots" />
        <HubIcon v-else slot="start" name="cloud-upload-outline" />
        {{ t('grant.submit') }}
      </ion-button>

      <ion-note v-if="errorKey" color="danger" class="grant-block" data-testid="grant-error">
        {{ t(errorKey) }}
        <template v-if="errorStatusCode"> ({{ errorStatusCode }})</template>
      </ion-note>
    </template>

    <!-- La otra puerta al mismo trámite, para quien prefiera papel y pantalla grande. Se ofrece
         SIEMPRE, también mientras se revisa: desde el ordenador se ve el mismo expediente. -->
    <ion-button
      v-if="isAdmin"
      fill="clear"
      size="small"
      class="mt-2"
      data-testid="grant-open-dashboard"
      @click="openDashboard()"
    >
      <HubIcon slot="start" name="open-outline" />
      {{ t('grant.preferComputer') }}
    </ion-button>
  </div>
</template>

<script setup lang="ts">
/**
 * **Donde el cliente consigue el modelo del otorgamiento y sube el que ya firmó** (hub#1293).
 *
 * ERPlora remite los registros VERI\*FACTU **en nombre del** obligado, y eso exige su
 * consentimiento firmado: el Anexo I del acuerdo de colaboración social 017. Esta pantalla ya no
 * hace firmar aquí — hacía dibujar un trazo en un `<canvas>` sobre una paráfrasis del modelo, y la
 * FAQ de colaboración social de la AEAT admite exactamente dos firmas: **manuscrita** sobre el
 * modelo impreso (con el sello de la entidad si el otorgante es una sociedad) o **electrónica con
 * el certificado cualificado del propio cliente** (AutoFirma). Un trazo en pantalla no es ninguna
 * de las dos, y un sello no cabe en un canvas.
 *
 * Así que el flujo es de dos pasos, y los dos ocurren FUERA de aquí en el medio:
 *
 *  1. **Descargar el modelo oficial** — lo genera el SaaS, que es donde vive su texto (la p. 11 del
 *     acuerdo dice que «no podrá ser modificado»: dos copias del mismo documento legal acaban
 *     diciendo cosas distintas). Se guarda con `save-download`, que es la única vía que también
 *     funciona dentro de la app instalada.
 *  2. **Subir lo firmado** — el PDF, la copia del documento de identidad, y según el caso la
 *     muestra de firma (NIE) y el justificante de representación (sociedad).
 *
 * Y después se **espera**: toda subida queda `pendiente` y la aprueba una persona de ERPlora en
 * 24-72 h. ERPlora responde ante la AEAT «de la autenticidad de la firma… así como de la copia del
 * DNI», y esa responsabilidad no se automatiza.
 *
 * Tres cosas que este componente NO hace, y son el diseño:
 *
 * 1. **No habla con el SaaS.** Llama a rutas del runtime, y es el runtime quien pone el
 *    `X-Hub-Token` — que es secreto suyo y nunca cruza a este navegador (ADR-0003).
 * 2. **No compone ningún documento.** Ni el modelo ni el firmado: el primero llega hecho, el
 *    segundo se reenvía tal cual.
 * 3. **No se queda nada.** Los ficheros se olvidan en cuanto salen — la custodia es del SaaS
 *    (RGPD), y una copia aquí sería una copia en cada backup y en cada blueprint exportado.
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
// hub#797 — los `ion-*` se IMPORTAN. Este componente no importaba ninguno: funcionaba solo porque
// otra pantalla ya montada los había registrado antes, así que abrirlo el primero (deep-link,
// recarga en esta ruta) lo dejaba pintando etiquetas desconocidas. En una pantalla donde se tramita
// el otorgamiento fiscal, eso no es un detalle de estilo.
import {
  IonButton,
  IonInput,
  IonItem,
  IonLabel,
  IonNote,
  IonSelect,
  IonSelectOption,
  IonSpinner,
} from '@ionic/vue';
import {
  RepresentationGrantError,
  downloadRepresentationGrantModel,
  getRepresentationGrant,
  postRepresentationGrant,
  publishFiscalIdentity,
  type RepresentationGrantStatusValue,
} from '../lib/runtime';
import { isAdmin } from '../lib/session';
import { config } from '../lib/config';
import { openExternal } from '../lib/open-external';
import { saasDoor } from '../lib/saas-door';
import { SaveDownloadError, saveDownload, saveDownloadMessageKey } from '../lib/save-download';
import HubIcon from './HubIcon.vue';
import GrantFilePicker from './GrantFilePicker.vue';
import { formatDate } from '../lib/format-datetime';

const props = defineProps<{
  obligadoNif: string;
  obligadoName: string;
  /** La dirección que el negocio ya configuró, en una sola cadena. Se aprovecha como vía. */
  obligadoAddress?: string;
}>();
const emit = defineEmits<{ (e: 'signed'): void }>();
const { t, te, locale } = useI18n();

/**
 * Las letras que un NIF español lleva delante cuando pertenece a una **entidad** y no a una
 * persona. Mismas letras y mismo nombre que en el runtime y en el SaaS: una sociedad firma a través
 * de quien su escritura nombre, así que ese documento tiene que viajar — y pedírselo a un autónomo
 * sería pedirle algo que no existe.
 */
const ENTITY_LETTERS = 'ABCDEFGHJNPQRSUVW';

function isLegalPersonNif(nif: string): boolean {
  const normalised = nif.replace(/[\s.-]/g, '').toUpperCase();
  return normalised.length > 0 && ENTITY_LETTERS.includes(normalised[0]);
}

/** `''` = todavía no se sabe (cargando, o el runtime no contestó). Nunca se inventa. */
const status = ref<RepresentationGrantStatusValue>('');
const at = ref('');
const rejectedReason = ref('');
const loading = ref(true);

const obligadoMunicipio = ref('');
const obligadoVia = ref(props.obligadoAddress ?? '');
const obligadoNumero = ref('');
const signerNif = ref('');
const signerName = ref('');
const signerMunicipio = ref('');
const signerVia = ref('');
const signerNumero = ref('');

const documentType = ref<'dni' | 'nie'>('dni');
const signedDocument = ref<File | null>(null);
const dniFile = ref<File | null>(null);
const signatureSample = ref<File | null>(null);
const representationProof = ref<File | null>(null);

const busy = ref(false);
const downloading = ref(false);
const savedPath = ref('');
/** El fallo, como CLAVE de i18n: la pantalla traduce por código, nunca por la frase (ADR-0055). */
const errorKey = ref('');
const errorStatusCode = ref<number | null>(null);

const stateIcon = computed(() => {
  if (status.value === 'vigente') return 'shield-checkmark-outline';
  if (status.value === 'pendiente') return 'time-outline';
  if (status.value === 'rechazado') return 'alert-circle-outline';
  return 'shield-outline';
});

const atLabel = computed(() => {
  if (!at.value) return '';
  return formatDate(at.value, { locale: locale.value }) ?? at.value;
});

/**
 * Cuándo hay algo que hacer. Con el otorgamiento vigente no se pide nada; mientras se revisa
 * tampoco — ofrecer «vuelve a subirlo» a quien acaba de subirlo es lo que genera duplicados que
 * otra persona tiene que desempatar a mano.
 */
const showForm = computed(() => status.value !== 'vigente' && status.value !== 'pendiente');

const needsSignatureSample = computed(() => documentType.value === 'nie');
const needsRepresentationProof = computed(() => isLegalPersonNif(props.obligadoNif));

const canDownloadModel = computed(
  () =>
    !!props.obligadoNif.trim() && !!signerNif.value.trim() && !!signerName.value.trim(),
);

const canSubmit = computed(
  () =>
    !!props.obligadoNif.trim() &&
    !!props.obligadoName.trim() &&
    !!signedDocument.value &&
    !!dniFile.value &&
    (!needsSignatureSample.value || !!signatureSample.value) &&
    (!needsRepresentationProof.value || !!representationProof.value),
);

async function load() {
  loading.value = true;
  try {
    const state = await getRepresentationGrant();
    status.value = state.status;
    at.value = state.at;
    rejectedReason.value = state.rejected_reason;
    if (state.document_type === 'dni' || state.document_type === 'nie') {
      documentType.value = state.document_type;
    }
  } catch {
    // Sin respuesta no se pinta un estado: «no lo sé» y «no has firmado» no son lo mismo, y
    // enseñar el segundo cuando pasa el primero manda a alguien a firmar dos veces.
    status.value = '';
  } finally {
    loading.value = false;
  }
}

onMounted(load);

// ── Paso 1: el modelo ─────────────────────────────────────────────────────────────────────────

function modelFields() {
  return {
    obligado_nif: props.obligadoNif.trim(),
    obligado_name: props.obligadoName.trim(),
    obligado_municipio: obligadoMunicipio.value.trim(),
    obligado_via: obligadoVia.value.trim(),
    obligado_numero: obligadoNumero.value.trim(),
    signer_nif: signerNif.value.trim(),
    signer_name: signerName.value.trim(),
    signer_municipio: signerMunicipio.value.trim(),
    signer_via: signerVia.value.trim(),
    signer_numero: signerNumero.value.trim(),
  };
}

/**
 * Trae el modelo y lo GUARDA. El fichero es el objeto del trámite, así que un botón que no dice
 * nada al fallar es peor que ninguno: mientras el SaaS nuevo se despliega esa ruta contesta 404, y
 * eso se enseña con su número.
 */
async function downloadModel() {
  if (!canDownloadModel.value || downloading.value) return;
  downloading.value = true;
  errorKey.value = '';
  errorStatusCode.value = null;
  savedPath.value = '';
  try {
    const pdf = await downloadRepresentationGrantModel(modelFields());
    const nif = props.obligadoNif.trim().replace(/[^A-Za-z0-9]/g, '');
    const saved = await saveDownload(`anexo-i-otorgamiento-${nif}.pdf`, pdf);
    if (saved) savedPath.value = saved;
  } catch (e) {
    showFailure(e);
  } finally {
    downloading.value = false;
  }
}

// ── Paso 2: la subida ─────────────────────────────────────────────────────────────────────────

async function submit() {
  if (!canSubmit.value || busy.value) return;
  busy.value = true;
  errorKey.value = '';
  errorStatusCode.value = null;
  try {
    const state = await postRepresentationGrant({
      obligado_nif: props.obligadoNif.trim(),
      obligado_name: props.obligadoName.trim(),
      signer_nif: signerNif.value.trim(),
      signer_name: signerName.value.trim(),
      document_type: documentType.value,
      signed_document: signedDocument.value!,
      dni_copy: dniFile.value!,
      ...(needsSignatureSample.value && signatureSample.value
        ? { signature_sample: signatureSample.value }
        : {}),
      ...(needsRepresentationProof.value && representationProof.value
        ? { representation_proof: representationProof.value }
        : {}),
    });
    status.value = state.status;
    at.value = state.at;
    rejectedReason.value = '';
    // 🔒 Se olvidan AQUÍ, en el camino de éxito y solo en él: si el envío falla, lo que la persona
    // acaba de adjuntar sigue en pantalla en vez de obligarla a buscar los ficheros otra vez.
    signedDocument.value = null;
    dniFile.value = null;
    signatureSample.value = null;
    representationProof.value = null;
    emit('signed');
  } catch (e) {
    showFailure(e);
  } finally {
    busy.value = false;
  }
}

/**
 * Convierte cualquier fallo en algo que se pueda LEER, y en el idioma de quien mira.
 *
 * Por CÓDIGO y no por la frase del runtime (ADR-0055): el runtime escribe en inglés para el log.
 * Un código que la pantalla todavía no conozca cae en el genérico en vez de dejarla muda.
 */
function showFailure(e: unknown) {
  if (e instanceof SaveDownloadError) {
    errorKey.value = saveDownloadMessageKey(e);
    return;
  }
  if (e instanceof RepresentationGrantError && e.code) {
    // `te` antes de `t`: el runtime contesta un 401 con `error: <prosa>`, y `t` de una clave que
    // no existe devuelve la clave — en pantalla, «grant.errors.falta sesión (…)».
    const key = `grant.errors.${e.code}`;
    errorKey.value = te(key) ? key : 'grant.errors.unknown';
    errorStatusCode.value = e.statusCode ?? null;
    return;
  }
  errorKey.value = 'grant.errors.unknown';
}

// ── La otra puerta ────────────────────────────────────────────────────────────────────────────

/**
 * El mismo trámite desde el ordenador — POR FUERA, nunca llevándose esta ventana.
 *
 * Dentro de la app instalada el webview no tiene barra ni Atrás: navegar en sitio deja al usuario
 * atrapado en el SaaS sin vuelta (mismo motivo y mismo remedio que `management-link.ts`).
 */
async function openDashboard() {
  // La página de allí NOMBRA al obligado, y solo lo conoce si este hub se lo ha publicado
  // (hub#1306): la identidad de negocio vive en `hub_settings` y el SaaS no entra en el hub
  // (ADR-0201, decisión 5). Sin publicar, el cliente aterriza en un muro —«pon antes tus datos
  // fiscales»— que ya rellenó aquí. Así que se publica ANTES de mandarlo, no después.
  try {
    await publishFiscalIdentity();
  } catch {
    // Se abre igual: puede haberse publicado antes y allí ya saberlo, y cerrarle esta vía por un
    // fallo de sincronización le quitaría la única alternativa a esta pantalla. Pero no muda —
    // si la página le pide los datos fiscales, esto es lo que se lo explica.
    errorKey.value = 'grant.errors.identity_not_shared';
  }
  // pm#196 — se cruza con el pase de un solo uso. El apoderamiento se firma en erplora.com y desde
  // la app instalada se llegaba SIN sesión: login y segundo factor otra vez en mitad de un trámite
  // fiscal. Si el pase no se puede acuñar, `saasDoor` devuelve este mismo enlace y lo reporta.
  const path = `/dashboard/hubs/${encodeURIComponent(config.hubId)}/fiscal/representation-grant/`;
  const url = `${config.cloudApiUrl}${path}`;
  try {
    await openExternal(await saasDoor(path, url, 'representation-grant'));
  } catch {
    errorKey.value = 'grant.errors.open_external_failed';
  }
}

defineExpose({
  status,
  at,
  rejectedReason,
  obligadoMunicipio,
  obligadoVia,
  obligadoNumero,
  signerNif,
  signerName,
  signerMunicipio,
  signerVia,
  signerNumero,
  documentType,
  signedDocument,
  dniFile,
  signatureSample,
  representationProof,
  needsSignatureSample,
  needsRepresentationProof,
  canDownloadModel,
  canSubmit,
  errorKey,
  downloadModel,
  submit,
  openDashboard,
});
</script>

<style scoped>
.grant-block {
  display: block;
  margin: 0.5rem 0;
}

.grant-step {
  display: block;
  margin-top: 1.25rem;
}

.grant-step h3 {
  font-weight: 600;
}

/* El rótulo de cada parte: separa los dos bloques de dirección sin gritar como un h3. El hueco de
   abajo no es estético — la etiqueta flotante de un `ion-input` con `fill="outline"` se pinta sobre
   el borde superior del campo, y con menos margen se solapaba con este rótulo (visto a 768 px). */
.grant-party {
  display: block;
  margin: 1.25rem 0 0.75rem;
}

.grant-party h4 {
  margin: 0;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--ion-color-medium-shade, #6b6b6b);
}

/* Las tres casillas de una dirección caben en una fila en escritorio y se apilan en el móvil: a
   390 px, tres campos en línea dejan «Municipio» en dos letras. */
.grant-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

@media (min-width: 640px) {
  .grant-row {
    grid-template-columns: 2fr 3fr 1fr;
  }
}

/* La capa del art. 13 RGPD se lee: prosa, no una nota al pie de 10 px. */
.grant-privacy {
  margin-top: 1rem;
  padding: 0.75rem;
  border: 1px solid var(--ion-color-step-150, #e0e0e0);
  border-radius: 8px;
  background: var(--ion-color-step-50, #fafafa);
  font-size: 0.8rem;
  line-height: 1.5;
}

.grant-privacy p {
  margin: 0 0 0.35rem;
}

.grant-privacy-title {
  font-weight: 600;
}

/* El estado se lee ENTERO: `ion-label` trunca con ellipsis por defecto y a 390 px eso dejaba
   «Lo estamos revisando; te avisamos por…» — la mitad de la frase que dice cuánto hay que esperar. */
.grant-state-label p {
  white-space: normal;
}
</style>
