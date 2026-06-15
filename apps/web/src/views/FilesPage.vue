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
    <ok-file-manager ref="fmEl" searchable uploadable></ok-file-manager>

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
import { IonToast } from '@ionic/vue';
import AppPage from '../components/AppPage.vue';
import { RUNTIME_URL } from '../lib/runtime';
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
  if (data) {
    folders = data.folders ?? [];
    allFiles = data.files ?? [];
    path = data.path ?? [];
    quota = data.quota;
    selected = folder;
  } else {
    // Sin endpoint todavía: estado vacío honesto (no mock).
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

// Abre/descarga un fichero por su URL (raw del runtime en local, S3 firmada en cloud).
function openFile(id: string): void {
  const file = allFiles.find((f) => f.id === id);
  if (!file?.url) {
    toast(t('files.empty'));
    return;
  }
  // El runtime devuelve una URL relativa (`/api/media/raw?…`); la absolutizamos contra el runtime
  // para que funcione aunque la web no use el proxy de dev. Las URLs S3 ya vienen absolutas.
  const href = /^https?:\/\//.test(file.url) ? file.url : `${RUNTIME_URL}${file.url}`;
  window.open(href, '_blank', 'noopener');
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
  openFile((e as CustomEvent<{ id: string }>).detail.id);
}
function onDownload(e: Event): void {
  openFile((e as CustomEvent<{ id: string }>).detail.id);
}
async function onUpload(e: Event): Promise<void> {
  const files = (e as CustomEvent<{ files: File[] }>).detail.files ?? [];
  if (!files.length) return;
  const ok = await uploadMedia(selected, files);
  toast(ok ? t('files.upload') + ' ✓' : t('files.empty'));
  if (ok) await load(selected);
}
async function onDelete(e: Event): Promise<void> {
  const id = (e as CustomEvent<{ id: string }>).detail.id;
  const file = allFiles.find((f) => f.id === id);
  if (!window.confirm(`${t('files.delete')}: ${file?.name ?? id}?`)) return;
  const ok = await deleteMedia(id);
  toast(ok ? t('files.delete') + ' ✓' : t('files.empty'));
  if (ok) await load(selected);
}
async function onCreateFolder(e: Event): Promise<void> {
  const parent = (e as CustomEvent<{ parent: string }>).detail.parent ?? selected;
  const name = window.prompt(t('files.newFolder'));
  if (!name) return;
  const ok = await createMediaFolder(parent, name);
  toast(ok ? t('files.newFolder') + ' ✓' : t('files.empty'));
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
