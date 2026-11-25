// A switch of Settings saved as soon as it is moved. Ionic keeps the position the person moved it to even when the save
// fails, so `repaint` changes then: the switch keyed on it is painted again on the saved value.
import { type MaybeRefOrGetter, type Ref, ref, toValue } from 'vue';

export interface SavedSwitch {
  change: (checked: boolean) => Promise<void>;
  /** The last change could not be saved. */
  failed: Ref<boolean>;
  repaint: Ref<number>;
}

export function useSavedSwitch(saved: MaybeRefOrGetter<boolean>, save: (checked: boolean) => Promise<unknown>): SavedSwitch {
  const failed = ref(false);
  const repaint = ref(0);

  async function change(checked: boolean): Promise<void> {
    if (checked === toValue(saved)) return;
    failed.value = false;
    try {
      await save(checked);
    } catch {
      failed.value = true;
      repaint.value += 1;
    }
  }

  return { change, failed, repaint };
}
