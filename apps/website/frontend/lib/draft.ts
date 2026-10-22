// The editor's draft: what `website.site.save` takes (template, theme, content), cut from what `website.site.get`
// answers. The form edits a deep copy, with the address padded to its four lines (one field each); what is sent
// drops the empty ones. The server's 422 (`fields`, keyed by the path of the field) is read back onto the fields.
import type { SaveIn, SiteOut } from '../operations';

/** The address takes four lines at most (the server's bound too). */
export const ADDRESS_LINES = 4;

/** A deep copy of JSON data, also of Vue's reactive or readonly proxies (which `structuredClone` refuses). */
export function copyOf<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function toDraft(site: SiteOut): SaveIn {
  const copy = copyOf({ template: site.template, theme: site.theme, content: site.content });
  const lines = copy.content.location.address_lines;
  copy.content.location.address_lines = [...lines, ...Array<string>(Math.max(0, ADDRESS_LINES - lines.length)).fill('')];
  return copy;
}

/** What goes to the server: the draft without its empty address lines. */
export function toSaveIn(draft: SaveIn): SaveIn {
  const copy = copyOf(draft);
  copy.content.location.address_lines = copy.content.location.address_lines.filter((line) => line.trim() !== '');
  return copy;
}

/** Whether two drafts say the same, as the server keeps them: every text without the spaces around it. */
export function sameDraft(a: SaveIn, b: SaveIn): boolean {
  const kept = (draft: SaveIn) => JSON.stringify(toSaveIn(draft), (_key, value: unknown) => (typeof value === 'string' ? value.trim() : value));
  return kept(a) === kept(b);
}

/** The server's message for `path`, or for the first field under it. */
export function errorUnder(fields: Readonly<Record<string, string>> | undefined, path: string): string | undefined {
  if (!fields) return undefined;
  if (fields[path]) return fields[path];
  const nested = Object.keys(fields).find((key) => key.startsWith(`${path}.`));
  return nested ? fields[nested] : undefined;
}
