// VeriFactu's state of hub `a` for the specs of its step on the Home (hub#682): the account's photo with the signed
// authorisation, sent the way the SaaS sends it (`PUT /internal/hubs/{id}/state`, signed), and the configuration's
// columns a run moves, kept in scratch tables before it and put back after it (or the configuration removed, if the run
// made it). A spec keeps them in its `beforeAll` (`keepVerifactu`) and puts them back in its `afterAll`
// (`putVerifactuBack`); one spec at a time, as the e2e runs (`workers: 1`, playwright.config.ts).
import { expect } from '@playwright/test';

import { internalPut, psql } from './helpers';

/** The configuration's columns a run moves: the photo's, the route and the environment. */
const CONFIG_COLUMNS = [
  'route',
  'environment',
  'production_since',
  'representation_status',
  'representation_updated_at',
  'representation_reason',
  'synced_version',
  'synced_at',
  'hub_status',
  'hub_id',
];

/** What the running spec kept of `a`'s VeriFactu. */
interface Kept {
  /** `a`'s id in the registry. */
  hubId: string;
  /** The scratch tables of the configuration and of the photo. */
  backup: { config: string; photo: string };
  /** Whether `a` had a configuration before the run (if not, the one the run made is removed). */
  hadConfig: boolean;
  /** The last photo version sent: monotonic, as an older one changes nothing. */
  version: number;
}

let kept: Kept | null = null;

function running(): Kept {
  if (!kept) throw new Error('keepVerifactu() first, in the spec’s beforeAll.');
  return kept;
}

/** Keeps `a`'s VeriFactu configuration and photo in the scratch tables `<prefix>_config_before` and
 *  `<prefix>_photo_before`, for `putVerifactuBack`. */
export function keepVerifactu(prefix: string): void {
  const hubId = psql("select id from base_hub where slug = 'a'");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(hubId)) {
    throw new Error(`The registry has no hub a (got ${JSON.stringify(hubId)}): run node tests/e2e/database.ts.`);
  }
  const backup = { config: `${prefix}_config_before`, photo: `${prefix}_photo_before` };
  const hadConfig = psql('select count(*) from verifactu_config') !== '0';
  const version = Math.max(
    Math.floor(Date.now() / 1000),
    Number(psql('select coalesce(max(synced_version), 0) from verifactu_config')),
    Number(psql(`select state_version from base_hub where id = '${hubId}'`)),
  );
  psql(
    [
      `drop table if exists ${backup.config}`,
      `drop table if exists ${backup.photo}`,
      `create table ${backup.config} as select * from verifactu_config`,
      `create table ${backup.photo} as select id, state, state_version from base_hub where id = '${hubId}'`,
    ].join('; '),
  );
  kept = { hubId, backup, hadConfig, version };
}

/** Puts back what `keepVerifactu` kept, and drops its scratch tables; nothing if it kept nothing. */
export function putVerifactuBack(): void {
  if (!kept) return;
  const { backup, hadConfig } = kept;
  kept = null;
  const sets = CONFIG_COLUMNS.map((column) => `${column} = b.${column}`).join(', ');
  psql(
    [
      hadConfig
        ? `update verifactu_config c set ${sets} from ${backup.config} b where b.id = c.id`
        : 'delete from verifactu_config where not exists (select 1 from verifactu_record)',
      `update base_hub h set state = b.state, state_version = b.state_version from ${backup.photo} b where b.id = h.id`,
      `drop table ${backup.config}`,
      `drop table ${backup.photo}`,
    ].join('; '),
  );
}

/** The SaaS's photo of hub `a`, with the signed authorisation in `status`. */
export async function pushPhoto(status: string): Promise<void> {
  const run = running();
  run.version += 1;
  const verifactu = { representation: { status, updated_at: new Date().toISOString(), reason: '' } };
  const body = JSON.stringify({ hub_id: run.hubId, slug: 'a', version: run.version, status: 'active', verifactu });
  const response = await internalPut(`/internal/hubs/${run.hubId}/state`, body);
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version: run.version });
}

/** ERPlora files for `a`, its authorisation revoked, in `environment`: in production, a wall where it applies. */
export async function revokedIn(environment: 'production' | 'testing'): Promise<void> {
  await pushPhoto('approved');
  await pushPhoto('revoked');
  const since = environment === 'production' ? 'now()' : 'null';
  psql(`update verifactu_config set route = 'erplora', environment = '${environment}', production_since = ${since}`);
}
