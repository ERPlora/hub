//! Grounding audit of one assistant turn (hub#1038, #1039, #1041, #1044, #1047).
//!
//! ADR-0282 already tells the model, in words, not to claim a write it did not make and not
//! to invent a field it did not read. The QA pass of 2026-08-19 caught it doing both while
//! that prompt was live — so the guarantee cannot live in the prompt. It lives here: the
//! runtime holds the receipts (which tools ran, with what outcome) and checks the answer
//! against them before the user reads it.
//!
//! Deliberately pure: text in, verdict out. No transport, no LLM, no fixtures.

/** A tool the runtime actually ran this turn, with the outcome the dispatcher returned. */
export interface ExecutedTool {
  name: string;
  kind: 'query' | 'command';
  status: 'ok' | 'error' | 'cancelled';
  result: unknown;
}

export interface TurnAudit {
  /** The answer says something was written, but nothing was written. */
  claimedWithoutEffect: boolean;
  /** Identifiers printed to the user that no tool result of this turn carried. */
  unsourcedIds: string[];
  /** Screens named in the answer that this hub does not serve. */
  unknownRoutes: string[];
}

/**
 * Assertive success claims — first person, passive or "with success". Deliberately NOT the
 * bare participle: "cuando hayas creado el servicio" is advice, not a claim, and a lock that
 * cries wolf on ordinary answers stops being read.
 *
 * Cancellation verbs are absent on purpose: "acción cancelada" is TRUE when the user cancels,
 * and flagging it would punish the honest path.
 */
const CLAIM_PATTERNS: RegExp[] = [
  // es — "he creado", "hemos actualizado", "ya he eliminado"
  /\b(?:he|hemos)\s+(?:\w+\s+){0,2}?(?:cread|actualizad|eliminad|borrad|guardad|modificad|añadid|aplicad|dad\s+de\s+alta)\w*/i,
  // es — "se ha creado", "ha sido actualizada", "queda guardado"
  /\b(?:se\s+ha|se\s+han|ha\s+sido|han\s+sido|queda|quedan)\s+(?:\w+\s+){0,2}?(?:cread|actualizad|eliminad|borrad|guardad|modificad|añadid|aplicad)\w*/i,
  // es — "creada con éxito", "aplicado correctamente"
  /\b(?:cread|actualizad|eliminad|borrad|guardad|modificad|añadid|aplicad)\w*\s+(?:con\s+éxito|correctamente)/i,
  // en — "I've created", "we have updated"
  /\b(?:i(?:'ve)?|we)\s+(?:have\s+)?(?:\w+\s+){0,2}?(?:created|updated|deleted|removed|saved|applied|added)\b/i,
  // en — "has been created", "was successfully updated"
  /\b(?:has|have|was|were)\s+(?:been\s+)?(?:successfully\s+)?(?:created|updated|deleted|removed|saved|applied|added)\b/i,
  // en — "successfully created"
  /\bsuccessfully\s+(?:created|updated|deleted|removed|saved|applied|added)\b/i,
];

/**
 * Identifier shapes. ERPlora ids are UUIDs as TEXT (ADR-0007); the QA pass caught the model
 * printing `svc_7f2a1e8b`-style ids that cannot exist in the product at all. Both shapes are
 * checked, so a real id quoted back is verified rather than trusted.
 *
 * The hex run must be long enough that ordinary vocabulary (`iva_21`, `price_cents`,
 * `tax_category_key`) cannot reach it.
 */
const ID_PATTERNS: RegExp[] = [
  /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
  /\b[a-z]{2,8}_[0-9a-f]{6,}\b/gi,
];

/**
 * Routes the answer points the user at. The router's catch-all redirects an unknown path to
 * /dashboard, so an invented screen fails SILENTLY: the user follows the steps, lands
 * somewhere else and concludes their hub is broken (hub#1047, hub#1048).
 */
const ROUTE_IN_TEXT = /\/(?:m\/[\w-]+(?:\/[\w-]+)*|dashboard|settings|apps|system|billing|employees|files|profile|activation|api-docs)(?:\/[\w-]+)*/g;

/** Everything this turn is allowed to quote: what the tools returned, plus what the user typed. */
function sourcedText(executed: ExecutedTool[], userText: string | undefined): string {
  const fromTools = executed
    .map((t) => {
      try {
        return JSON.stringify(t.result ?? null);
      } catch {
        return '';
      }
    })
    .join(' ');
  return `${fromTools} ${userText ?? ''}`.toLowerCase();
}

export function auditTurn(turn: {
  text: string;
  executed: ExecutedTool[];
  userText?: string;
  /** The hub's real navigation map. Omit it and the route lock stays quiet, rather than
   *  flagging every route it has no way to verify. */
  knownRoutes?: string[];
}): TurnAudit {
  const { text, executed, userText, knownRoutes } = turn;

  const wroteSomething = executed.some((t) => t.kind === 'command' && t.status === 'ok');
  const claimsAWrite = CLAIM_PATTERNS.some((re) => re.test(text));

  const allowed = sourcedText(executed, userText);
  const seen = new Set<string>();
  const unsourcedIds: string[] = [];
  for (const re of ID_PATTERNS) {
    for (const match of text.matchAll(re)) {
      const id = match[0];
      const key = id.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      if (!allowed.includes(key)) unsourcedIds.push(id);
    }
  }

  const unknownRoutes: string[] = [];
  if (knownRoutes && knownRoutes.length > 0) {
    const map = new Set(knownRoutes.map((r) => r.replace(/\/+$/, '').toLowerCase()));
    const seenRoutes = new Set<string>();
    for (const match of text.matchAll(ROUTE_IN_TEXT)) {
      const route = match[0].replace(/\/+$/, '');
      const key = route.toLowerCase();
      if (seenRoutes.has(key)) continue;
      seenRoutes.add(key);
      // A module's tabs belong to the module, not to the shell: `/m/services` in the map
      // vouches for `/m/services/categories`. What the map must still reject is a module
      // that is not installed at all.
      const knownAsModule =
        key.startsWith('/m/') && [...map].some((k) => k.startsWith('/m/') && (key === k || key.startsWith(`${k}/`)));
      if (!map.has(key) && !knownAsModule) unknownRoutes.push(route);
    }
  }

  return { claimedWithoutEffect: claimsAWrite && !wroteSomething, unsourcedIds, unknownRoutes };
}
