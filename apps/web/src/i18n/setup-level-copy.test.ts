// @vitest-environment node
// hub#1726 — the three badges of the setup checklist, measured against what the runtime REFUSES.
//
// A badge on this list is not decoration: it is a claim about the dispatcher, and the owner reads it
// as a promise. The checklist told a new business that «your invoice numbering» and «configure
// VeriFactu» were *Needed to sell* — and the till then took 12,50 € in cash and printed a receipt
// with its VeriFactu QR, without either of them configured. Nothing was broken at the till: the
// badge was simply describing a gate that does not exist, so the owner believed they could not
// trade while the system traded.
//
// The core already draws the line, and it draws it the other way round from the copy
// (`crates/runtime/src/setup_status.rs`):
//
//   - ⛔ `legal` is the ONE level derived from a real refusal — `enforce_fiscal_precondition`, the
//     gate of ADR-0203. And that gate rejects **invoicing**, not selling: ADR-0203 says in its own
//     consequences that a sale without identity still closes, and what dies is the
//     `invoice.create_from_sale` listener. So ⛔ may name a block, and the block it names is the
//     invoice.
//   - 🔴 `functional` is a module saying, in its own manifest, that its configuration matters. The
//     core's rule for it is explicit: a manifest «can never make itself a condition for selling».
//     There is no gate behind it — `level_of` only reaches ⛔ through `BLOCKING_KEYS` (the business
//     identity) or the certificate arm.
//   - 🟡 `recommended` claims nothing at all.
//
// So the invariant these tests hold is one sentence: **only ⛔ may name a refusal, and the refusal
// it names is invoicing.** Everything else describes how much the setup matters, never what the
// user is or is not allowed to do. A badge that promises a block that never fires is the same class
// of lie as a ⛔ painted on a 🟡 (guarded in `lib/assistant-setup.test.ts`) — only in the direction
// nobody was watching.
//
// The guard covers BOTH surfaces that turn `level` into words, because the copy was wrong in the
// two of them at once and a fix to one alone leaves the owner told the same thing by the other: the
// checklist card badge (`setup.level*`, hub#372) and the assistant briefing (hub#373).
import { describe, expect, it } from 'vitest';

import { setupBriefing } from '../lib/assistant-setup';
import { parseSetupStatus, type SetupStatus } from '../lib/setup-status';
import en from './locales/en';
import es from './locales/es';

type Catalogue = { setup: Record<string, string> };

const EN = (en as unknown as Catalogue).setup;
const ES = (es as unknown as Catalogue).setup;

/**
 * Words that assert the user CANNOT do something, or MUST do it before something else works. Only
 * the ⛔ badge has a dispatcher behind it, so only the ⛔ badge is allowed to use them.
 *
 * The list is the guard: it has to catch wordings nobody has written yet, in BOTH languages at
 * once, or a rename to «Mandatory» only dies through the pinned string above and survives the
 * moment somebody updates that pin. Keep the two halves symmetric.
 */
const CLAIMS_A_BLOCK: readonly RegExp[] = [
  // en
  /\bneeded to\b/i,
  /\brequired to\b/i,
  /\bcan ?not\b/i,
  /\bcan't\b/i,
  /\bmust\b/i,
  /\buntil\b/i,
  /\bmandatory\b/i,
  /\bessential\b/i,
  // es
  /\bnecesario para\b/i,
  /\bimprescindible\b/i,
  /\bobligatorio\b/i,
  /\bno puedes\b/i,
  /\bdebes\b/i,
  /\bhasta que\b/i,
];

/** Words for the operation the gate does NOT touch. ⛔ rejects the invoice; the sale still closes. */
const NAMES_SELLING: readonly RegExp[] = [
  /\bsell\b/i,
  /\bselling\b/i,
  /\bsales?\b/i,
  /\bvender\b/i,
  /\bventas?\b/i,
];

function item(key: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    key,
    source: 'module',
    module_id: key.split('.')[0],
    state: 'pending',
    required: true,
    level: 'functional',
    title: `Your ${key}`,
    description: `Set up ${key}.`,
    icon: 'settings-outline',
    route: `/${key}`,
    order: 10,
    actions: ['manual'],
    ...over,
  };
}

