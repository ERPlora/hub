// What the assistant knows about the configuration of the hub (hub#373).
//
// **The configuration state is a single query, and the assistant is one of its readings**
// (`architecture/hub/setup-status.md`, ADR-0222/0224/0227). Until now it was not: the panel handed
// the chat a paragraph it had built from a list kept beside the query, so the assistant could
// describe a hub the checklist did not. Two lists that disagree are worse than one imperfect list.
//
// This module turns the SAME document the card paints into the briefing the model gets. It does not
// evaluate, does not sort and does not filter — the runtime already did, by country and by
// permission. What it decides is what may be SAID, and three rules are hard:
//
// * **An `unavailable` item is never a task.** It is our breakdown, not the user's job: «go install
//   an app» against a catalogue that offers nothing sends someone to a screen where they can do
//   nothing. Its route is not even named.
// * **⛔ is not a strong recommendation.** It is the statement that the runtime REJECTS the
//   operation (ADR-0203's fiscal gate). Softened, it promises a protection that does not exist;
//   painted on a 🟡, it promises a gate that will never fire.
// * **A wall the user cannot bring down is said, not assigned** (hub#435). The runtime keeps a ⛔ on
//   the list of a session that cannot clear it, because the refusal is going to land on THEM. The
//   assistant names it and names who can fix it; it never offers to do it and never sends them to
//   the screen that would refuse them.
// * **Nothing is invented and nothing is re-filtered.** The list is closed: an item that is not in
//   the document does not exist, and one the query returned is not for this layer to hide.
import {
  LEVEL_LEGAL,
  LEVEL_FUNCTIONAL,
  LEVEL_RECOMMENDED,
  STATE_DONE,
  STATE_PENDING,
  STATE_UNAVAILABLE,
  type SetupItem,
  type SetupStatus,
} from './setup-status';

/**
 * Resolves an i18n key, or `null` when this catalogue does not carry it.
 *
 * The assistant has to call an item **what the checklist calls it**: a core item's `key` is also its
 * i18n key (`setup-status.md` §6bis) and a module's title arrives in canonical English. Naming it
 * one way on screen and another in the chat sends the user looking for something that is not there.
 */
export type Translator = (key: string) => string | null;

export interface BriefingOptions {
  /** The user's language. The briefing is ours (English, the code's language); the answer is theirs. */
  locale: string;
  /** The `key` of the item the chat opens on, so it never opens blank. `null` = the whole checklist. */
  focusKey?: string | null;
  /** How the UI names an item. Absent ⇒ the payload's English title, which is its own fallback. */
  translate?: Translator;
}

/**
 * The items the assistant may hand over as something to do: **pending and this session's.**
 *
 * A `done` has nothing left; an `unavailable` has nothing the user can do at all; and one that is
 * not `actionable` (hub#435) is somebody else's to type — offering any of them would have the model
 * invent a way to finish something that will be refused, or refuse itself.
 */
export function assistantTasks(status: SetupStatus | null): SetupItem[] {
  return (status?.items ?? []).filter((i) => i.state === STATE_PENDING && i.actionable);
}

/**
 * The walls the user cannot bring down themselves: ⛔ and pending, but not theirs (hub#435).
 *
 * They are in the document precisely because the runtime is going to refuse THIS session, so they
 * are said out loud — with who can clear them — and never handed over as a task.
 */
function delegatedItems(status: SetupStatus | null): SetupItem[] {
  return (status?.items ?? []).filter((i) => i.state === STATE_PENDING && !i.actionable);
}

/**
 * The `system` turn that opens a configuration chat: the document, said out loud.
 *
 * Rebuilt on every turn from the current answer (not stored), so a hub that gets configured mid-chat
 * stops being described as unconfigured.
 */
export function setupBriefing(status: SetupStatus | null, opts: BriefingOptions): string {
  const head = `You are the setup assistant of an ERPlora hub. Reply in the user's language (locale: ${opts.locale}).`;

  // An absence is not an answer. Without a document there is nothing to describe, and the one thing
  // that must not be said is the reassuring one: silence is not a configured hub.
  const items = status?.items ?? [];
  if (!status || items.length === 0) {
    return `${head}\n\nThe configuration state could NOT be read right now, so do not tell the user the hub is set up and do not list what is missing. Ask what they want to configure, or point them at the setup checklist on the home panel.`;
  }

  const tr = opts.translate;
  const blocks = [head, RULES];

  const focus = items.find((i) => i.key === opts.focusKey);
  if (focus) blocks.push(focusBlock(focus, tr));

  blocks.push(todoBlock(status, tr));

  const delegated = delegatedItems(status);
  if (delegated.length) {
    const lines = delegated.map((i) => `- ${title(i, tr)}${levelNote(i)}`).join('\n');
    blocks.push(`${NOT_THEIRS_HEADING}\n${lines}`);
  }

  const broken = items.filter((i) => i.state === STATE_UNAVAILABLE);
  if (broken.length) {
    const lines = broken.map((i) => `- ${title(i, tr)}: ${ON_US_REASON}`).join('\n');
    blocks.push(`${ON_US_HEADING}\n${lines}`);
  }

  const done = items.filter((i) => i.state === STATE_DONE);
  if (done.length) {
    blocks.push(`ALREADY DONE — never bring these up as a task: ${done.map((i) => title(i, tr)).join(', ')}.`);
  }

  return blocks.join('\n\n');
}

