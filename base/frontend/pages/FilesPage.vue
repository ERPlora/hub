<script setup lang="ts">
// Files (APP-BASE-8; the old hub's FilesPage, HUB_SHELL-F130…F134): the business's files, live (`base.file.list`,
// re-run after every write of them from any device). Like the old screen: the tree of folders on the left — content of
// the page, not a menu; on a narrow screen a «Folders» selector —, the open folder's path, its folders and files in a
// grid or a list, «Space» (used, against the plan's when it has one, else «No limit»), «Search files…» in the open
// folder. Who runs the business (`can`, from the server) uploads (the button, or by dropping files), makes folders,
// renames, moves («Move to…», or by dragging onto a folder) and deletes (asked first); everyone opens (the preview) and
// downloads. The open folder is in the address (`?folder=`). Every refusal reads its own sentence (hub#1776); every
// notice is a sentence, never a key (hub#2197).
import { EmptyState, FormModal, InlineFeedback, UsageMeter, useConfirm } from '@erplora/ui/components';
import { type ApiError, fetchFile, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import {
  IonButton,
  IonInput,
  IonItem,
  IonLabel,
  IonList,
  IonPopover,
  IonSearchbar,
  IonSelect,
  IonSelectOption,
} from '@ionic/vue';
import { computed, ref, useTemplateRef } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FilePreview from '../components/FilePreview.vue';
import FileTree from '../components/FileTree.vue';
import { bytesToBase64, saveFile } from '../lib/data';
import {
  afterDelete,
  afterMove,
  childrenOf,
  extensionOf,
  flatFolders,
  formatSize,
  iconFor,
  matches,
  MAX_FOLDER_NAME,
  MAX_NAME,
  nameOf,
  parentOf,
  rawUrl,
  refusalKey,
  tooLarge,
} from '../lib/files';
import { useBaseI18n } from '../lib/i18n';
import type { FileItem } from '../operations';

/** A file or a folder of the open folder, as the actions take it. */
interface Entry {
  path: string;
  name: string;
  folder: boolean;
  file?: FileItem;
}

const { t, locale } = useBaseI18n();
const route = useRoute();
const router = useRouter();
const { confirm } = useConfirm();

const folder = computed(() => (typeof route.query.folder === 'string' ? route.query.folder : ''));
const { data, status, error, refresh } = useLive(
  'base.file.list',
  computed(() => ({ folder: folder.value })),
);
const upload = useCommand('base.file.upload');
const createFolder = useCommand('base.file.create_folder');
const rename = useCommand('base.file.rename');
const move = useCommand('base.file.move');
const remove = useCommand('base.file.delete');

/** The listing of the folder open, never one left from the folder before. */
const listing = computed(() => (data.value && data.value.folder === folder.value ? data.value : undefined));
const failed = computed(() => status.value === 'error');
const loading = computed(() => !listing.value && !failed.value);
const can = computed(() => listing.value?.can ?? { upload: false, delete: false });
const canMove = computed(() => can.value.upload && can.value.delete);
const tree = computed(() => listing.value?.folders ?? []);
const flat = computed(() => flatFolders(tree.value));

const search = ref('');
const view = ref<'grid' | 'list'>('grid');
const entries = computed<Entry[]>(() => {
  const here = listing.value;
  if (!here) return [];
  const folders = search.value.trim()
    ? []
    : childrenOf(here.folders, here.folder).map((node) => ({ path: node.path, name: node.name, folder: true }));
  const files = here.files
    .filter((item) => matches(item.name, search.value))
    .map((item) => ({ path: item.path, name: item.name, folder: false, file: item }));
  return [...folders, ...files];
});

const spaceLine = computed(() => {
  const space = listing.value?.space;
  if (!space) return '';
  const used = formatSize(space.used_bytes, locale.value);
  return space.limit_bytes === null
    ? `${t('base.files.space.label')}: ${t('base.files.space.unlimited', { used })}`
    : `${t('base.files.space.label')}: ${t('base.files.space.of', { used, limit: formatSize(space.limit_bytes, locale.value) })}`;
});
/** How full the plan's space is, exact: the meter's bar (its line says the amounts, in the units that fit them). */
const spacePercent = computed(() => {
  const space = listing.value?.space;
  return space?.limit_bytes ? (space.used_bytes * 100) / space.limit_bytes : 0;
});

const when = (iso: string | null) =>
  iso ? new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso)) : '';

