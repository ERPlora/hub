// `readMailCode`: the sign-in code the local SaaS mails on every password login, read from the files
// Django's file e-mail backend writes (`saas/.mail/<timestamp>-<id>.log`, RFC 822, quoted-printable);
// `mailDirFrom`: that folder.
import { mkdtempSync, rmSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { mailDirFrom, readMailCode } from './mail';

const SEPARATOR = '-'.repeat(79);

/** A message as Django's file backend writes it, ending with its separator line. */
function message(to: string, code: string, subject = 'Sign-In Code'): string {
  return [
    'Content-Type: text/plain; charset="utf-8"',
    'Content-Transfer-Encoding: quoted-printable',
    'MIME-Version: 1.0',
    `Subject: ${subject}`,
    'From: noreply@erplora.com',
    `To: ${to}`,
    'Date: Thu, 15 Oct 2026 08:26:35 +0000',
    'Message-ID: <179205279521.36034.18318650551267467381@localhost>',
    '',
    'Hello from ERPlora!',
    '',
    'Your sign-in code is listed below. Please enter it in your open browser windo=',
    'w.',
    '',
    code,
    '',
    'This mail can be safely ignored if you did not initiate this action.',
    '',
    'Thank you for using ERPlora 2026.',
    'https://erplora.com',
    '',
    SEPARATOR,
    '',
  ].join('\n');
}

/** `text` as a literal inside a regular expression. */
const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

let dir: string;
const since = Date.parse('2026-10-15T10:00:00Z');

/** Writes `content` to `dir/name` with its modification time `at` (epoch ms). */
function mail(name: string, content: string, at: number): void {
  const path = join(dir, name);
  writeFileSync(path, content);
  utimesSync(path, new Date(at), new Date(at));
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'erplora-mail-'));
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

describe('readMailCode', () => {
  it('takes the code of the newest mail to that address sent since the login', async () => {
    // The newer file sorts first by name: the order is the modification time, not the name.
    mail('20261015-100002-2.log', message('owner@example.com', '111111'), since + 2_000);
    mail('20261015-100001-9.log', message('owner@example.com', '222222'), since + 1_000);

    await expect(readMailCode({ dir, to: 'owner@example.com', since, timeout: 0 })).resolves.toBe('111111');
  });

  it('ignores mails to other addresses and mails older than the login', async () => {
    mail('a-old.log', message('owner@example.com', '333333'), since - 60_000);
    mail('b-owner.log', message('owner@example.com', '444444'), since + 1_000);
    mail('c-employee.log', message('employee@example.com', '555555'), since + 5_000);

    await expect(readMailCode({ dir, to: 'owner@example.com', since, timeout: 0 })).resolves.toBe('444444');
    await expect(readMailCode({ dir, to: 'employee@example.com', since, timeout: 0 })).resolves.toBe('555555');
  });

  it('matches the address whatever its case or display name', async () => {
    mail('owner.log', message('Owner <OWNER@Example.com>', '666666'), since + 1_000);

    await expect(readMailCode({ dir, to: 'owner@example.com', since, timeout: 0 })).resolves.toBe('666666');
  });

  it('reads only the line of six digits, and the last message for that address in a file', async () => {
    const both = message('owner@example.com', '777777') + message('owner@example.com', '888888');
    mail('connection.log', both, since + 1_000);

    await expect(readMailCode({ dir, to: 'owner@example.com', since, timeout: 0 })).resolves.toBe('888888');
  });

  it('waits until the mail arrives', async () => {
    const now = Date.now();
    setTimeout(() => mail('late.log', message('owner@example.com', '999999'), Date.now()), 100);

    await expect(readMailCode({ dir, to: 'owner@example.com', since: now, timeout: 3_000, interval: 20 })).resolves.toBe(
      '999999',
    );
  });

  it('fails with the address, the folder and the wait when no mail arrives', async () => {
    mail('old.log', message('owner@example.com', '123456'), since - 1_000);

    await expect(readMailCode({ dir, to: 'owner@example.com', since, timeout: 100, interval: 20 })).rejects.toThrow(
      new RegExp(`no sign-in code mailed to owner@example\\.com in ${escape(dir)}.* within 100 ms`),
    );
  });

  it('fails at once, naming the folder and E2E_MAIL_DIR, when the folder does not exist', async () => {
    // The SaaS writes the mail before it answers the sign-in form: a folder still missing then is one
    // it never writes to, and waiting the whole timeout for it only hides that.
    const missing = join(dir, 'elsewhere');
    const started = Date.now();

    await expect(
      readMailCode({ dir: missing, to: 'owner@example.com', since, timeout: 2_000, interval: 20 }),
    ).rejects.toThrow(new RegExp(`mail folder ${escape(missing)} does not exist.*E2E_MAIL_DIR`));
    expect(Date.now() - started).toBeLessThan(1_000);
  });
});

describe('mailDirFrom', () => {
  it("defaults to the shared SaaS's folder beside the Hub, saas/.mail", () => {
    expect(mailDirFrom({}, '/repo')).toBe(join('/repo', 'saas', '.mail'));
  });

  it('takes E2E_MAIL_DIR when it is set, and the default when it is empty', () => {
    expect(mailDirFrom({ E2E_MAIL_DIR: '/elsewhere/.mail' }, '/repo')).toBe('/elsewhere/.mail');
    expect(mailDirFrom({ E2E_MAIL_DIR: '' }, '/repo')).toBe(join('/repo', 'saas', '.mail'));
  });
});
