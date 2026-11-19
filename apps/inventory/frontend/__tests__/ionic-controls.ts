import { flush } from './mount-inventory';

export async function typeText(el: (id: string) => (HTMLElement & { value?: unknown }) | null, id: string, value: string): Promise<void> {
  const field = el(id)!;
  field.value = value;
  field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
  await flush();
}
