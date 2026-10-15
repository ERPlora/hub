<script setup lang="ts">
// «Add a course» at the foot of the builder (COMBO-F05), as the old screen had it: Course name,
// «Minimum picks» (1 or more makes it compulsory, 0 optional; there is no other switch), «Maximum
// picks» (0 is no limit) and «The same option may be picked more than once». A new course goes last
// (the server places it). With a `course` it is «Course · {name}», keeps its place and sends only what
// changed; «Cancel» or a save ends the edit (`done`). A missing name or a ceiling below the floor is
// said before sending; the server's refusals go under their field.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonCheckbox, IonInput } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { GroupOut, GroupPatchIn } from '../operations';

const props = defineProps<{
  comboId: string;
  /** The course being edited; `null` = «Add a course». */
  course: GroupOut | null;
}>();
const emit = defineEmits<{ done: [] }>();

interface Form {
  name: string;
  min: string;
  max: string;
  repeat: boolean;
}

const t = useT();
const create = useCommand('combo.group.create');
const update = useCommand('combo.group.update');
const error = computed(() => (props.course ? update.error.value : create.error.value));
const fields = computed(() => error.value?.fields ?? {});
const pending = computed(() => create.pending.value || update.pending.value);

const fromCourse = (course: GroupOut | null): Form =>
  course
    ? { name: course.name, min: String(course.min_choices), max: String(course.max_choices), repeat: course.allow_repeat }
    : { name: '', min: '1', max: '1', repeat: false };

const form = ref<Form>(fromCourse(props.course));
const reason = ref('');

watch(
  () => props.course?.id,
  () => {
    form.value = fromCourse(props.course);
    reason.value = '';
    create.error.value = null;
    update.error.value = null;
  },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const count = (value: string): number => {
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) ? Number(trimmed) : (trimmed as unknown as number);
};

async function save(): Promise<void> {
  reason.value = '';
  const name = form.value.name.trim();
  const min = count(form.value.min);
  const max = count(form.value.max);
  if (!name) {
    reason.value = t('combo.courseForm.noName');
    return;
  }
  if (typeof min === 'number' && typeof max === 'number' && max !== 0 && max < min) {
    reason.value = t('combo.courseForm.ceiling', { max, min });
    return;
  }
  try {
    if (props.course) {
      const change: GroupPatchIn = { id: props.course.id };
      if (name !== props.course.name) change.name = name;
      if (min !== props.course.min_choices) change.min_choices = min;
      if (max !== props.course.max_choices) change.max_choices = max;
      if (form.value.repeat !== props.course.allow_repeat) change.allow_repeat = form.value.repeat;
      if (Object.keys(change).length > 1) await update.run(change);
      emit('done');
    } else {
      await create.run({ combo_id: props.comboId, name, min_choices: min, max_choices: max, allow_repeat: form.value.repeat });
      form.value = fromCourse(null);
    }
  } catch {
    // Said under its field or below the form; what was typed stays.
  }
}

function cancel(): void {
  update.error.value = null;
  emit('done');
}

const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const loose = computed(() => {
  const known = ['name', 'min_choices', 'max_choices'];
  return error.value && !Object.keys(fields.value).some((key) => known.includes(key)) ? error.value.message : '';
});
</script>

<template>
  <section
    class="combo-course-form"
    data-testid="combo-course-form"
  >
    <h3
      class="combo-course-form__title"
      data-testid="combo-course-form-title"
    >
      {{ course ? $t('combo.courseForm.titleEdit', { name: course.name }) : $t('combo.courseForm.titleNew') }}
    </h3>
    <div class="combo-course-form__row">
      <ion-input
        data-testid="combo-course-form-name"
        :value="form.name"
        :label="$t('combo.courseForm.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="255"
        :error-text="fields.name"
        :class="invalid(fields.name)"
        @ion-input="form = { ...form, name: text($event.detail.value) }"
      />
      <ion-input
        data-testid="combo-course-form-min"
        type="number"
        inputmode="numeric"
        min="0"
        max="50"
        :value="form.min"
        :label="$t('combo.courseForm.min')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="fields.min_choices"
        :class="invalid(fields.min_choices)"
        @ion-input="form = { ...form, min: text($event.detail.value) }"
      />
      <ion-input
        data-testid="combo-course-form-max"
        type="number"
        inputmode="numeric"
        min="0"
        max="50"
        :value="form.max"
        :label="$t('combo.courseForm.max')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="fields.max_choices"
        :class="invalid(fields.max_choices)"
        @ion-input="form = { ...form, max: text($event.detail.value) }"
      />
    </div>
    <p class="combo-course-form__help">
      {{ $t('combo.courseForm.minHelp') }}
    </p>
    <p class="combo-course-form__help">
      {{ $t('combo.courseForm.maxHelp') }}
    </p>
    <ion-checkbox
      data-testid="combo-course-form-repeat"
      :checked="form.repeat"
      label-placement="end"
      justify="start"
      @ion-change="form = { ...form, repeat: $event.detail.checked }"
    >
      {{ $t('combo.courseForm.repeat') }}
    </ion-checkbox>
    <div class="combo-course-form__actions">
      <ion-button
        size="small"
        data-testid="combo-course-form-save"
        :disabled="pending"
        @click="save"
      >
        {{ $t('combo.save') }}
      </ion-button>
      <ion-button
        v-if="course"
        size="small"
        fill="outline"
        data-testid="combo-course-form-cancel"
        @click="cancel"
      >
        {{ $t('combo.cancel') }}
      </ion-button>
    </div>
    <p
      v-if="reason"
      class="combo-course-form__reason"
      data-testid="combo-course-form-reason"
    >
      {{ reason }}
    </p>
    <InlineFeedback
      v-if="loose"
      tone="danger"
      data-testid="combo-course-form-error"
    >
      {{ loose }}
    </InlineFeedback>
  </section>
</template>

<style scoped>
.combo-course-form {
  border: 1px dashed var(--ion-border-color, #e7e2d6);
  border-radius: 10px;
  padding: 0.75rem 1rem;
  display: grid;
  gap: 0.6rem;
}
.combo-course-form__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}
.combo-course-form__row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.combo-course-form__row > * {
  flex: 1 1 12rem;
  min-width: 0;
}
.combo-course-form__help {
  margin: 0;
  font-size: 0.82rem;
  opacity: 0.75;
}
/* The checkbox's label is long («The same option may be picked more than once»): Ionic keeps it on
   one line, which at 390 px runs past the card. */
.combo-course-form ion-checkbox::part(label) {
  white-space: normal;
}
.combo-course-form__actions {
  display: flex;
  gap: 0.4rem;
}
.combo-course-form__reason {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-danger, #c5000f);
}
</style>
