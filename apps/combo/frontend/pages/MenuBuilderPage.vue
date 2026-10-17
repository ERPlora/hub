<script setup lang="ts">
// The menu's builder (WORKBOOK «Pantallas · Constructor del menú»; COMBO-F05, F06, F12), opened from a
// row of Menus: `combo.combo.get` live. On top, «All menus», the name and the closed price, what the menu
// does on the receipt (one line eaten in, split to take away) and, when the till does not offer it yet,
// why. Then «Courses»: a card per course in the order the till asks them (the handle and the arrows save
// the whole order at once; «Withdraw» asks first), and «Add a course», which edits the course whose
// «Edit details» was pressed. Every change comes back through the stream; a menu withdrawn meanwhile
// (here or on another device) leaves only «This menu no longer exists» and the way back.
import { ConfirmDialog, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonReorderGroup } from '@ionic/vue';
import { computed, ref } from 'vue';

import CourseCard from '../components/CourseCard.vue';
import CourseForm from '../components/CourseForm.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { formatMoney } from '../lib/format';
import type { GroupOut } from '../operations';

const props = defineProps<{ id: string }>();

const session = useSession();
const canManage = computed(() => session.can('combo.manage'));
const t = useT();
const locale = useLocale();

const { data: menu, status, error } = useLive('combo.combo.get', () => ({ id: props.id }));
const blocked = computed(() => blockingError(error.value));
// The stream keeps the last menu it painted; once the server says it is gone, nothing of it is offered.
const gone = computed(() => error.value?.code === 'not_found');
const shown = computed(() => (gone.value ? undefined : menu.value));
const courses = computed(() => shown.value?.groups ?? []);
const goods = computed(() => menu.value?.supply_kind === 'goods');

// The order of the courses: the arrows of a card and the handle end in the same write.
const reorder = useCommand('combo.group.reorder');

function moved<T>(list: readonly T[], from: number, to: number): T[] {
  const out = [...list];
  const [row] = out.splice(from, 1);
  out.splice(to, 0, row);
  return out;
}

async function saveOrder(ids: string[]): Promise<void> {
  try {
    await reorder.run({ id: props.id, group_ids: ids });
  } catch {
    // Said above the courses; the live menu comes back with what the server holds.
  }
}

function step(index: number, delta: -1 | 1): void {
  const to = index + delta;
  if (to < 0 || to >= courses.value.length) return;
  void saveOrder(moved(courses.value, index, to).map((course) => course.id));
}

function onReorder(event: CustomEvent<{ from: number; to: number; complete: (data?: boolean | unknown[]) => unknown }>): void {
  const { from, to } = event.detail;
  // Ionic puts the card back; the live menu paints the order the server saved.
  event.detail.complete(false);
  if (from !== to) void saveOrder(moved(courses.value, from, to).map((course) => course.id));
}

// Editing a course in the form at the foot, and withdrawing one.
const editing = ref<GroupOut | null>(null);
const remove = useCommand('combo.group.delete');
const removing = ref<GroupOut | null>(null);
const removeOpen = ref(false);

function askRemove(course: GroupOut): void {
  remove.error.value = null;
  removing.value = course;
  removeOpen.value = true;
}

async function confirmRemove(): Promise<void> {
  if (!removing.value) return;
  try {
    await remove.run({ id: removing.value.id });
  } catch {
    return; // The dialog says why.
  }
  if (editing.value?.id === removing.value.id) editing.value = null;
  removeOpen.value = false;
}
</script>

