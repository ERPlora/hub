<template>
  <!-- Editor.js se monta sobre este holder. La UI del editor la genera la librería en runtime. -->
  <div ref="holder" class="page-editor" data-testid="page-editor" />
</template>

<script setup lang="ts">
// PageEditor — editor de páginas públicas del Hub (ADR-0160 F2). Envuelve Editor.js y produce
// JSON de BLOQUES (nunca HTML). Se usa SOLO en la ruta de edición autenticada; esta pieza es el
// componente, no la ruta ni el transporte de guardado (aún no existe): el guardado se emite.
//
// SEGURIDAD (ADR-0160): SOLO tools curados. Se PROHÍBE registrar `@editorjs/raw` (inyecta HTML
// crudo) y `@editorjs/embed` (inyecta iframes). Media: solo del propio Hub vía /files (ADR-0047),
// nunca URLs externas.
import { onMounted, onBeforeUnmount, ref, shallowRef } from 'vue';
import { useI18n } from 'vue-i18n';
import EditorJS, { type OutputData, type EditorConfig, type ToolConstructable } from '@editorjs/editorjs';
import Header from '@editorjs/header';
import List from '@editorjs/list';
import Quote from '@editorjs/quote';
import Delimiter from '@editorjs/delimiter';
import Table from '@editorjs/table';
import ImageTool from '@editorjs/image';
import { RUNTIME_URL, runtimeHeaders } from '../lib/runtime';

const props = withDefaults(
  defineProps<{
    /** Bloques a cargar al abrir el editor (salida previa de `save()`). */
    initialData?: OutputData;
    /** Carpeta de `media/` donde suben las imágenes de la página (ver lib/media.ts). */
    mediaFolder?: string;
  }>(),
  { mediaFolder: 'pages' },
);

// El guardado no tiene transporte todavía: el padre (la ruta de edición) recibe el JSON y decide
// dónde persistirlo. `save()` (expuesto) también lo devuelve para composición imperativa.
const emit = defineEmits<{ (e: 'save', data: OutputData): void }>();

const { t } = useI18n();
const holder = ref<HTMLDivElement | null>(null);
// shallowRef: la instancia de Editor.js no debe hacerse reactiva en profundidad (es un objeto
// grande con DOM interno); solo necesitamos guardar la referencia.
const editor = shallowRef<EditorJS | null>(null);

// --- Uploader de media del Hub (/files, ADR-0047). SOLO media interna: nunca URLs externas. ---
type UploadResult = { success: number; file: { url: string } };
const FAILED: UploadResult = { success: 0, file: { url: '' } };

/** Solo se acepta media ya alojada en el propio Hub. Cualquier esquema/host externo → rechazo. */
function isInternalMediaUrl(url: string): boolean {
  return url.startsWith('/files/') || url.startsWith('/api/media/');
}

/**
 * Sube una imagen a `media/<folder>` vía el runtime del Hub (mismo contrato que lib/media.ts).
 *
 * TODO(ADR-0047): fijar el contrato de `POST /api/media/upload` para que devuelva la URL (firmada)
 * del fichero subido. Hoy `uploadMedia()` (lib/media.ts) solo devuelve `ok:boolean`; aquí leemos
 * de forma defensiva `data.file.url` / `data.url`, pero el wiring fino vive en `crates/server`
 * (columna del humano). Si el runtime no devuelve una URL interna, la subida se reporta fallida
 * (Editor.js muestra su propio error) — nunca se acepta una URL externa.
 */
async function uploadByFile(file: Blob): Promise<UploadResult> {
  try {
    const form = new FormData();
    form.append('folder', props.mediaFolder);
    form.append('files', file);
    // Sin Content-Type manual: el navegador fija el boundary del multipart.
    const res = await fetch(`${RUNTIME_URL}/api/media/upload`, {
      method: 'POST',
      headers: runtimeHeaders(),
      body: form,
    });
    if (!res.ok) return FAILED;
    const body = (await res.json()) as {
      data?: { url?: string; file?: { url?: string } };
      url?: string;
    };
    const url = body.data?.file?.url ?? body.data?.url ?? body.url ?? '';
    if (!url || !isInternalMediaUrl(url)) return FAILED;
    return { success: 1, file: { url } };
  } catch {
    return FAILED;
  }
}

/** Referenciar por URL: solo rutas internas del Hub (/files, /api/media). Externas → rechazo. */
async function uploadByUrl(url: string): Promise<UploadResult> {
  if (!isInternalMediaUrl(url)) return FAILED;
  return { success: 1, file: { url } };
}

/** Conjunto CURADO de tools. NO se añaden `raw` ni `embed` a propósito (seguridad, ADR-0160). */
function buildTools(): NonNullable<EditorConfig['tools']> {
  return {
    header: { class: Header, inlineToolbar: true },
    list: { class: List, inlineToolbar: true },
    quote: { class: Quote, inlineToolbar: true },
    delimiter: Delimiter,
    // `as ToolConstructable`: el .d.ts de @editorjs/table declara su config como requerida y no
    // encaja en BlockToolConstructable; en runtime es un tool válido. Cast acotado a esta línea.
    table: { class: Table as unknown as ToolConstructable, inlineToolbar: true },
    image: {
      class: ImageTool,
      // Uploader propio → media del Hub. `endpoints` se omite adrede (no delegamos en un backend
      // externo); el uploader controla el destino y valida que la URL sea interna.
      config: { uploader: { uploadByFile, uploadByUrl } },
    },
    // paragraph es el bloque por defecto del core de Editor.js: no hace falta registrarlo.
  };
}

onMounted(() => {
  if (!holder.value) return;
  editor.value = new EditorJS({
    holder: holder.value,
    data: props.initialData,
    placeholder: t('pageEditor.placeholder'),
    tools: buildTools(),
  });
});

onBeforeUnmount(() => {
  // Limpieza: Editor.js registra listeners y DOM propios; destroy() los libera.
  editor.value?.destroy?.();
  editor.value = null;
});

/** Serializa el contenido a JSON de bloques, lo emite en `@save` y lo devuelve. */
async function save(): Promise<OutputData> {
  if (!editor.value) throw new Error('PageEditor: editor no está listo');
  const data = await editor.value.save();
  emit('save', data);
  return data;
}

defineExpose({ save });
</script>

<style scoped>
/* El editor ocupa el ancho disponible; la altura la marca el contenido (crece con los bloques). */
.page-editor {
  width: 100%;
}
</style>
