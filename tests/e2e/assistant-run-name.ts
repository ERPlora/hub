// The business's name during one scenario run (qa/assistant-scenarios.spec.ts): its own name with the run's id after
// it. The assistant's instructions begin with the business's name, so two runs never share that start and a provider's
// prompt cache cannot make a repeated run cheaper or faster than a business's first conversation; within one
// conversation the cache works as in production. Pure, so Vitest proves it (assistant-run-name.test.ts).

/** A run's id at the end of the name, as `runBusinessName` writes it (`psql()` reads it back without outer spaces). */
const RUN_ID = /\s*·\s*[A-Za-z0-9._-]+$/;

/** The business's own name, without the id a run left if it stopped before putting it back. */
export const ownName = (name: string): string => name.replace(RUN_ID, '');

/** `name` with the run's id after it (the id alone when the business has no name). */
export const runBusinessName = (name: string, run: string): string => `${ownName(name)} · ${run}`.trim();

/** The statement that names `a` in the registry, run through `psql()` of helpers.ts (which passes it in double quotes
 *  through the shell). */
export function renameSql(name: string): string {
  if (/["$`]/.test(name)) throw new Error(`the business name «${name}» has double quotes, dollars or backticks, which the shell would change`);
  return `update base_hub set name = '${name.replace(/'/g, "''")}' where slug = 'a'`;
}