/**
 * The ground rules. They exist because the model's helpfulness is exactly the failure mode here: it
 * would happily fill a gap in the list with a plausible task, or turn our breakdown into a chore.
 */
const RULES = [
  'The list below IS `hub.setup.status`, the hub\'s one source of truth for what is configured. It arrives ordered and already filtered by country and by permission, and it is complete: do not invent an item that is not here, do not filter it again, and do not bring up one that is already done.',
  'Ways in, per item: template = import a starter catalogue · catalog = install it from the marketplace · manual = the screen named on the item · assistant = you can do it yourself with your tools.',
  'When you send the user to a screen, write its path exactly as it appears here — the app turns it into a button.',
].join('\n');

const ON_US_HEADING = "ON US — not the user's task: never offer these, and never name a screen for them.";
const ON_US_REASON = 'we cannot offer this yet; it is our breakdown to fix, not their job.';

/**
 * The heading for the walls that are not theirs (hub#435).
 *
 * Deliberately NOT the "on us" one: nothing of ours is broken, so promising a fix from us would have
 * the user wait for something that is never coming. It names **who** can clear it — an administrator
 * of the hub — because a wall with no owner is the dead end the strip and the card also refuse to be.
 */
const NOT_THEIRS_HEADING =
  'BLOCKING, BUT NOT THE USER’S TO DO — an administrator of this hub has to set these up. Say what they block and who can clear them, do NOT offer to do them, and do NOT name a screen for them.';

/** The opening: which item the chat was opened on, said before the list so it never opens blank. */
function focusBlock(item: SetupItem, tr?: Translator): string {
  const name = `THE USER IS ASKING ABOUT «${title(item, tr)}»`;
  if (item.state === STATE_UNAVAILABLE) {
    return `${name} — and it is ON US (see below): say so plainly, and do not turn it into a task for them.`;
  }
  if (item.state === STATE_DONE) {
    return `${name} — and it is already done: confirm it and offer to review it, do not ask for it again.`;
  }
  if (!item.actionable) {
    return `${name} — and it is NOT THEIRS to do (see below): say what it blocks and who can clear it, do not offer to do it and do not name a screen for it.`;
  }
  return `${name} — open on it: what it is, why it matters and how to finish it. Do not open with the whole list.`;
}

/**
 * What is left for the USER.
 *
 * The ⛔ figure is the query's (`blocking_pending`) — that one is a fact about the runtime and
 * re-deriving it is the divergence hub#369 closed. The first number is the length of the list that
 * follows, which since hub#435 can be shorter than `pending`: the walls that are not theirs are
 * pending for the hub but are not lines here, and a header that counted them would have the model
 * announce a task it then cannot name.
 */
function todoBlock(status: SetupStatus, tr?: Translator): string {
  const tasks = assistantTasks(status);
  if (tasks.length === 0) {
    if (delegatedItems(status).length > 0) {
      return 'STILL TO DO: nothing the user can do themselves — what is left is below and belongs to an administrator.';
    }
    return status.unavailable > 0
      ? 'STILL TO DO: nothing the user can do right now.'
      : 'STILL TO DO: nothing — every item of the checklist is done.';
  }
  const blocking = status.blockingPending > 0 ? ` · blocking invoicing: ${status.blockingPending}` : '';
  const lines = tasks.map((item, i) => taskLines(item, i + 1, tr)).join('\n');
  return `STILL TO DO (${tasks.length} of ${status.total}${blocking}):\n${lines}`;
}

/** One task: what it is, what it costs to skip it, where it is done and how. */
function taskLines(item: SetupItem, n: number, tr?: Translator): string {
  const lines = [`${n}. ${title(item, tr)}${moduleTag(item)}${levelNote(item)}`];
  const desc = description(item, tr);
  if (desc) lines.push(`   ${desc}`);
  const ways = item.actions.length ? ` · Ways in: ${item.actions.join(', ')}` : '';
  lines.push(`   Screen: ${item.route}${ways}`);
  return lines.join('\n');
}

/**
 * What skipping it costs. **Read from `level`, never re-derived from `required`**: a boolean cannot
 * express ⛔, and two surfaces deriving it separately end up disagreeing (`setup-status.md` §4).
 */
function levelNote(item: SetupItem): string {
  if (item.level === LEVEL_LEGAL) {
    return ' — BLOCKS INVOICING: the hub rejects the operation until this is done. This is not advice, it is what the runtime does.';
  }
  if (item.level === LEVEL_FUNCTIONAL) return ' — needed to sell: the till cannot do its job without it.';
  if (item.level === LEVEL_RECOMMENDED) return ' — recommended: the business runs without it.';
  // A level this shell does not know is not guessed into a promise about the runtime.
  return '';
}

/** Which module owns it, so a tool call can name it. Empty for a core item. */
function moduleTag(item: SetupItem): string {
  return item.moduleId ? ` [module: ${item.moduleId}]` : '';
}

function title(item: SetupItem, tr?: Translator): string {
  return tr?.(`setup.items.${item.key}.title`) || item.title || item.key;
}

function description(item: SetupItem, tr?: Translator): string {
  return tr?.(`setup.items.${item.key}.description`) || item.description;
}
