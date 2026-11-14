import { useTemplateRef } from 'vue';

/** FormModal takes a refusal away when it hears the field of that name change. A group of controls refused as one
 *  (a rule's tiers, a schedule's week, the customer chosen in her own search) has no such field: the window calls
 *  what this returns on each change the person makes to the group, and the group's element (`ref="<ref>"`, a
 *  `<fieldset name="<key>">`) says it with a native `input`, as a typed field does. */
export function useGroupChange(ref: string): () => void {
  const group = useTemplateRef<HTMLElement>(ref);
  return () => {
    group.value?.dispatchEvent(new Event('input', { bubbles: true }));
  };
}
