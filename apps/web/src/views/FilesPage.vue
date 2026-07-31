<!--
  FilesPage — gestor de archivos (Drive-like) de la carpeta `media/` del Hub.

  `media/` es el path por defecto de TODOS los ficheros del Hub (se crea en el despliegue):
  adjuntos de módulos, registros de sistema (`_logs/`) y monitor de actividad (`_system/`).
  Esta pantalla la navega con el componente `ok-file-manager` de OutfitKit — solo renderiza y
  emite eventos `ok-*`; aquí cableamos el storage real vía `lib/media.ts` (runtime Rust).

  El componente es responsive por sí mismo (≤768px el árbol colapsa a un <select>). Los datos
  vienen del runtime; si el endpoint aún no existe, la pantalla queda vacía (sin mock).
-->
<template>
  <AppPage :title="t('files.title')">
    <ok-inline-feedback
      v-if="loadFailed"
      class="files-feedback"
      tone="danger"
      icon="cloud-offline-outline"
      :heading="t('files.loadErrorTitle')"
    >
      {{ t('files.loadErrorBody') }}
      <ion-button slot="actions" size="small" fill="outline" @click="load(selected)">
        {{ t('files.retry') }}
      </ion-button>
    </ok-inline-feedback>

    <ok-file-manager ref="fmEl" searchable :uploadable="isAdmin"></ok-file-manager>

    <!-- «Abrir» previsualiza aquí dentro (ADR-0165); «Descargar» sigue bajando el fichero. -->
    <FilePreviewModal
      :file="previewFile"
      :open="previewOpen"
      @close="closePreview"
      @download="downloadPreviewed"
    />

    <ion-toast
      :is-open="toastOpen"
      :message="toastMessage"
      :duration="2600"
      position="bottom"
      @did-dismiss="toastOpen = false"
    />
  </AppPage>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonToast, alertController } from '@ionic/vue';
import AppPage from '../components/AppPage.vue';
import FilePreviewModal from '../components/FilePreviewModal.vue';
import { RUNTIME_URL, runtimeHeaders } from '../lib/runtime';
import { isAdmin } from '../lib/session';
import {
  fetchMedia,
  uploadMedia,
  deleteMedia,
  createMediaFolder,
  type MediaFolder,
  type MediaFile,
  renameMedia,
  type MediaCrumb,
  type MediaQuota,
  type MediaPolicy,
} from '../lib/media';

const { t } = useI18n();

// El elemento Lit con sus props reactivas (asignación imperativa: robusto para objetos/eventos).
type FmElement = HTMLElement & {
  folders: MediaFolder[];
  files: MediaFile[];
  path: MediaCrumb[];
  quota?: MediaQuota;
  policy?: MediaPolicy;
  selected: string;
  view: 'grid' | 'list';
  loading: boolean;
  labels: Record<string, string>;
};
const fmEl = ref<FmElement | null>(null);

// Estado local. `allFiles` es la lista maestra de la carpeta actual (la búsqueda filtra sobre ella).
let folders: MediaFolder[] = [];
let allFiles: MediaFile[] = [];
let path: MediaCrumb[] = [];
let quota: MediaQuota | undefined;
// Lo que el runtime dice que se puede hacer en la carpeta actual (ADR-0166). Solo adorna la UI:
// el servidor revalida en cada endpoint, así que aquí no hay barrera que saltarse.
let policy: MediaPolicy | undefined;
let selected = '';
let query = '';

const toastOpen = ref(false);
const toastMessage = ref('');
const loadFailed = ref(false);
function toast(msg: string): void {
  toastMessage.value = msg;
  toastOpen.value = true;
}

// Etiquetas i18n del componente (merge sobre sus defaults en español).
function labels(): Record<string, string> {
  return {
    upload: t('files.upload'),
    import: t('files.import'),
    search: t('files.search'),
    folders: t('files.folders'),
    space: t('files.space'),
    empty: t('files.empty'),
    download: t('files.download'),
    delete: t('files.delete'),
    open: t('files.open'),
    newFolder: t('files.newFolder'),
  };
}

// Empuja el estado local a las props del web component.
function applyState(): void {
  const el = fmEl.value;
  if (!el) return;
  const q = query.trim().toLowerCase();
  el.folders = folders;
  el.files = q ? allFiles.filter((f) => f.name.toLowerCase().includes(q)) : allFiles;
  el.path = path;
  el.quota = quota;
  el.policy = policy;
  el.selected = selected;
  el.labels = labels();
}