function status(items: Record<string, unknown>[]): SetupStatus | null {
  return parseSetupStatus([
    {
      items,
      total: items.length,
      pending: items.filter((i) => i.state === 'pending').length,
      unavailable: 0,
      blocking_pending: items.filter((i) => i.state === 'pending' && i.level === 'legal').length,
    },
  ]);
}

describe('the checklist badge only promises what the runtime enforces', () => {
  it('⛔ names the refusal that exists, and names it as INVOICING', () => {
    expect(EN.levelLegal).toBe('Needed to invoice');
    expect(ES.levelLegal).toBe('Necesario para facturar');
  });

  it('🔴 says how much it matters, never that the till is shut', () => {
    expect(EN.levelFunctional).toBe('Important');
    expect(ES.levelFunctional).toBe('Importante');
  });

  it('🟡 stays the softest of the three', () => {
    expect(EN.levelRecommended).toBe('Recommended');
    expect(ES.levelRecommended).toBe('Recomendado');
  });

  it('no badge below ⛔ asserts the user cannot do something', () => {
    const softer = [
      ['en.levelFunctional', EN.levelFunctional],
      ['es.levelFunctional', ES.levelFunctional],
      ['en.levelRecommended', EN.levelRecommended],
      ['es.levelRecommended', ES.levelRecommended],
    ] as const;

    for (const [name, copy] of softer) {
      for (const claim of CLAIMS_A_BLOCK) {
        expect(copy, `setup.${name}: «${copy}» promises a gate that does not exist`).not.toMatch(claim);
      }
    }
  });

  it('⛔ itself never says «sell»: the sale closes, the invoice is what dies', () => {
    for (const [name, copy] of [['en', EN.levelLegal], ['es', ES.levelLegal]] as const) {
      for (const word of NAMES_SELLING) {
        expect(copy, `setup.${name}.levelLegal: «${copy}» blocks the wrong operation`).not.toMatch(word);
      }
    }
  });

  // The blocking strip (hub#374) is the third surface, and the loudest: it cuts the screen of the
  // person at the till. It is allowed to claim a block — it only ever appears on a wall, which is
  // ⛔ and pending — but it has to claim the RIGHT one, for the same reason the badge does.
  it('the strip, the one surface that may shout, still shouts about the invoice', () => {
    const strips = [
      ['en.title', (EN as unknown as { blocking: Record<string, string> }).blocking.title],
      ['en.body', (EN as unknown as { blocking: Record<string, string> }).blocking.body],
      ['es.title', (ES as unknown as { blocking: Record<string, string> }).blocking.title],
      ['es.body', (ES as unknown as { blocking: Record<string, string> }).blocking.body],
    ] as const;

    for (const [name, copy] of strips) {
      for (const word of NAMES_SELLING) {
        expect(copy, `setup.blocking.${name}: «${copy}» blocks the wrong operation`).not.toMatch(word);
      }
      expect(copy, `setup.blocking.${name} stopped naming what is actually refused`).toMatch(
        /invoice|factur/i,
      );
    }
  });
});

describe('the assistant tells the owner the same truth as the badge', () => {
  const brief = (doc: SetupStatus | null) => setupBriefing(doc, { locale: 'es' });

  it('a 🔴 is never handed over as «you cannot sell»', () => {
    const text = brief(status([item('verifactu.setup', { level: 'functional' })]));

    for (const word of NAMES_SELLING) {
      expect(text, `the briefing tells the owner a 🔴 stops the sale: ${word.source}`).not.toMatch(word);
    }
    expect(text).not.toMatch(/\bcannot\b/i);

    // …and the sentence that translates the level — the task line the note hangs from — makes no
    // claim of a block in ANY wording: the historical one promised a shut till without ever saying
    // «sell» («the till cannot do its job without it»). Scoped to that line on purpose: the ⛔ note
    // and the «on us» reason are allowed their «until» / «cannot», and neither is under test here.
    const taskLine = text.split('\n').find((line) => /^1\. /.test(line));
    expect(taskLine, 'the briefing lost the task line the level note hangs from').toBeDefined();
    for (const claim of CLAIMS_A_BLOCK) {
      expect(taskLine, `the 🔴 note promises a gate that does not exist: ${claim.source}`).not.toMatch(claim);
    }
  });

  it('⛔ keeps its teeth: the one level with a gate still says so', () => {
    const text = brief(status([item('business_identity', { level: 'legal', source: 'core', module_id: null })]));

    expect(text).toContain('BLOCKS INVOICING');
  });
});
