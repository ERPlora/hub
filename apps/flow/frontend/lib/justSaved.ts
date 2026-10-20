// An automation saved for the first time is opened again on its own address (`/flow/automations/<id>`),
// a new page: the mark left here says it was just saved, so that page opens saying «Saved.» (FLOW-F09).
// Read once: neither the address nor a reload carry it.
const marked = new Set<string>();

export function markSaved(id: string): void {
  marked.add(id);
}

/** Whether `id` was just saved, forgetting it. */
export function takeSaved(id: string): boolean {
  return marked.delete(id);
}
