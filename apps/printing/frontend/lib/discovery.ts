// Finding the printers the device reaches (PRINTING-F02). Only the native app can look — mDNS and the
// sweep of port 9100, the computer's print queues, the paired Bluetooth printers — with its command
// `erplora_discover_printers` (ERPlora/app, through Tauri's global bridge, `withGlobalTauri`). Its answer
// is the outcome of `crates/peripherals/src/discovery.rs`: the printers found, or the permission the
// device denied (so an empty list always means «nothing found», hub#338/#1773); a refusal is a bare
// string. Each printer becomes the draft of «New printer»: the person still names it and gives it a role.
import type { PaperWidth, PrinterKind } from '../operations';

/** A printer as the app's scan gives it (`protocol::PrinterInfo`). */
export interface FoundPrinter {
  /** `network:<ip>:<port>`, `bluetooth:<mac>` or `usb:<queue>`. */
  id: string;
  name: string;
  type: string;
  /** `a4` (it announces IPP: an office printer, no ESC/POS) or `unknown`. */
  category?: string;
  status?: string;
  paper_width?: number;
  mac?: string;
}

export type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>;

/** What «New printer» starts with for a printer found. */
export interface PrinterDraft {
  name: string;
  kind: Exclude<PrinterKind, 'system'>;
  address: string;
  port: number | null;
  paper_width: PaperWidth;
}

/** A printer found that can be added, and whether the business already has it. */
export interface Candidate {
  id: string;
  name: string;
  added: boolean;
  draft: PrinterDraft;
}

export type DiscoveryResult =
  | { kind: 'browser' }
  | { kind: 'found'; printers: Candidate[] }
  | { kind: 'denied' }
  | { kind: 'unlinked' }
  | { kind: 'failed' };

/** The refusal of a command the app keeps for the business it is linked to (`hub_link.rs`). */
const NOT_THE_LINKED_HUB = 'not_the_linked_hub';
/** The longest printer name the server keeps. */
const MAX_NAME = 100;

type TauriWindow = { __TAURI__?: { core?: { invoke?: Invoke } } };

/** The native app's `invoke`, or `null` in a browser (no bridge: nothing can reach a printer). */
export function nativeInvoke(win: unknown = window): Invoke | null {
  const invoke = (win as TauriWindow).__TAURI__?.core?.invoke;
  return typeof invoke === 'function' ? invoke : null;
}

/** The draft of a printer found, or `null` when it cannot be added as a receipt printer. */
export function draftOf(found: FoundPrinter): PrinterDraft | null {
  if (found.category === 'a4') return null;
  const at = found.id.indexOf(':');
  const scheme = at > 0 ? found.id.slice(0, at) : '';
  const rest = at > 0 ? found.id.slice(at + 1) : '';
  let kind: PrinterDraft['kind'];
  let address = rest;
  let port: number | null = null;
  if (scheme === 'network') {
    const colon = rest.lastIndexOf(':');
    port = colon > 0 ? Number.parseInt(rest.slice(colon + 1), 10) : Number.NaN;
    if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
    address = rest.slice(0, colon);
    kind = 'network';
  } else if (scheme === 'bluetooth') {
    address = rest.toUpperCase();
    kind = 'bluetooth';
  } else if (scheme === 'usb') {
    kind = 'usb';
  } else {
    return null;
  }
  if (!address) return null;
  const name = (found.name ?? '').trim() || address;
  return { name: name.slice(0, MAX_NAME), kind, address, port, paper_width: found.paper_width === 58 ? 58 : 80 };
}

/** The target the server keeps for this printer (`Printer.target`), to know a printer already added. */
export function targetOf(draft: PrinterDraft): string {
  return draft.kind === 'network' ? `network:${draft.address}:${draft.port}` : `${draft.kind}:${draft.address}`;
}

/** Asks the app what it reaches. `known`: the targets of the business's printers. */
export async function discoverPrinters(invoke: Invoke | null, known: readonly string[]): Promise<DiscoveryResult> {
  if (!invoke) return { kind: 'browser' };
  let outcome: unknown;
  try {
    outcome = await invoke('erplora_discover_printers');
  } catch (refused) {
    return { kind: refused === NOT_THE_LINKED_HUB ? 'unlinked' : 'failed' };
  }
  const answer = outcome as { status?: string; printers?: FoundPrinter[] } | null;
  if (answer?.status === 'local_network_permission_denied') return { kind: 'denied' };
  if (answer?.status !== 'scanned' || !Array.isArray(answer.printers)) return { kind: 'failed' };
  const have = new Set(known.map((target) => target.toUpperCase()));
  const printers: Candidate[] = [];
  for (const found of answer.printers) {
    const draft = draftOf(found);
    if (draft) printers.push({ id: found.id, name: draft.name, added: have.has(targetOf(draft).toUpperCase()), draft });
  }
  return { kind: 'found', printers };
}
