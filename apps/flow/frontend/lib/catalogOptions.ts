import type { ComboOption } from '@erplora/ui/components';

/** An event or an action of the catalog, as its picker lists it. */
interface CatalogEntry {
  name: string;
  app_name: string;
}

/** A picker's options: each entry in words with its app under it, by app and then by name. */
export function catalogOptions(entries: readonly CatalogEntry[], label: (name: string) => string, locale: string): ComboOption[] {
  return entries
    .map((entry) => ({ id: entry.name, label: label(entry.name), hint: entry.app_name }))
    .sort((a, b) => a.hint.localeCompare(b.hint, locale) || a.label.localeCompare(b.label, locale));
}
