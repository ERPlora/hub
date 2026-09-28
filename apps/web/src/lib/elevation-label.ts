// Qué se está aprobando, dicho en las palabras del negocio (hub#579).
//
// El diálogo de aprobación no imprimía NADA: ni la acción, ni siquiera de qué app venía. El
// encargado tecleaba su PIN a ciegas, y un recibo (`approved_by`) que no dice qué se aprobó es un
// sello de goma.
//
// Lo que **no** se hace, y sigue siendo la decisión de hub#363: imprimir la clave de permiso o el
// nombre del command. `sales.void` es vocabulario nuestro, no del mostrador — y enseñarlo en la
// pantalla que mira el cliente sería resolver el problema rompiendo la razón por la que existía.
//
// La escalera, de mejor a peor: la traducción que el MÓDULO da a ese command → el nombre localizado
// del módulo → una frase genérica. Nunca el command crudo.
//
// hub#2180: the dialog also says HOW MUCH is being approved, when the module opts in. «Aplicar a
// una línea un descuento del 90 %» is what Toast and Square print instead of a generic «line
// discount above the limit» — the manager can tell a reasonable discount from an out-of-proportion
// one before signing off. A command's `approval_label` is a template next to its plain `label`;
// only the payload fields the template names by name ever reach this customer-facing screen (the
// hub#363 rule extends to the payload: it is not the counter's business either).
import { ref } from 'vue';

import { getLocale } from '../i18n';
import { formatMoney } from './money';
import type { InstalledManifest } from './module-loader';

/** Lo que un módulo aporta para poder nombrar sus acciones. */
export interface ElevationCatalogueEntry {
  moduleId: string;
  /** Nombre del módulo YA localizado (el mismo que pinta la navegación). */
  moduleName: string;
  /** `commands["<módulo>.<acción>"]` de su `locales/<lang>.json`. */
  commands: Record<
    string,
    {
      label?: string;
      /**
       * Optional template for the figure being approved (hub#2180), e.g.
       * `"Apply a {discount_percent, percent} line discount"` or
       * `"Discount of {discount_amount, money}"`. Holes are `{field}` (bare text or number),
       * `{field, money}` (minor units, hub currency) or `{field, percent}` (0-100). Only the
       * fields the template names by name are ever read from the payload (hub#363: the payload is
       * not the counter's business). When any hole cannot be resolved, the whole template is
       * dropped and the plain `label` is used instead — never a half-rendered sentence.
       */
      approval_label?: string;
      /**
       * Whole-sentence variants of `approval_label` for a command whose figures may be zero
       * (hub#2186), e.g. a ticket discount with a percentage, a fixed amount or both. Tried in
       * order; a number hole at ZERO counts as absent, so the first sentence whose holes are all
       * filled with non-zero figures wins. When none can be filled, `approval_label` and then
       * `label` apply as before. A separate key so that a shell from before hub#2186 ignores it.
       */
      approval_labels?: readonly string[];
    }
  >;
}

/** Lo que el diálogo pinta. Cadenas vacías = «no se sabe», y la UI cae a su copia genérica. */
export interface ElevationDescription {
  /** La acción en palabras del negocio («Anular una venta»). */
  action: string;
  /** De qué app viene, localizado («Ventas / TPV»). */
  moduleName: string;
}

/** El módulo de un command namespaced: lo de delante del PRIMER punto (`sales.orders.void`). */
export function moduleOfCommand(command: string): string {
  const dot = command.indexOf('.');
  return dot > 0 ? command.slice(0, dot) : '';
}

/**
 * Matches a template hole: `{field}` or `{field, format}`. The field name is `[a-z0-9_]+` (a
 * top-level payload key); the format, when present, is a bare word (`money`, `percent`, …).
 */
const APPROVAL_HOLE = /\{\s*([a-z0-9_]+)\s*(?:,\s*([a-z]+)\s*)?\}/gi;

/**
 * Renders one hole's value, or `null` when it cannot be shown as-is. `format` picks the shape:
 * `money` and `percent` both require a finite number (anything else — string, `null`, `NaN`,
 * `Infinity`, an object, a boolean — refuses rather than guess); a bare hole accepts a non-blank
 * string or a finite number. An unknown format name always refuses.
 */
