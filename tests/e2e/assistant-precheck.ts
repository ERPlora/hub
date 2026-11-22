// Whether a scenario (assistant-scenario.ts) can be asked at all, by rules that are the same for every model, so a
// model's missing sense is reported apart from the model's failures: a photo only reaches a model that sees images. The
// tools its opening is offered never stop it: every turn offers the search of the rest (base.assistant.find_tools), so
// finding the one it lacks is the model's job. Also the guard every scenario ends with: no fiscal record ever left the
// business. Pure, so Vitest proves it (assistant-precheck.test.ts).
import type { Scenario } from './assistant-scenario.ts';

/** Why the scenario is not asked (null: it is): a photo the model cannot see. */
export function notRunnable(scenario: Scenario, vision: boolean): string | null {
  if (scenario.attachments.some((file) => file.kind === 'photo') && !vision) return 'not runnable: the model does not see images';
  return null;
}

/** The fiscal records that ever left the business for the tax agency, or that it answered: always 0 in a scenario run. */
export const SENT_SQL = "select count(*) from verifactu_record where transmitted_at is not null or coalesce(csv, '') <> ''";
