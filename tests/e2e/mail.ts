// The sign-in code the local SaaS mails on every password login (`ACCOUNT_LOGIN_BY_CODE_REQUIRED`).
// In local the SaaS uses Django's file e-mail backend: one `<timestamp>-<id>.log` per connection in
// `saas-next/.mail/`, each message in RFC 822 (headers, a blank line, a quoted-printable body) followed
// by a line of 79 dashes. The code is the body's line of six digits, alone. No Playwright here: the
// browser steps live in helpers.ts.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

export interface ReadMailCodeOptions {
  /** The folder the SaaS writes its mails to. */
  dir: string;
  /** The address the code was mailed to (any case, with or without a display name in `To:`). */
  to: string;
  /** Epoch ms of the login: older files are never read. */
  since: number;
  /** How long to wait for the mail, in ms (default 15 s). */
  timeout?: number;
  /** Pause between two reads of the folder, in ms (default 250). */
  interval?: number;
}

/** The body's line with six digits and nothing else. */
const CODE = /^[ \t]*(\d{6})[ \t]*$/m;
/** Django's file backend ends every message with this line. */
const SEPARATOR = /^-{79}[ \t]*$/m;
/** The addresses of a header such as `To: Owner <owner@example.com>, other@example.com`. */
const ADDRESS = /[^\s<>,;"']+@[^\s<>,;"']+/g;

/** A quoted-printable body as text: soft line breaks joined, `=XX` bytes decoded as UTF-8. */
function decodeQuotedPrintable(body: string): string {
  const joined = body.replace(/=\r?\n/g, '');
  const bytes: number[] = [];
  for (let i = 0; i < joined.length; i += 1) {
    const hex = joined[i] === '=' ? joined.slice(i + 1, i + 3) : '';
    if (/^[0-9A-Fa-f]{2}$/.test(hex)) {
      bytes.push(parseInt(hex, 16));
      i += 2;
    } else {
      bytes.push(...Buffer.from(joined[i], 'utf8'));
    }
  }
  return Buffer.from(bytes).toString('utf8');
}

/** The code of one message when it was mailed to `to`. */
function codeOf(message: string, to: string): string | undefined {
  const normalized = message.replace(/\r\n/g, '\n').replace(/^\n+/, '');
  const split = normalized.indexOf('\n\n');
  if (split < 0) return undefined;
  // Headers folded over several lines are unfolded first (RFC 822 §3.1.1).
  const headers = normalized.slice(0, split).replace(/\n[ \t]+/g, ' ').split('\n');
  const header = (name: string): string | undefined =>
    headers.find((line) => line.toLowerCase().startsWith(`${name}:`))?.slice(name.length + 1).trim();
  const recipients = (header('to') ?? '').match(ADDRESS)?.map((address) => address.toLowerCase()) ?? [];
  if (!recipients.includes(to.toLowerCase())) return undefined;
  const raw = normalized.slice(split + 2);
  const body = header('content-transfer-encoding')?.toLowerCase() === 'quoted-printable' ? decodeQuotedPrintable(raw) : raw;
  return CODE.exec(body)?.[1];
}

/** Files of `dir` modified since `since`, newest first; none while the folder does not exist yet. */
function mailsSince(dir: string, since: number): string[] {
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch (error) {
    // The SaaS creates the folder with its first mail.
    if ((error as { code?: unknown }).code === 'ENOENT') return [];
    throw error;
  }
  const mails: { path: string; mtime: number }[] = [];
  for (const name of names) {
    const path = join(dir, name);
    // A file deleted between the listing and here is skipped.
    const stat = statSync(path, { throwIfNoEntry: false });
    if (stat?.isFile() && stat.mtimeMs >= since) mails.push({ path, mtime: stat.mtimeMs });
  }
  return mails.sort((a, b) => b.mtime - a.mtime || b.path.localeCompare(a.path)).map(({ path }) => path);
}

/** The code of the newest mail to `to` sent since `since`, if one is there already. */
function findCode(dir: string, to: string, since: number): string | undefined {
  for (const path of mailsSince(dir, since)) {
    const messages = readFileSync(path, 'utf8').split(SEPARATOR).reverse();
    for (const message of messages) {
      const code = codeOf(message, to);
      if (code) return code;
    }
  }
  return undefined;
}

const pause = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * The six-digit sign-in code of the newest mail to `to` written to `dir` since `since`, waiting up to
 * `timeout` ms for it. Fails naming the address, the folder and the wait when none arrives.
 */
export async function readMailCode({ dir, to, since, timeout = 15_000, interval = 250 }: ReadMailCodeOptions): Promise<string> {
  const deadline = Date.now() + timeout;
  for (;;) {
    const code = findCode(dir, to, since);
    if (code) return code;
    const left = deadline - Date.now();
    if (left <= 0) {
      throw new Error(
        `no sign-in code mailed to ${to} in ${dir} since ${new Date(since).toISOString()} within ${timeout} ms`,
      );
    }
    await pause(Math.min(interval, left));
  }
}