/** The sentence of a refusal, by its code; with the file's extension or the plan's space where it says them. */
function reasonOf(failure: unknown, name = ''): string {
  const code = (failure as ApiError | undefined)?.code;
  const limit = listing.value?.space.limit_bytes;
  return t(refusalKey(code), {
    extension: extensionOf(name),
    space: limit ? formatSize(limit, locale.value) : '',
  });
}

function openFolder(path: string): void {
  search.value = '';
  void router.replace({ path: route.path, query: path ? { folder: path } : {} });
}

const folderLabel = (path: string) => (path ? nameOf(path) : t('base.files.root'));

// ── Upload (BASE-G83) ──
const picker = useTemplateRef<HTMLInputElement>('picker');
const progress = ref<{ done: number; total: number } | null>(null);
const dropping = ref(false);

async function uploadAll(chosen: File[]): Promise<void> {
  if (!chosen.length || progress.value) return;
  const into = folder.value;
  const failures: string[] = [];
  const renamed: string[] = [];
  let saved = 0;
  progress.value = { done: 0, total: chosen.length };
  for (const file of chosen) {
    if (tooLarge(file.size)) {
      failures.push(t('base.files.uploadFailed', { name: file.name, reason: t('base.files.refusal.tooLarge') }));
    } else {
      try {
        const content_base64 = bytesToBase64(new Uint8Array(await file.arrayBuffer()));
        const answer = await upload.run({ folder: into, name: file.name, content_base64 });
        saved += 1;
        if (answer.name !== file.name.trim().normalize('NFC')) renamed.push(answer.name);
      } catch (failure) {
        failures.push(t('base.files.uploadFailed', { name: file.name, reason: reasonOf(failure, file.name) }));
      }
    }
    progress.value = { done: progress.value.done + 1, total: chosen.length };
  }
  progress.value = null;
  if (failures.length) void toastError(failures.join('\n'));
  if (saved) {
    void toastSuccess(
      renamed.length === 1 && saved === 1
        ? t('base.files.uploadedAs', { name: renamed[0] })
        : t('base.files.uploaded'),
    );
  }
}

function picked(event: Event): void {
  const input = event.target as HTMLInputElement;
  const chosen = Array.from(input.files ?? []);
  input.value = '';
  void uploadAll(chosen);
}

/** What is being dragged from the list: its path, to drop on a folder (a move). */
const dragging = ref<string | null>(null);

function draggingFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files');
}

function overManager(event: DragEvent): void {
  if (!can.value.upload || !draggingFiles(event)) return;
  event.preventDefault();
  dropping.value = true;
}

function dropOnManager(event: DragEvent): void {
  dropping.value = false;
  if (!can.value.upload || !draggingFiles(event)) return;
  event.preventDefault();
  void uploadAll(Array.from(event.dataTransfer?.files ?? []));
}

// ── New folder (BASE-G83) ──
const folderOpen = ref(false);
const folderName = ref('');
const folderError = computed(() =>
  createFolder.error.value ? { message: reasonOf(createFolder.error.value, folderName.value) } : null,
);

function askFolder(): void {
  folderName.value = '';
  createFolder.error.value = null;
  folderOpen.value = true;
}

async function makeFolder(): Promise<void> {
  try {
    await createFolder.run({ parent: folder.value, name: folderName.value });
    folderOpen.value = false;
    void toastSuccess(t('base.files.newFolderDialog.done'));
  } catch {
    // The dialog stays open with the sentence of why (folderError).
  }
}

// ── The actions of an entry ──
const menuFor = ref<Entry | null>(null);
const menuEvent = ref<Event | undefined>(undefined);

function openMenu(entry: Entry, event: Event): void {
  menuEvent.value = event;
  menuFor.value = entry;
}

function act(action: (entry: Entry) => void | Promise<void>): void {
  const entry = menuFor.value;
  menuFor.value = null;
  if (entry) void action(entry);
}

// ── Open and download (BASE-G84) ──
const previewing = ref<FileItem | null>(null);
const previewOpen = ref(false);

function openEntry(entry: Entry): void {
  if (entry.folder) {
    openFolder(entry.path);
    return;
  }
  previewing.value = entry.file ?? null;
  previewOpen.value = true;
}

