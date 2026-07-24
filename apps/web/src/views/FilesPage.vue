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
import { RUNTIME_URL, runtimeHeaders } from '../lib/runtime';
import { isAdmin } from '../lib/session';
import {
  fetchMedia,
  uploadMedia,
  deleteMedia,
  createMediaFolder,
  type MediaFolder,
  type MediaFile,
  type MediaCrumb,
  type MediaQuota,
} from '../lib/media';

const { t } = useI18n();

// El elemento Lit con sus props reactivas (asignación imperativa: robusto para objetos/eventos).
type FmElement = HTMLElement & {
  folders: MediaFolder[];
  files: MediaFile[];
  path: MediaCrumb[];
  quota?: MediaQuota;
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
    selected = folder;
  } else {
    // El feedback explica el error; el gestor queda vacío y permite reintentar sin inventar datos.
    folders = [];
    allFiles = [];
    path = [];
    quota = undefined;
    selected = folder;
  }
  query = '';
  if (el) el.loading = false;
  applyState();
}

// Abre/descarga un fichero por su URL (raw autenticado del runtime en local, URL firmada en cloud).
async function openFile(id: string, download = false): Promise<void> {
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
    if (download) anchor.download = file.name;
    else {
      anchor.target = '_blank';
      anchor.rel = 'noopener';
    }
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
  void openFile((e as CustomEvent<{ id: string }>).detail.id);
}
function onDownload(e: Event): void {
  void openFile((e as CustomEvent<{ id: string }>).detail.id, true);
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
async function onDelete(e: Event): Promise<void> {
  if (!isAdmin.value) {
    toast(t('files.permissionDenied'));
    return;
  }
  const id = (e as CustomEvent<{ id: string }>).detail.id;
  const file = allFiles.find((f) => f.id === id);
  const alert = await alertController.create({
    header: t('files.deleteTitle'),
    message: t('files.deleteBody', { name: file?.name ?? id }),
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
  if (ok) await load(selected);
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
  el.removeEventListener('ok-create-folder', onCreateFolder as EventListener);
});
</script>

<style scoped>
.files-feedback {
  margin-bottom: 0.75rem;
}
</style>
