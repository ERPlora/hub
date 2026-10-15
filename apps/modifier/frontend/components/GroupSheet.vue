<script setup lang="ts">
// The group's sheet (WORKBOOK «Hoja del grupo»; MODIFIER-F04, F05): «Group — {name}» with its rule, the
// group followed live (`modifier.group.get`; gone, the sheet closes), and two sections, 20 rows at a time
// with «Load more»: «Options», each with its supplement, its kitchen name, its own tax category and «By
// default»; «Applies to», each product or category. Whoever may manage adds, edits and deletes options
// (the option form, a confirmation) and applies or stops applying the group (the link form, a
// confirmation); an employee only reads. A group that asks for more options than it has, and cannot
// repeat them, says the till could not complete it. It says `closed` once Ionic dismissed it: unmounting a
// presented modal leaves its overlay on screen.
import { ConfirmDialog, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonModal, IonTitle, IonToolbar } from '@ionic/vue';
import { computed, nextTick, ref, watch } from 'vue';

import { useSheetList } from '../composables/useSheetList';
import { useLocale, useT } from '../composables/useT';
import { choiceRule, formatDelta } from '../lib/format';
import type { GroupOut, LinkOut, OptionOut } from '../operations';
import LinkFormModal from './LinkFormModal.vue';
import OptionFormModal from './OptionFormModal.vue';

const props = defineProps<{
  /** The group as the list painted it: what the sheet shows until its own read arrives. */
  group: GroupOut;
}>();

const open = defineModel<boolean>('open', { default: false });
/** Ionic has dismissed it (its animation done): only now may the page unmount it. */
const emit = defineEmits<{ closed: [] }>();

function dismissed(): void {
  open.value = false;
  emit('closed');
}

const t = useT();
const locale = useLocale();
const session = useSession();
const canManage = computed(() => session.can('modifier.manage'));

const detail = useLive('modifier.group.get', () => ({ id: props.group.id }));
const group = computed<GroupOut>(() => detail.data.value ?? props.group);

const options = useSheetList('modifier.option.list', () => ({ group_id: props.group.id }));
const links = useSheetList('modifier.link.list', () => ({ group_id: props.group.id }));

const rule = computed(() => choiceRule(group.value, t));
const short = computed(
  () => !group.value.allow_repeat && options.total.value > 0 && options.total.value < group.value.min_choices,
);
const delta = (cents: number) => formatDelta(cents, locale.value, t('modifier.free'));
const target = (link: LinkOut) =>
  link.target_kind === 'product' ? `${link.product_name ?? ''} (${link.product_sku ?? ''})` : (link.category_name ?? '');
const targetLabel = (link: LinkOut) =>
  link.target_kind === 'product'
    ? t('modifier.sheet.product', { name: link.product_name ?? '', sku: link.product_sku ?? '' })
    : t('modifier.sheet.category', { name: link.category_name ?? '' });

// Options: the form and the deletion.
const editing = ref<OptionOut | null>(null);
const optionFormOpen = ref(false);
function openOption(option: OptionOut | null): void {
  editing.value = option;
  optionFormOpen.value = true;
}
const removeOption = useCommand('modifier.option.delete');
const deleting = ref<OptionOut | null>(null);
const deleteOpen = ref(false);
function askDelete(option: OptionOut): void {
  removeOption.error.value = null;
  deleting.value = option;
  deleteOpen.value = true;
}
async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await removeOption.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

// Links: the form and the detachment.
const linkFormOpen = ref(false);
const detach = useCommand('modifier.link.detach');
const detaching = ref<LinkOut | null>(null);
const detachOpen = ref(false);
function askDetach(link: LinkOut): void {
  detach.error.value = null;
  detaching.value = link;
  detachOpen.value = true;
}
async function confirmDetach(): Promise<void> {
  if (!detaching.value) return;
  try {
    await detach.run({ id: detaching.value.id });
  } catch {
    return; // The dialog says why.
  }
  detachOpen.value = false;
}