async function download(item: FileItem): Promise<void> {
  try {
    const { blob, name } = await fetchFile(rawUrl(item.path), item.content_type);
    saveFile(name || item.name, blob);
  } catch (failure) {
    void toastError(t('base.files.downloadFailed', { name: item.name, reason: reasonOf(failure, item.name) }));
  }
}

// ── Rename and move (BASE-G85) ──
const renaming = ref<Entry | null>(null);
const renameOpen = ref(false);
const renameName = ref('');
const renameError = computed(() =>
  rename.error.value ? { message: reasonOf(rename.error.value, renameName.value) } : null,
);

function askRename(entry: Entry): void {
  renaming.value = entry;
  renameName.value = entry.name;
  rename.error.value = null;
  renameOpen.value = true;
}

async function doRename(): Promise<void> {
  const entry = renaming.value;
  if (!entry) return;
  try {
    const answer = await rename.run({ path: entry.path, name: renameName.value });
    renameOpen.value = false;
    void toastSuccess(t('base.files.renameDialog.done'));
    if (entry.folder) followTo(afterMove(folder.value, entry.path, answer.path));
  } catch {
    // The dialog stays open with the sentence of why (renameError).
  }
}

const moving = ref<Entry | null>(null);
const moveOpen = ref(false);
const moveTo = ref('');
const moveError = computed(() => (move.error.value ? { message: reasonOf(move.error.value) } : null));
/** Where `moving` may go: the top and every folder, but never a folder inside itself. */
const destinations = computed(() => {
  const from = moving.value;
  const all = [{ path: '', name: t('base.files.root'), depth: 0 }, ...flat.value.map((f) => ({ ...f, depth: f.depth + 1 }))];
  return from?.folder ? all.filter((f) => f.path !== from.path && !f.path.startsWith(`${from.path}/`)) : all;
});

function askMove(entry: Entry): void {
  moving.value = entry;
  moveTo.value = parentOf(entry.path);
  move.error.value = null;
  moveOpen.value = true;
}

async function relocate(entry: Entry, to: string): Promise<void> {
  const answer = await move.run({ path: entry.path, to });
  void toastSuccess(t('base.files.moveDialog.done', { folder: folderLabel(to) }));
  if (entry.folder) followTo(afterMove(folder.value, entry.path, answer.path));
}

async function doMove(): Promise<void> {
  const entry = moving.value;
  if (!entry) return;
  try {
    await relocate(entry, moveTo.value);
    moveOpen.value = false;
  } catch {
    // The dialog stays open with the sentence of why (moveError).
  }
}

function startDrag(event: DragEvent, entry: Entry): void {
  if (!canMove.value) return;
  dragging.value = entry.path;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', entry.name);
  }
}

async function dropOnFolder(to: string): Promise<void> {
  const from = dragging.value;
  dragging.value = null;
  const entry = entries.value.find((candidate) => candidate.path === from);
  if (!entry) return;
  try {
    await relocate(entry, to);
  } catch (failure) {
    void toastError(t('base.files.moveDialog.failed', { reason: reasonOf(failure) }));
  }
}

function followTo(path: string): void {
  if (path !== folder.value) openFolder(path);
}

// ── Delete (BASE-G86) ──
async function askDelete(entry: Entry): Promise<void> {
  const yes = await confirm({
    title: t(entry.folder ? 'base.files.deleteDialog.folderTitle' : 'base.files.deleteDialog.fileTitle'),
    message: t(entry.folder ? 'base.files.deleteDialog.folderMessage' : 'base.files.deleteDialog.fileMessage', {
      name: entry.name,
    }),
    confirmLabel: t('base.files.deleteDialog.confirm'),
    cancelLabel: t('base.files.deleteDialog.cancel'),
    tone: 'danger',
  });
  if (!yes) return;
  try {
    await remove.run({ path: entry.path });
    void toastSuccess(t(entry.folder ? 'base.files.deleteDialog.folderDone' : 'base.files.deleteDialog.fileDone'));
    if (entry.folder) followTo(afterDelete(folder.value, entry.path));
  } catch (failure) {
    void toastError(t('base.files.deleteDialog.failed', { reason: reasonOf(failure, entry.name) }));
  }
}
</script>