function formatHole(value: unknown, format: string | undefined, zeroIsAbsent: boolean): string | null {
  if (zeroIsAbsent && value === 0) return null;
  if (format === 'money') {
    return typeof value === 'number' && Number.isFinite(value) ? formatMoney(value) : null;
  }
  if (format === 'percent') {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null;
    return new Intl.NumberFormat(getLocale(), { style: 'percent', maximumFractionDigits: 2, useGrouping: true }).format(
      value / 100,
    );
  }
  if (format) return null; // unrecognised format name, e.g. `date`
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed === '' ? null : trimmed;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    // Grouped from four digits like money (hub#1090), not CLDR's Spanish «1234,5».
    return new Intl.NumberFormat(getLocale(), { useGrouping: true }).format(value);
  }
  return null;
}

/**
 * Fills `template`'s holes from `payload`, or returns `''` when it cannot be filled completely —
 * a missing field, an unresolvable value, or a leftover `{`/`}` (an unmatched or malformed hole)
 * all fall back the same way. Fields are read as OWN top-level keys only, never inherited ones.
 * With `zeroIsAbsent` (the `approval_labels` variants, hub#2186) a number at zero cannot fill a hole.
 */
function renderApprovalTemplate(template: string, payload: Record<string, unknown>, zeroIsAbsent = false): string {
  let resolved = true;
  const rendered = template.replace(APPROVAL_HOLE, (whole, field: string, format: string | undefined) => {
    if (!Object.prototype.hasOwnProperty.call(payload, field)) {
      resolved = false;
      return whole;
    }
    const filled = formatHole(payload[field], format, zeroIsAbsent);
    if (filled === null) {
      resolved = false;
      return whole;
    }
    return filled;
  });
  if (!resolved || rendered.includes('{') || rendered.includes('}')) return '';
  return rendered.trim();
}

/**
 * Describes the action waiting for approval. `ask` is accepted partially on purpose: only `command`
 * and `payload` are used here, and taking the whole `ElevationAsk` would tie this function —and its
 * tests— to the transport. `payload` is read only to fill the holes its `approval_label` names
 * (hub#2180): a field the template did not ask for by name is never shown.
 */
export function describeElevation(
  ask: { command: string; permission?: string; payload?: Record<string, unknown> },
  catalogue: readonly ElevationCatalogueEntry[],
): ElevationDescription {
  const moduleId = moduleOfCommand(ask.command);
  const entry = catalogue.find((c) => c.moduleId === moduleId);
  if (!entry) return { action: '', moduleName: '' };
  const commandEntry = entry.commands[ask.command];
  const rendered = ask.payload && commandEntry ? renderApproval(commandEntry, ask.payload) : '';
  return {
    action: rendered || commandEntry?.label?.trim() || '',
    moduleName: entry.moduleName.trim(),
  };
}

/**
 * The first `approval_labels` variant that fills with non-zero figures, else `approval_label` as
 * written, else `''`. The locale is module-supplied JSON: a non-list or a non-text entry is skipped.
 */
function renderApproval(
  commandEntry: { approval_label?: unknown; approval_labels?: unknown },
  payload: Record<string, unknown>,
): string {
  const variants = Array.isArray(commandEntry.approval_labels) ? commandEntry.approval_labels : [];
  for (const variant of variants) {
    if (typeof variant !== 'string') continue;
    const rendered = renderApprovalTemplate(variant, payload, true);
    if (rendered) return rendered;
  }
  const template = commandEntry.approval_label;
  return typeof template === 'string' && template ? renderApprovalTemplate(template, payload) : '';
}

/** El catálogo vigente. Vacío = todavía no se sabe, y la escalera degrada al mensaje genérico. */
export const elevationCatalogue = ref<ElevationCatalogueEntry[]>([]);

/**
 * Lo llena desde lo que el shell ya carga. El `import()` es DINÁMICO a propósito: `module-loader`
 * arrastra el registro de iconos, y meterlo en el grafo estático de un diálogo que vive montado
 * siempre convierte una pantalla de aprobación en un motivo para cargar medio shell.
 */
export async function loadElevationCatalogue(): Promise<void> {
  try {
    const { loadInstalledManifests } = await import('./module-loader');
    elevationCatalogue.value = catalogueFromManifests(await loadInstalledManifests());
  } catch {
    elevationCatalogue.value = [];
  }
}

/** Construye el catálogo desde lo que ya carga el shell (manifests instalados + su locale). */
export function catalogueFromManifests(
  installed: readonly InstalledManifest[],
): ElevationCatalogueEntry[] {
  return installed.map((m) => ({
    moduleId: m.moduleId,
    // El `name` del manifest es el inglés canónico (ADR-0055); el locale del módulo lo traduce.
    moduleName: m.locale?.name?.trim() || m.manifest.name,
    commands: m.locale?.commands ?? {},
  }));
}
