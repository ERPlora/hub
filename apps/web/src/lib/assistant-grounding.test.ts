// The lock behind hub#1038 / #1039 / #1041 / #1044 / #1047: a turn that executed NO tool
// cannot claim it changed something, and NO identifier may reach the user unless a tool
// result in THIS turn actually carried it.
//
// Why a pure function and not a prompt line: ADR-0282 already says it in words ("describe
// what will change rather than claiming it is already done", "never invent a field you did
// not read") and the QA pass of 2026-08-19 caught the model breaking both while the prompt
// was live. A rule the model evaluates is advice; this is the runtime checking the receipt.
//
// The audit takes the turn's TEXT and the tools that actually ran, and nothing else — so it
// is testable with no transport, no LLM and no fixtures.

import { describe, expect, it } from 'vitest';

import { auditTurn, type ExecutedTool } from './assistant-grounding';

const ok = (name: string, result: unknown): ExecutedTool => ({
  name,
  kind: 'command',
  status: 'ok',
  result,
});
const readOk = (name: string, result: unknown): ExecutedTool => ({
  name,
  kind: 'query',
  status: 'ok',
  result,
});

describe('auditTurn — a claim needs a receipt', () => {
  // hub#1038, verbatim from the QA session: the user said "Sí", NOTHING ran, and the drawer
  // printed "✅ Categoría creada con éxito" with an invented id.
  it('flags a success claim when no write executed at all', () => {
    const audit = auditTurn({
      text: '✅ Categoría creada con éxito.\n- ID asignado: `cat_9b4e7c1a`\n- Nombre: "Barbería QA"',
      executed: [],
    });

    expect(audit.claimedWithoutEffect).toBe(true);
  });

  it('stays silent when the write really ran', () => {
    const audit = auditTurn({
      text: '✅ Categoría creada con éxito.',
      executed: [ok('services.categories.create', { id: 'ok' })],
    });

    expect(audit.claimedWithoutEffect).toBe(false);
  });

  // hub#1038: the user cancelled the card. "Not confirmed" is not "done".
  it('treats a cancelled write as no effect', () => {
    const audit = auditTurn({
      text: 'Listo, ya he creado el servicio.',
      executed: [{ name: 'services.services.create', kind: 'command', status: 'cancelled', result: null }],
    });

    expect(audit.claimedWithoutEffect).toBe(true);
  });

  // hub#1039: the dispatcher answered 422 and the assistant said it was done anyway.
  it('treats a failed write as no effect', () => {
    const audit = auditTurn({
      text: 'He actualizado el precio del servicio.',
      executed: [{ name: 'services.services.update', kind: 'command', status: 'error', result: null }],
    });

    expect(audit.claimedWithoutEffect).toBe(true);
  });

  // A read is not a write: "you have 40 services" after a real list must pass untouched.
  it('does not flag a plain read answer', () => {
    const audit = auditTurn({
      text: 'Tienes 40 servicios en el catálogo.',
      executed: [readOk('services.services.list', { rows: [] })],
    });

    expect(audit.claimedWithoutEffect).toBe(false);
  });

  // The assistant answers in English too (hub#1045 caught an English turn), so the lock
  // cannot be Spanish-only.
  it('catches the claim in English as well', () => {
    const audit = auditTurn({ text: 'Done — the service has been created.', executed: [] });

    expect(audit.claimedWithoutEffect).toBe(true);
  });

  // The whole point of the lock is that it must not cry wolf on ordinary answers, or the
  // banner becomes noise and stops being read.
  it('leaves an ordinary answer alone', () => {
    const audit = auditTurn({
      text: 'Para cambiar un precio entra en Servicios y abre la ficha del servicio.',
      executed: [],
    });

    expect(audit.claimedWithoutEffect).toBe(false);
  });
});

describe('auditTurn — an identifier must come from a tool result', () => {
  // hub#1038/#1039: `cat_9b4e7c1a`, `svc_7f2a1e8b`, `app_5d8a2f1b` — none of them can exist.
  // ERPlora ids are UUIDs as TEXT (ADR-0007).
  it('flags an id the turn never read', () => {
    const audit = auditTurn({
      text: 'Encontrado: `id`: `svc_7f2a1e8b`, precio 1500.',
      executed: [readOk('services.services.list', { rows: [{ id: '4e1c9b0a-2f8d-4a71-9c33-5b7e2a1d6f04' }] })],
    });

    expect(audit.unsourcedIds).toEqual(['svc_7f2a1e8b']);
  });

  it('accepts an id that the tool result really carried', () => {
    const realId = '4e1c9b0a-2f8d-4a71-9c33-5b7e2a1d6f04';
    const audit = auditTurn({
      text: `El servicio ${realId} está activo.`,
      executed: [readOk('services.services.get', { id: realId, name: 'Corte' })],
    });

    expect(audit.unsourcedIds).toEqual([]);
  });

  // Echoing back an id the user typed is not an invention.
  it('accepts an id the user supplied', () => {
    const audit = auditTurn({
      text: 'Miro el servicio svc_7f2a1e8b.',
      executed: [],
      userText: 'Dame el servicio svc_7f2a1e8b',
    });

    expect(audit.unsourcedIds).toEqual([]);
  });

  // Field names, slugs and tax keys travel in every answer; none of them is an id.
  it('does not mistake ordinary vocabulary for an id', () => {
    const audit = auditTurn({
      text: 'El campo `price_cents` va en céntimos, la categoría es `iva_21` y la plantilla `peluqueria` toca `tax_category_key`. Ruta: /m/services/services.',
      executed: [],
    });

    expect(audit.unsourcedIds).toEqual([]);
  });
});

describe('auditTurn — a screen must exist before it is named', () => {
  // hub#1048: `/settings/developers` does not exist. The router's catch-all redirects to
  // /dashboard, so an invented route fails SILENTLY — the user is left believing their hub
  // is broken. hub#1047 is the same failure with a whole invoicing walkthrough.
  const known = ['/dashboard', '/settings', '/apps', '/system', '/m/services/services', '/m/invoice/invoice'];

  it('flags a route the hub does not serve', () => {
    const audit = auditTurn({
      text: 'Ve a `/settings/developers` (o Configuración → Desarrolladores).',
      executed: [],
      knownRoutes: known,
    });

    expect(audit.unknownRoutes).toEqual(['/settings/developers']);
  });

  it('accepts the routes the hub really serves', () => {
    const audit = auditTurn({
      text: 'Lo tienes en /m/services/services y la configuración en /settings.',
      executed: [],
      knownRoutes: known,
    });

    expect(audit.unknownRoutes).toEqual([]);
  });

  // Without a route map (an early turn, or a caller that does not supply one) the lock must
  // stay quiet rather than flag every route it cannot verify.
  // A module's own tabs are the module's business, not the shell's: the map carries the
  // installed module (`/m/services`) and any tab under it is accepted. What must NOT be
  // accepted is a module that is not installed at all.
  it('accepts a tab under an installed module, and rejects an uninstalled one', () => {
    const audit = auditTurn({
      text: 'Míralo en /m/services/categories y luego en /m/payroll/list.',
      executed: [],
      knownRoutes: ['/m/services', '/settings'],
    });

    expect(audit.unknownRoutes).toEqual(['/m/payroll/list']);
  });

  it('says nothing when it has no map to check against', () => {
    const audit = auditTurn({ text: 'Ve a /settings/developers.', executed: [] });

    expect(audit.unknownRoutes).toEqual([]);
  });
});
