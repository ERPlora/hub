// erplora.com's photo of hub `a` for a spec that changes what it says (its people, its plan…): sent the way the SaaS
// sends it (`PUT /internal/hubs/{id}/state`, signed by `internalPut`), with `a`'s photo and version kept in a scratch
// table before the run and put back after.
import { expect } from '@playwright/test';

import { internalPut, psql } from './helpers';
import { STACK } from './stack';

export interface PhotoOfA {
  hubId: string;
  /** A newer photo of `a` with `fields` (its own id, slug and version always win), which the Hub has to apply. */
  send(fields: Record<string, unknown>): Promise<void>;
  /** `a`'s photo and version as the run found them, and the scratch table dropped. */
  putBack(): void;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** Keeps `a`'s photo in the scratch table `backup` and answers how to send newer ones. */
export function keepPhotoOfA(backup: string): PhotoOfA {
  const hubId = psql("select id from base_hub where slug = 'a'");
  if (!UUID.test(hubId)) {
    throw new Error(
      `The registry of DB_NAME=${STACK.database} has no hub a (got ${JSON.stringify(hubId)}): run node tests/e2e/database.ts.`,
    );
  }
  // Monotonic photo versions: an older one changes nothing.
  let version = Math.max(Math.floor(Date.now() / 1000), Number(psql(`select state_version from base_hub where id = '${hubId}'`)));
  psql(
    [
      `drop table if exists ${backup}`,
      `create table ${backup} as select id, state, state_version from base_hub where id = '${hubId}'`,
    ].join('; '),
  );
  return {
    hubId,
    async send(fields) {
      version += 1;
      const body = JSON.stringify({ ...fields, hub_id: hubId, slug: 'a', version });
      const response = await internalPut(`/internal/hubs/${hubId}/state`, body);
      const answer = await response.text();
      expect(response.status, answer).toBe(200);
      expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
    },
    putBack() {
      psql(
        [
          `update base_hub h set state = b.state, state_version = b.state_version from ${backup} b where b.id = h.id`,
          `drop table ${backup}`,
        ].join('; '),
      );
    },
  };
}