// The group was deleted elsewhere: its open dialog closes first, then the sheet. A dialog still presented
// when the page unmounts the sheet would stay on screen over it.
watch(
  () => detail.error.value?.code,
  async (code) => {
    if (code !== 'not_found') return;
    const dialogOpen = optionFormOpen.value || linkFormOpen.value || deleteOpen.value || detachOpen.value;
    optionFormOpen.value = false;
    linkFormOpen.value = false;
    deleteOpen.value = false;
    detachOpen.value = false;
    if (dialogOpen) await nextTick();
    open.value = false;
  },
);
</script>

<template>
  <ion-modal
    :is-open="open"
    data-testid="modifier-sheet"
    @did-dismiss="dismissed"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title data-testid="modifier-sheet-title">
          {{ t('modifier.sheet.title', { name: group.name }) }}
        </ion-title>
        <ion-buttons slot="end">
          <ion-button
            data-testid="modifier-sheet-close"
            @click="open = false"
          >
            {{ t('modifier.close') }}
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <p
        class="modifier-sheet__rule"
        data-testid="modifier-sheet-rule"
      >
        {{ rule }}
      </p>
      <InlineFeedback
        v-if="short"
        tone="warning"
        data-testid="modifier-sheet-short"
      >
        {{ t('modifier.sheet.short', { min: group.min_choices, count: options.total.value }) }}
      </InlineFeedback>

      <section class="modifier-sheet__section">
        <header class="modifier-sheet__head">
          <h2>{{ t('modifier.sheet.options') }}</h2>
          <ion-button
            v-if="canManage"
            size="small"
            data-testid="modifier-sheet-options-add"
            @click="openOption(null)"
          >
            {{ t('modifier.sheet.addOption') }}
          </ion-button>
        </header>
        <InlineFeedback
          v-if="options.status.value === 'error'"
          tone="danger"
          data-testid="modifier-sheet-options-error"
          :heading="t('modifier.sheet.optionsError')"
        >
          {{ options.error.value?.message }}
        </InlineFeedback>
        <p
          v-else-if="options.data.value === undefined"
          data-testid="modifier-sheet-options-loading"
        >
          {{ t('modifier.loading') }}
        </p>
        <p
          v-else-if="options.rows.value.length === 0"
          class="modifier-sheet__empty"
          data-testid="modifier-sheet-options-empty"
        >
          {{ t('modifier.sheet.noOptions') }}
        </p>
        <ul class="modifier-sheet__list">
          <li
            v-for="option in options.rows.value"
            :key="option.id"
            class="modifier-sheet__row"
            :data-testid="`modifier-sheet-options-row-${option.id}`"
          >
            <div class="modifier-sheet__main">
              <strong>{{ option.name }}</strong>
              <span class="modifier-sheet__delta">{{ delta(option.price_delta) }}</span>
              <StatusPill
                v-if="option.is_default"
                size="sm"
                tone="success"
                :label="t('modifier.sheet.default')"
              />
            </div>
            <div
              v-if="option.kitchen_name || option.tax_category_name"
              class="modifier-sheet__line"
            >
              <span v-if="option.kitchen_name">{{ t('modifier.sheet.kitchen', { name: option.kitchen_name }) }}</span>
              <span v-if="option.tax_category_name">{{ t('modifier.sheet.ownTax', { name: option.tax_category_name }) }}</span>
            </div>
            <div
              v-if="canManage"
              class="modifier-sheet__actions"
            >
              <ion-button
                size="small"
                fill="clear"
                :data-testid="`modifier-sheet-options-edit-${option.id}`"
                @click="openOption(option)"
              >
                {{ t('modifier.sheet.edit') }}
              </ion-button>
              <ion-button
                size="small"
                fill="clear"
                color="danger"
                :data-testid="`modifier-sheet-options-delete-${option.id}`"
                @click="askDelete(option)"
              >
                {{ t('modifier.sheet.delete') }}
              </ion-button>
            </div>
          </li>
        </ul>
        <div
          v-if="options.hasMore.value"
          class="modifier-sheet__more"
        >
          <span data-testid="modifier-sheet-options-count">{{ t('modifier.showing', { shown: options.rows.value.length, total: options.total.value }) }}</span>
          <ion-button
            fill="clear"
            data-testid="modifier-sheet-options-more"
            @click="options.loadMore()"
          >
            {{ t('modifier.loadMore') }}
          </ion-button>
        </div>
      </section>

      <section class="modifier-sheet__section">
        <header class="modifier-sheet__head">
          <h2>{{ t('modifier.sheet.appliesTo') }}</h2>
          <ion-button
            v-if="canManage"
            size="small"
            data-testid="modifier-sheet-links-add"
            @click="linkFormOpen = true"
          >
            {{ t('modifier.sheet.addLink') }}
          </ion-button>
        </header>
        <InlineFeedback
          v-if="links.status.value === 'error'"
          tone="danger"
          data-testid="modifier-sheet-links-error"
          :heading="t('modifier.sheet.linksError')"
        >
          {{ links.error.value?.message }}
        </InlineFeedback>
        <p
          v-else-if="links.data.value === undefined"
          data-testid="modifier-sheet-links-loading"
        >
          {{ t('modifier.loading') }}
        </p>
        <p
          v-else-if="links.rows.value.length === 0"
          class="modifier-sheet__empty"
          data-testid="modifier-sheet-links-empty"
        >
          {{ t('modifier.sheet.noLinks') }}
        </p>
        <ul class="modifier-sheet__list">
          <li
            v-for="link in links.rows.value"
            :key="link.id"
            class="modifier-sheet__row modifier-sheet__row--inline"
            :data-testid="`modifier-sheet-links-row-${link.id}`"
          >
            <span>{{ targetLabel(link) }}</span>
            <ion-button
              v-if="canManage"
              size="small"
              fill="clear"
              color="danger"
              :data-testid="`modifier-sheet-links-detach-${link.id}`"
              @click="askDetach(link)"
            >
              {{ t('modifier.sheet.detach') }}
            </ion-button>
          </li>
        </ul>
        <div
          v-if="links.hasMore.value"
          class="modifier-sheet__more"
        >
          <span data-testid="modifier-sheet-links-count">{{ t('modifier.showing', { shown: links.rows.value.length, total: links.total.value }) }}</span>
          <ion-button
            fill="clear"
            data-testid="modifier-sheet-links-more"
            @click="links.loadMore()"
          >
            {{ t('modifier.loadMore') }}
          </ion-button>
        </div>
      </section>
    </ion-content>
  </ion-modal>
  <OptionFormModal
    v-model:open="optionFormOpen"
    :group="group"
    :option="editing"
  />
  <LinkFormModal
    v-model:open="linkFormOpen"
    :group="group"
  />
  <ConfirmDialog
    v-model:open="deleteOpen"
    testid="modifier-sheet-option-delete"
    tone="danger"
    :title="t('modifier.options.delete.title')"
    :message="deleting ? t('modifier.options.delete.message', { name: deleting.name }) : ''"
    :confirm-label="t('modifier.options.delete.confirm')"
    :cancel-label="t('modifier.cancel')"
    :pending="removeOption.pending.value"
    :error="removeOption.error.value"
    @confirm="confirmDelete"
    @cancel="deleteOpen = false"
  />
  <ConfirmDialog
    v-model:open="detachOpen"
    testid="modifier-sheet-link-detach"
    tone="danger"
    :title="t('modifier.links.detach.title')"
    :message="detaching ? t('modifier.links.detach.message', { group: group.name, target: target(detaching) }) : ''"
    :confirm-label="t('modifier.links.detach.confirm')"
    :cancel-label="t('modifier.cancel')"
    :pending="detach.pending.value"
    :error="detach.error.value"
    @confirm="confirmDetach"
    @cancel="detachOpen = false"
  />
</template>

<style scoped>
.modifier-sheet__rule {
  margin: 0 0 12px;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.modifier-sheet__section {
  margin-top: 18px;
}
.modifier-sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.modifier-sheet__head h2 {
  margin: 0;
  font-size: 1.05rem;
}
.modifier-sheet__empty {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.modifier-sheet__list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.modifier-sheet__row {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--ion-border-color, #e5e3dd);
  border-radius: 10px;
}
.modifier-sheet__row--inline {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.modifier-sheet__main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.modifier-sheet__delta {
  font-variant-numeric: tabular-nums;
}
.modifier-sheet__line {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 0.88rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.modifier-sheet__actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}
.modifier-sheet__more {
  display: grid;
  justify-items: center;
  gap: 4px;
  margin-top: 8px;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