// Carga el contenido de una carpeta (raíz si se omite). Degrada a vacío si no hay endpoint.
async function load(folder = ''): Promise<void> {
  const el = fmEl.value;
  if (el) el.loading = true;
  const data = await fetchMedia(folder);
  loadFailed.value = !data;
  if (data) {
    folders = data.folders ?? [];
    allFiles = data.files ?? [];
    path = data.path ?? [];
    quota = data.quota;
    policy = data.policy;
    selected = folder;
  } else {
    // El feedback explica el error; el gestor queda vacío y permite reintentar sin inventar datos.
    folders = [];
    allFiles = [];
    path = [];
    quota = undefined;
    policy = undefined;
    selected = folder;
  }
  query = '';
  if (el) el.loading = false;
  applyState();
}

// ---- Visor (ADR-0165) ----
// «Abrir» ya no lanza el fichero a una pestaña del navegador: lo previsualiza en el modal, que
// es lo único que funciona igual en los dos productos (en Hub Local/Tauri no hay pestañas).
const previewFile = ref<MediaFile | null>(null);
const previewOpen = ref(false);

function openPreview(id: string): void {
  const file = allFiles.find((f) => f.id === id);
  if (!file) {
    toast(t('files.empty'));
    return;
  }
  previewFile.value = file;
  previewOpen.value = true;
}

function closePreview(): void {
  previewOpen.value = false;
  previewFile.value = null;
}

/** Descarga desde el botón del propio visor, sobre el fichero que se está viendo. */
function downloadPreviewed(): void {
  if (previewFile.value) void downloadFile(previewFile.value.id);
}

// Descarga un fichero por su URL (raw autenticado del runtime en local, URL firmada en cloud).
async function downloadFile(id: string): Promise<void> {
  const file = allFiles.find((f) => f.id === id);
  if (!file?.url) {
    toast(t('files.empty'));
    return;
  }
  if (/^https?:\/\//.test(file.url)) {
    window.open(file.url, '_blank', 'noopener');
    return;
  }
  try {
    // `window.open` no puede adjuntar `X-Hub-Session`: el fichero local protegido se obtiene como
    // blob con el fetch autenticado y solo ese object URL temporal llega al navegador.
    const response = await fetch(`${RUNTIME_URL}${file.url}`, { headers: runtimeHeaders() });
    if (!response.ok) throw new Error(String(response.status));
    const objectUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = file.name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000);
  } catch {
    toast(t('files.openError'));
  }
}

// ---- Listeners de los eventos `ok-*` del componente ----
function onNavigate(e: Event): void {
  void load((e as CustomEvent<{ id: string }>).detail.id);
}
function onSearch(e: Event): void {
  query = (e as CustomEvent<{ query: string }>).detail.query ?? '';
  applyState();
}
function onOpen(e: Event): void {
  openPreview((e as CustomEvent<{ id: string }>).detail.id);
}
function onDownload(e: Event): void {
  void downloadFile((e as CustomEvent<{ id: string }>).detail.id);
}
async function onUpload(e: Event): Promise<void> {
  if (!isAdmin.value) {
    toast(t('files.permissionDenied'));
    return;
  }
  const files = (e as CustomEvent<{ files: File[] }>).detail.files ?? [];
  if (!files.length) return;
  const ok = await uploadMedia(selected, files);
  toast(ok ? t('files.uploadSuccess') : t('files.uploadError'));
  if (ok) await load(selected);
}
/** Carpeta que contiene a `path` (cadena vacía = la raíz de `media/`). */
function parentOf(path: string): string {
  return path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
}