<template>
  <AppPage
    :title="shown?.name ?? $t('combo.title')"
    back-href="/combo/menus"
    content-layout="detail"
  >
    <PageNotices
      testid="combo-builder"
      :status="status"
      :error="error"
    />
    <div
      v-if="!blocked"
      class="combo-builder"
    >
      <div class="combo-builder__head">
        <ion-button
          size="small"
          fill="clear"
          router-link="/combo/menus"
          router-direction="back"
          data-testid="combo-builder-back"
        >
          <HubIcon
            slot="start"
            name="ion:arrow-back-outline"
          />
          {{ $t('combo.builder.back') }}
        </ion-button>
        <template v-if="shown">
          <span
            class="combo-builder__name"
            data-testid="combo-builder-name"
          >{{ shown.name }}</span>
          <span
            class="combo-builder__price"
            data-testid="combo-builder-price"
          >{{ formatMoney(shown.price, locale) }}</span>
        </template>
      </div>

      <InlineFeedback
        v-if="gone"
        tone="warning"
        icon="ion:trash-outline"
        :heading="t('combo.builder.goneTitle')"
        data-testid="combo-builder-gone"
      >
        {{ $t('combo.builder.goneMessage') }}
      </InlineFeedback>

      <template v-if="shown">
        <InlineFeedback
          :tone="goods ? 'warning' : 'info'"
          icon="ion:receipt-outline"
          data-testid="combo-builder-supply"
        >
          {{ goods ? $t('combo.builder.goodsWarning') : $t('combo.builder.serviceWarning') }}
        </InlineFeedback>
        <InlineFeedback
          v-if="shown.blockers.length"
          tone="warning"
          :heading="t('combo.builder.notOnTill')"
          data-testid="combo-builder-blockers"
        >
          <ul class="combo-builder__blockers">
            <li
              v-for="blocker in shown.blockers"
              :key="`${blocker.code}-${blocker.group_id ?? ''}`"
            >
              {{ blocker.message }}
            </li>
          </ul>
        </InlineFeedback>
        <InlineFeedback
          v-if="reorder.error.value"
          tone="danger"
          data-testid="combo-builder-reorder-error"
        >
          {{ reorder.error.value.message }}
        </InlineFeedback>
      </template>

      <section
        v-if="!gone"
        class="combo-builder__courses"
      >
        <h2 class="combo-builder__title">
          {{ $t('combo.courses.title') }}
        </h2>
        <p class="combo-builder__help">
          {{ $t('combo.courses.help') }}
        </p>
        <p
          v-if="status === 'loading' && !menu"
          class="combo-builder__muted"
          data-testid="combo-builder-loading"
        >
          {{ $t('combo.courses.loading') }}
        </p>
        <InlineFeedback
          v-else-if="status === 'error' && !blocked"
          tone="danger"
          :heading="t('combo.courses.loadError')"
          data-testid="combo-builder-error"
        >
          {{ error?.message }}
        </InlineFeedback>
        <p
          v-else-if="menu && courses.length === 0"
          class="combo-builder__muted"
          data-testid="combo-builder-empty"
        >
          {{ $t('combo.courses.empty') }}
        </p>
        <ion-reorder-group
          v-if="courses.length"
          class="combo-builder__list"
          data-testid="combo-builder-courses"
          :disabled="!canManage"
          @ion-item-reorder="onReorder"
        >
          <CourseCard
            v-for="(course, index) in courses"
            :key="course.id"
            :course="course"
            :index="index"
            :count="courses.length"
            @move="step(index, $event)"
            @edit="editing = course"
            @remove="askRemove(course)"
          />
        </ion-reorder-group>
        <CourseForm
          v-if="canManage && menu"
          :combo-id="id"
          :course="editing"
          @done="editing = null"
        />
      </section>
    </div>
    <ConfirmDialog
      v-model:open="removeOpen"
      testid="combo-course-delete"
      tone="danger"
      :title="t('combo.courses.deleteTitle')"
      :message="removing ? t('combo.courses.deleteMessage', { name: removing.name }) : ''"
      :confirm-label="t('combo.courses.deleteConfirm')"
      :cancel-label="t('combo.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmRemove"
      @cancel="removeOpen = false"
    />
  </AppPage>
</template>

<style scoped>
.combo-builder {
  display: grid;
  gap: 0.75rem;
}
.combo-builder > *,
.combo-builder__courses > * {
  min-width: 0;
}
.combo-builder__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
.combo-builder__name {
  font-size: 1.05rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.combo-builder__price {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.combo-builder__blockers {
  margin: 0;
  padding-left: 1.1rem;
}
.combo-builder__courses {
  display: grid;
  gap: 0.75rem;
}
.combo-builder__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}
.combo-builder__help,
.combo-builder__muted {
  margin: 0;
  font-size: 0.85rem;
  opacity: 0.75;
}
.combo-builder__list {
  display: grid;
  gap: 0.75rem;
}
</style>