<template>
  <AppPage :title="t('base.files.title')">
    <div
      class="files"
      data-testid="files-manager"
      @dragover="overManager($event)"
      @dragleave="dropping = false"
      @drop="dropOnManager($event)"
    >
      <InlineFeedback
        v-if="failed"
        tone="danger"
        data-testid="files-error"
        :heading="t('base.files.error.heading')"
      >
        {{ t(refusalKey(error?.code)) }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="files-retry"
            @click="refresh()"
          >
            {{ t('base.files.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <div class="files-layout">
        <aside
          class="files-card files-folders"
          data-testid="files-tree"
        >
          <h2
            class="files-section-label"
            data-testid="files-folders-label"
          >
            {{ t('base.files.folders') }}
          </h2>
          <button
            type="button"
            class="files-root"
            :class="{ 'files-root-open': !folder }"
            data-testid="files-root"
            :aria-current="!folder ? 'true' : undefined"
            @click="openFolder('')"
            @dragover="canMove && dragging && parentOf(dragging) ? $event.preventDefault() : undefined"
            @drop.prevent="canMove && dragging && parentOf(dragging) ? dropOnFolder('') : undefined"
          >
            <HubIcon
              name="ion:folder-outline"
              decorative
            />
            {{ t('base.files.root') }}
          </button>
          <FileTree
            :nodes="tree"
            :selected="folder"
            :droppable="canMove"
            :dragging="dragging"
            @select="openFolder($event)"
            @drop="dropOnFolder($event)"
          />
        </aside>
        <div
          class="files-card files-folder-select"
          data-testid="files-folder-select"
        >
          <ion-select
            :value="folder"
            interface="popover"
            :label="t('base.files.folders')"
            label-placement="stacked"
            @ion-change="openFolder(String($event.detail.value ?? ''))"
          >
            <ion-select-option value="">
              {{ t('base.files.root') }}
            </ion-select-option>
            <ion-select-option
              v-for="option in flat"
              :key="option.path"
              :value="option.path"
            >
              {{ '  '.repeat(option.depth + 1) + option.name }}
            </ion-select-option>
          </ion-select>
        </div>
        <section class="files-card files-main">
          <header class="files-toolbar">
            <ion-searchbar
              class="files-search"
              data-testid="files-search"
              :value="search"
              :placeholder="t('base.files.search')"
              @ion-input="search = String($event.detail.value ?? '')"
            />
            <div
              class="files-buttons"
              role="group"
              :aria-label="t('base.files.view.label')"
            >
              <ion-button
                fill="clear"
                size="small"
                data-testid="files-view-list"
                :aria-label="t('base.files.view.list')"
                :title="t('base.files.view.list')"
                :aria-pressed="view === 'list' ? 'true' : 'false'"
                :class="{ 'files-view-on': view === 'list' }"
                @click="view = 'list'"
              >
                <HubIcon
                  slot="icon-only"
                  name="ion:list-outline"
                />
              </ion-button>
              <ion-button
                fill="clear"
                size="small"
                data-testid="files-view-grid"
                :aria-label="t('base.files.view.grid')"
                :title="t('base.files.view.grid')"
                :aria-pressed="view === 'grid' ? 'true' : 'false'"
                :class="{ 'files-view-on': view === 'grid' }"
                @click="view = 'grid'"
              >
                <HubIcon
                  slot="icon-only"
                  name="ion:grid-outline"
                />
              </ion-button>
            </div>
            <div
              v-if="can.upload"
              class="files-buttons"
            >
              <ion-button
                fill="outline"
                size="small"
                data-testid="files-new-folder"
                @click="askFolder()"
              >
                <HubIcon
                  slot="start"
                  name="ion:folder-outline"
                />
                {{ t('base.files.newFolder') }}
              </ion-button>
              <ion-button
                size="small"
                data-testid="files-upload"
                :disabled="!!progress"
                @click="picker?.click()"
              >
                <HubIcon
                  slot="start"
                  name="ion:cloud-upload-outline"
                />
                {{ t('base.files.upload') }}
              </ion-button>
            </div>
            <input
              ref="picker"
              class="files-picker"
              type="file"
              multiple
              tabindex="-1"
              aria-hidden="true"
              data-testid="files-upload-input"
              @change="picked($event)"
            >
          </header>
          <nav
            class="files-crumbs"
            :aria-label="t('base.files.folders')"
          >
            <button
              type="button"
              data-crumb=""
              @click="openFolder('')"
            >
              {{ t('base.files.root') }}
            </button>
            <template
              v-for="crumb in listing?.crumbs ?? []"
              :key="crumb.path"
            >
              <HubIcon
                name="ion:chevron-forward-outline"
                decorative
              />
              <button
                type="button"
                :data-crumb="crumb.path"
                :aria-current="crumb.path === folder ? 'true' : undefined"
                @click="openFolder(crumb.path)"
              >
                {{ crumb.name }}
              </button>
            </template>
            <ion-button
              v-if="folder && listing && (can.upload || can.delete)"
              fill="clear"
              size="small"
              data-testid="files-folder-actions"
              :aria-label="t('base.files.actions.label', { name: nameOf(folder) })"
              @click="openMenu({ path: folder, name: nameOf(folder), folder: true }, $event)"
            >
              <HubIcon
                slot="icon-only"
                name="ion:ellipsis-vertical"
              />
            </ion-button>
          </nav>
          <template v-if="listing">
            <UsageMeter
              v-if="listing.space.limit_bytes !== null"
              class="files-space"
              data-testid="files-space"
              size="sm"
              :label="spaceLine"
              :percent="spacePercent"
              :locale="locale"
            />
            <p
              v-else
              class="files-space"
              data-testid="files-space"
            >
              {{ spaceLine }}
            </p>
          </template>
          <p
            v-if="progress"
            class="files-muted"
            role="status"
            data-testid="files-progress"
          >
            {{ t('base.files.uploading', { done: progress.done + 1 > progress.total ? progress.total : progress.done + 1, total: progress.total }) }}
          </p>
          <p
            v-if="loading"
            class="files-muted"
            role="status"
            data-testid="files-loading"
          >
            {{ t('base.files.loading') }}
          </p>
          <template v-else-if="listing">
            <EmptyState
              v-if="!entries.length && !search.trim()"
              icon="ion:folder-outline"
              data-testid="files-empty"
              :heading="t('base.files.empty')"
              :message="can.upload ? t('base.files.emptyHint') : undefined"
            />
            <p
              v-else-if="!entries.length"
              class="files-muted"
              data-testid="files-no-match"
            >
              {{ t('base.files.noMatch', { search: search.trim() }) }}
            </p>
            <ul
              v-else
              class="files-items"
              :class="view === 'grid' ? 'files-grid' : 'files-list'"
              data-testid="files-items"
            >
              <li
                v-for="entry in entries"
                :key="entry.path"
                class="files-item"
                :data-item="entry.path"
                :data-kind="entry.folder ? 'folder' : 'file'"
                :draggable="canMove ? 'true' : 'false'"
                @dragstart="startDrag($event, entry)"
                @dragend="dragging = null"
                @dragover="entry.folder && canMove && dragging && dragging !== entry.path ? $event.preventDefault() : undefined"
                @drop.prevent="entry.folder && canMove && dragging && dragging !== entry.path ? dropOnFolder(entry.path) : undefined"
              >
                <button
                  type="button"
                  class="files-item-main"
                  data-testid="files-item-main"
                  @click="openEntry(entry)"
                >
                  <span class="files-item-icon">
                    <HubIcon
                      :name="entry.folder ? 'ion:folder-outline' : iconFor(entry.file?.preview ?? '')"
                      decorative
                    />
                  </span>
                  <span class="files-item-name">{{ entry.name }}</span>
                  <span
                    v-if="entry.file"
                    class="files-item-meta"
                  >
                    {{ formatSize(entry.file.size, locale) }}<template v-if="view === 'list' && entry.file.modified"> · {{ when(entry.file.modified) }}</template>
                  </span>
                  <span
                    v-else
                    class="files-item-meta"
                  >{{ t('base.files.folder') }}</span>
                </button>
                <ion-button
                  fill="clear"
                  size="small"
                  class="files-item-actions"
                  data-testid="files-item-actions"
                  :aria-label="t('base.files.actions.label', { name: entry.name })"
                  @click="openMenu(entry, $event)"
                >
                  <HubIcon
                    slot="icon-only"
                    name="ion:ellipsis-vertical"
                  />
                </ion-button>
              </li>
            </ul>
          </template>
          <p
            v-if="dropping"
            class="files-drop"
            data-testid="files-drop"
          >
            {{ t('base.files.drop') }}
          </p>
        </section>
      </div>
    </div>

    <ion-popover
      :is-open="menuFor !== null"
      :event="menuEvent"
      data-testid="files-actions-menu"
      @did-dismiss="menuFor = null"
    >
      <ion-list
        v-if="menuFor"
        lines="none"
      >
        <template v-if="!menuFor.folder && menuFor.file">
          <ion-item
            button
            :detail="false"
            data-testid="files-action-open"
            @click="act(openEntry)"
          >
            <HubIcon
              slot="start"
              name="ion:open-outline"
            />
            <ion-label>{{ t('base.files.actions.open') }}</ion-label>
          </ion-item>
          <ion-item
            button
            :detail="false"
            data-testid="files-action-download"
            @click="act((entry) => entry.file && download(entry.file))"
          >
            <HubIcon
              slot="start"
              name="ion:download-outline"
            />
            <ion-label>{{ t('base.files.actions.download') }}</ion-label>
          </ion-item>
        </template>
        <ion-item
          v-if="can.upload"
          button
          :detail="false"
          data-testid="files-action-rename"
          @click="act(askRename)"
        >
          <HubIcon
            slot="start"
            name="ion:create-outline"
          />
          <ion-label>{{ t(menuFor.folder ? 'base.files.actions.renameFolder' : 'base.files.actions.rename') }}</ion-label>
        </ion-item>
        <ion-item
          v-if="canMove"
          button
          :detail="false"
          data-testid="files-action-move"
          @click="act(askMove)"
        >
          <HubIcon
            slot="start"
            name="ion:swap-horizontal-outline"
          />
          <ion-label>{{ t('base.files.actions.move') }}</ion-label>
        </ion-item>
        <ion-item
          v-if="can.delete"
          button
          :detail="false"
          data-testid="files-action-delete"
          @click="act(askDelete)"
        >
          <HubIcon
            slot="start"
            name="ion:trash-outline"
          />
          <ion-label color="danger">
            {{ t(menuFor.folder ? 'base.files.actions.deleteFolder' : 'base.files.actions.delete') }}
          </ion-label>
        </ion-item>
      </ion-list>
    </ion-popover>

    <FormModal
      v-model:open="folderOpen"
      testid="files-new-folder-dialog"
      :title="t('base.files.newFolderDialog.title')"
      :submit-label="t('base.files.newFolderDialog.create')"
      :pending="createFolder.pending.value"
      :error="folderError"
      :submit-disabled="!folderName.trim()"
      @submit="makeFolder()"
      @cancel="folderOpen = false"
    >
      <ion-input
        data-testid="files-new-folder-name"
        data-autofocus
        mode="md"
        fill="outline"
        label-placement="floating"
        :label="t('base.files.newFolderDialog.name')"
        :value="folderName"
        :maxlength="MAX_FOLDER_NAME"
        :counter="true"
        @ion-input="folderName = String($event.detail.value ?? '')"
      />
    </FormModal>

    <FormModal
      v-model:open="renameOpen"
      testid="files-rename-dialog"
      :title="t(renaming?.folder ? 'base.files.renameDialog.titleFolder' : 'base.files.renameDialog.title')"
      :submit-label="t('base.files.renameDialog.save')"
      :pending="rename.pending.value"
      :error="renameError"
      :submit-disabled="!renameName.trim()"
      @submit="doRename()"
      @cancel="renameOpen = false"
    >
      <ion-input
        data-testid="files-rename-name"
        data-autofocus
        mode="md"
        fill="outline"
        label-placement="floating"
        :label="t('base.files.renameDialog.name')"
        :value="renameName"
        :maxlength="MAX_NAME"
        @ion-input="renameName = String($event.detail.value ?? '')"
      />
    </FormModal>

    <FormModal
      v-model:open="moveOpen"
      testid="files-move-dialog"
      :title="t('base.files.moveDialog.title', { name: moving?.name ?? '' })"
      :submit-label="t('base.files.moveDialog.save')"
      :pending="move.pending.value"
      :error="moveError"
      @submit="doMove()"
      @cancel="moveOpen = false"
    >
      <p class="files-section-label">
        {{ t('base.files.moveDialog.to') }}
      </p>
      <ul
        class="files-destinations"
        role="listbox"
        :aria-label="t('base.files.moveDialog.to')"
      >
        <li
          v-for="option in destinations"
          :key="option.path"
          role="option"
          class="files-destination"
          :class="{ 'files-destination-on': option.path === moveTo }"
          data-testid="files-move-option"
          :data-to="option.path"
          :aria-selected="option.path === moveTo ? 'true' : 'false'"
          :style="{ paddingInlineStart: `${12 + option.depth * 16}px` }"
          tabindex="0"
          @click="moveTo = option.path"
          @keydown.enter.prevent="moveTo = option.path"
        >
          <HubIcon
            name="ion:folder-outline"
            decorative
          />
          {{ option.name }}
        </li>
      </ul>
    </FormModal>

    <FilePreview
      :file="previewing"
      :open="previewOpen"
      @close="previewOpen = false"
      @download="previewing && download(previewing)"
    />
  </AppPage>
</template>

<style scoped>
.files {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.files-layout {
  display: grid;
  grid-template-columns: minmax(200px, 260px) minmax(0, 1fr);
  align-items: start;
  gap: 16px;
}

.files-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}

.files-folder-select {
  display: none;
}

.files-section-label {
  margin: 4px 8px 8px;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.files-root {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 6px 10px;
  border: 0;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.files-root-open {
  background: var(--ep-primary-tint, #e6f0ff);
  color: var(--ep-primary-text, #0b5ed7);
  font-weight: 600;
}

.files-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.files-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.files-search {
  flex: 1 1 220px;
  max-width: 360px;
  padding: 0;
  margin-inline-end: auto;
}

.files-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.files-view-on {
  --background: var(--ion-color-light, #f4f5f8);
}

.files-picker {
  display: none;
}

.files-crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 0.9375rem;
}

.files-crumbs button {
  padding: 2px 4px;
  border: 0;
  border-radius: 6px;
  background: none;
  color: var(--ion-color-primary, #3880ff);
  font: inherit;
  overflow-wrap: anywhere;
  cursor: pointer;
}

.files-crumbs button[aria-current='true'] {
  color: inherit;
  font-weight: 600;
}

p.files-space,
.files-muted {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.files-items {
  margin: 0;
  padding: 0;
  list-style: none;
}

.files-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.files-list {
  display: flex;
  flex-direction: column;
}

.files-item {
  position: relative;
  display: flex;
  align-items: center;
  min-width: 0;
  border-radius: 10px;
}

.files-grid .files-item {
  /* Every card of a row as tall as the tallest (a long name wraps), its content from the top. */
  align-items: stretch;
  border: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
}

.files-list .files-item {
  border-bottom: 1px solid var(--ep-border-color, var(--ion-color-light-shade, #d7d8da));
  border-radius: 0;
}

.files-item-main {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 10px;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.files-grid .files-item-main {
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 14px 12px;
}

.files-item-icon {
  display: inline-flex;
  color: var(--ion-color-primary, #3880ff);
  font-size: 1.5rem;
}

.files-item-name {
  min-width: 0;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.files-list .files-item-name {
  flex: 1;
}

.files-item-meta {
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.8125rem;
  white-space: nowrap;
}

.files-grid .files-item-actions {
  position: absolute;
  inset-block-start: 4px;
  inset-inline-end: 0;
}

.files-drop {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  border: 2px dashed var(--ion-color-primary, #3880ff);
  border-radius: var(--ep-radius, 12px);
  background: rgb(255 255 255 / 85%);
  font-weight: 600;
  pointer-events: none;
}

.files-destinations {
  max-height: 50vh;
  margin: 0;
  padding: 0;
  overflow: auto;
  list-style: none;
}

.files-destination {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
}

.files-destination-on {
  background: var(--ep-primary-tint, #e6f0ff);
  color: var(--ep-primary-text, #0b5ed7);
  font-weight: 600;
}

@media (max-width: 767px) {
  .files-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .files-folders {
    display: none;
  }

  .files-folder-select {
    display: block;
  }

  .files-toolbar {
    justify-content: flex-start;
  }

  .files-search {
    flex-basis: 100%;
    max-width: none;
  }
}
</style>