async function onDelete(e: Event): Promise<void> {
  if (!isAdmin.value) {
    toast(t('files.permissionDenied'));
    return;
  }
  const { id, kind } = (e as CustomEvent<{ id: string; kind?: 'file' | 'folder' }>).detail;
  const isFolder = kind === 'folder';
  const name = isFolder ? id.split('/').pop() : allFiles.find((f) => f.id === id)?.name;
  const alert = await alertController.create({
    header: isFolder ? t('files.deleteFolderTitle') : t('files.deleteTitle'),
    // Borrar una carpeta se lleva lo de dentro: el aviso tiene que decirlo.
    message: isFolder
      ? t('files.deleteFolderBody', { name: name ?? id })
      : t('files.deleteBody', { name: name ?? id }),
    buttons: [
      { text: t('files.cancel'), role: 'cancel' },
      { text: t('files.delete'), role: 'confirm', cssClass: 'alert-button-danger' },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss();
  if (result.role !== 'confirm') return;
  const ok = await deleteMedia(id);
  toast(ok ? t('files.deleteSuccess') : t('files.deleteError'));
  // Si se ha borrado la carpeta donde estabas, quedarte ahí sería quedarse en algo que ya no
  // existe: se sube a la de arriba.
  if (ok) await load(isFolder && id === selected ? parentOf(id) : selected);
}

async function onRename(e: Event): Promise<void> {
  if (!isAdmin.value) {
    toast(t('files.permissionDenied'));
    return;
  }
  const { id, name, kind } = (e as CustomEvent<{ id: string; name?: string; kind?: 'file' | 'folder' }>).detail;
  const alert = await alertController.create({
    header: t('files.rename'),
    inputs: [
      {
        name: 'name',
        type: 'text',
        // El nombre actual va precargado: renombrar suele ser retocarlo, no escribirlo entero.
        value: name ?? '',
        placeholder: t('files.newName'),
        attributes: { maxlength: 255, autocomplete: 'off' },
      },
    ],
    buttons: [
      { text: t('files.cancel'), role: 'cancel' },
      { text: t('files.rename'), role: 'confirm' },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss<{ values?: { name?: string } }>();
  if (result.role !== 'confirm') return;
  const next = result.data?.values?.name?.trim();
  if (!next || next === name) return;
  const ok = await renameMedia(id, next);
  toast(ok ? t('files.renameSuccess') : t('files.renameError'));
  if (!ok) return;
  // Renombrar la carpeta en la que estás cambia su ruta: hay que seguirla, no recargar la vieja.
  const renamedCurrent = kind === 'folder' && id === selected;
  const target = parentOf(id);
  await load(renamedCurrent ? (target ? `${target}/${next}` : next) : selected);
}
async function onCreateFolder(e: Event): Promise<void> {
  if (!isAdmin.value) {
    toast(t('files.permissionDenied'));
    return;
  }
  const parent = (e as CustomEvent<{ parent: string }>).detail.parent ?? selected;
  const alert = await alertController.create({
    header: t('files.newFolder'),
    inputs: [
      {
        name: 'folderName',
        type: 'text',
        placeholder: t('files.folderName'),
        attributes: { maxlength: 100, autocomplete: 'off' },
      },
    ],
    buttons: [
      { text: t('files.cancel'), role: 'cancel' },
      { text: t('files.createFolder'), role: 'confirm' },
    ],
  });
  await alert.present();
  const result = await alert.onDidDismiss<{ values?: { folderName?: string } }>();
  if (result.role !== 'confirm') return;
  const name = result.data?.values?.folderName?.trim();
  if (!name) return;
  const ok = await createMediaFolder(parent, name);
  toast(ok ? t('files.folderCreated') : t('files.folderError'));
  if (ok) await load(selected);
}

onMounted(async () => {
  const el = fmEl.value;
  if (el) {
    el.addEventListener('ok-navigate', onNavigate);
    el.addEventListener('ok-search', onSearch);
    el.addEventListener('ok-open', onOpen);
    el.addEventListener('ok-download', onDownload);
    el.addEventListener('ok-upload', onUpload as EventListener);
    el.addEventListener('ok-delete', onDelete as EventListener);
    el.addEventListener('ok-rename', onRename as EventListener);
    el.addEventListener('ok-create-folder', onCreateFolder as EventListener);
  }
  await load('');
});

onBeforeUnmount(() => {
  const el = fmEl.value;
  if (!el) return;
  el.removeEventListener('ok-navigate', onNavigate);
  el.removeEventListener('ok-search', onSearch);
  el.removeEventListener('ok-open', onOpen);
  el.removeEventListener('ok-download', onDownload);
  el.removeEventListener('ok-upload', onUpload as EventListener);
  el.removeEventListener('ok-delete', onDelete as EventListener);
  el.removeEventListener('ok-rename', onRename as EventListener);
  el.removeEventListener('ok-create-folder', onCreateFolder as EventListener);
});
</script>

<style scoped>
.files-feedback {
  margin-bottom: 0.75rem;
}
</style>
