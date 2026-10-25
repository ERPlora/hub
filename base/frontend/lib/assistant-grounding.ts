// What the assistant says, checked against what really ran (BASE-G117; gh:hub#1039): the panel never trusts what an
// answer says of itself. Three notices, painted outside the bubble and never written by the model:
// - `claimed_change`: the answer says it changed something («he creado…», «has been updated») and no write of the
//   turn ran (none, or cancelled, failed or refused);
// - `unread_id`: it writes an identifier (a UUID) that no tool of the turn returned and the person did not write;
// - `unknown_screen`: it links a screen this hub does not serve (BASE-G114: no «Go to» for it either).
import { linkPaths, parseMarkdown } from './assistant-markdown';

export interface Executed {
  name: string;
  kind: 'query' | 'command' | '';
  outcome: 'ok' | 'error' | 'refused' | 'cancelled';
  app?: string;
  /** Where it happened, as the server names it in the person's language (the platform by its screen). */
  app_name?: string;
}

export type GroundingNotice = 'claimed_change' | 'unread_id' | 'unknown_screen';

const CLAIMS = [
  // Spanish: «he creado», «he añadido», «se ha guardado», «queda guardado», «listo, …»
  /\b(he|hemos)\s+(cread[oa]|añadid[oa]|anadid[oa]|actualizad[oa]|cambiad[oa]|modificad[oa]|borrad[oa]|eliminad[oa]|guardad[oa]|anulad[oa]|registrad[oa]|dad[oa] de alta|cobrad[oa]|cerrad[oa]|abiert[oa])\b/i,
  /\bse\s+ha(n)?\s+(cread[oa]s?|añadid[oa]s?|actualizad[oa]s?|cambiad[oa]s?|modificad[oa]s?|borrad[oa]s?|eliminad[oa]s?|guardad[oa]s?|anulad[oa]s?|registrad[oa]s?)\b/i,
  /\bqueda(n)?\s+(guardad[oa]s?|cread[oa]s?|actualizad[oa]s?|registrad[oa]s?)\b/i,
  // English: «has been created», «I've updated», «I have deleted», «is now saved»
  /\b(has|have)\s+been\s+(created|added|updated|changed|modified|deleted|removed|saved|voided|registered|closed|opened)\b/i,
  /\bI(?:'ve|\s+have)\s+(created|added|updated|changed|modified|deleted|removed|saved|voided|registered|closed|opened)\b/i,
];
const UUID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;

export function groundingNotices(input: {
  answer: string;
  executed: Executed[];
  /** What each tool of the turn returned (its JSON). */
  results: string[];
  /** The person's last question. */
  question: string;
  screenExists: (path: string) => boolean;
}): GroundingNotice[] {
  const found: GroundingNotice[] = [];
  const wrote = input.executed.some((row) => row.kind === 'command' && row.outcome === 'ok');
  if (!wrote && CLAIMS.some((claim) => claim.test(input.answer))) found.push('claimed_change');
  const read = `${input.results.join('\n')}\n${input.question}`.toLowerCase();
  const ids = input.answer.match(UUID) ?? [];
  if (ids.some((id) => !read.includes(id.toLowerCase()))) found.push('unread_id');
  if (linkPaths(parseMarkdown(input.answer)).some((path) => !input.screenExists(path))) found.push('unknown_screen');
  return found;
}
