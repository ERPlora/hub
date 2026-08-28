// **The declaración responsable, read for the owner's screen** (hub#528, art. 13.2 RRSIF).
//
// RD 1007/2023 art. 13.2 makes the producer's responsible declaration appear «por escrito y de modo
// visible en el propio sistema informático **en cada una de sus versiones**». The public archive on
// erplora.com covers the other half of that article — the customer and the reseller at the moment of
// acquisition — but a business inspected by the AEAT is asked to show it from ITS OWN till, and
// until hub#528 the Hub had nowhere to show it.
//
// `GET /api/system/declaration` answers with the very `SistemaInformatico` block that travels inside
// every record: the manufacturer's seven fields as the control plane serves them, plus the two only
// this hub can declare (`Version` = the binary it runs, `NumeroInstalacion` = its `hub_id`). This
// module only reads it. **Nothing is defaulted here on purpose**: a value invented in the browser
// would make the till certify an identity that the invoices do not carry, which is the precise
// failure art. 13 sanctions.
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/**
 * The nine elements of `SistemaInformatico`, in the order the XSD declares them — which is the
 * order the panel prints, so the screen can be read side by side with a record.
 *
 * The keys keep the AEAT's literal Spanish spelling because that is what the XML carries; a
 * camelCase transliteration would invent a second name for a legal element.
 */
export const DECLARATION_FIELDS = [
  'NombreRazon',
  'NIF',
  'NombreSistemaInformatico',
  'IdSistemaInformatico',
  'Version',
  'NumeroInstalacion',
  'TipoUsoPosibleSoloVerifactu',
  'TipoUsoPosibleMultiOT',
  'IndicadorMultiplesOT',
] as const;

export type DeclarationField = (typeof DECLARATION_FIELDS)[number];

/** What `GET /api/system/declaration` answers. */
export interface SystemDeclaration {
  /** The version of the binary this hub is running (`1.2.3`). */
  version: string;
  /** This installation before the AEAT: the `hub_id`. */
  numeroInstalacion: string;
  /** Where the SIGNED text lives, on the control plane this hub belongs to. */
  declarationUrl: string;
  /**
   * The block as it travels in every record, or `null` when the manufacturer's half has not
   * reached this hub yet. `null` is NOT «use defaults»: there are none for a legal declaration,
   * and in that state the fiscal engine refuses to build an envelope at all.
   */
  sistemaInformatico: Record<DeclarationField, string> | null;
}

const str = (v: unknown): string => (typeof v === 'string' ? v : '');

/**
 * Reads the block, or throws. **A refusal never resolves into an empty declaration**: a card that
 * silently showed nothing would look exactly like a hub with nothing to declare, and the screen
 * whose whole job is to be shown to an inspector is the last place for that. The caller paints its
 * own "could not load" state (hub#375).
 */
export async function fetchResponsibleDeclaration(): Promise<SystemDeclaration> {
  const res = await fetch(`${RUNTIME_URL}/api/system/declaration`, { headers: runtimeHeaders() });
  const payload = (await res.json().catch(() => null)) as Partial<SystemDeclaration> | null;
  if (!res.ok || !payload || typeof payload.declarationUrl !== 'string') {
    throw new Error(`GET /api/system/declaration → HTTP ${res.status}`);
  }
  const block = payload.sistemaInformatico;
  // All nine or none: the same all-or-nothing rule the runtime applies to the producer facts. A
  // partial block is not half a declaration, it is a wrong one.
  const complete =
    !!block &&
    typeof block === 'object' &&
    DECLARATION_FIELDS.every((field) => str((block as Record<string, unknown>)[field]).length > 0);
  return {
    version: str(payload.version),
    numeroInstalacion: str(payload.numeroInstalacion),
    declarationUrl: payload.declarationUrl,
    sistemaInformatico: complete
      ? (Object.fromEntries(
          DECLARATION_FIELDS.map((field) => [field, str((block as Record<string, unknown>)[field])]),
        ) as Record<DeclarationField, string>)
      : null,
  };
}
