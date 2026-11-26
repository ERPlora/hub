// What to do about why a run stopped, by its code: the History says it under the reason, and the editor after
// «Run now»; the server's sentence says only what happened, so the advice is said once.
import type { Phrasing } from './phrasing';

export function advice(code: string, p: Phrasing): string {
  if (!code) return '';
  const key = `flow.history.advice.${code.replaceAll('.', '__')}`;
  return p.te(key) ? p.t(key) : '';
}

export function withAdvice(said: string, code: string, p: Phrasing): string {
  const more = advice(code, p);
  return more ? `${said} ${more}` : said;
}
