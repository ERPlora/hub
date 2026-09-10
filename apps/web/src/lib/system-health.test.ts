// What the hub says about itself, in the words of the person who owns the bar (hub#375).
//
// The bug this closes is not a rendering bug: the panel said **«System disconnected»** on a hub that
// was working perfectly, because the only thing it probed was the Bridge on `localhost:12321` — a
// port that in a plain browser is *supposed* to be silent. The sentence was alarming, it was about
// the printer host, and it was wrong. **A status that lies is worse than no status at all.**
//
// So these tests protect three claims, in this order:
//
//   1. **It talks about the printer, never about «the system».** The hub is obviously running — you
//      are reading its screen. A probe that only ever knew about the printer host can never be
//      promoted to a verdict about everything.
//   2. **It only talks about the printer when something prints.** No printing module, no sentence:
//      a hairdresser with no printer does not need a badge about one.
//   3. **«I could not check» is not «it is fine», and it is not «it is broken» either.** It is its
//      own state, it is never green, and it carries no call to action — our failed probe is not the
//      owner's homework (the same reasoning `unavailable` earned in the checklist, hub#371).
//
// And the fourth claim, which is the same one aimed at the numbers: **a metric nobody reported is
// not 0%.** A gauge sitting green at zero is exactly how hub#229 shipped «64 MB of memory» read
// from the wrong cgroup and nobody blinked.
//
// The copy is asserted against the REAL catalogues, English and Spanish. Here the wording *is* the
// feature: testing it against strings invented in the test file would test nothing.
import { describe, expect, it } from 'vitest';

import {
  PRINTING_MODULE_ID,
  PRINTING_ROUTE,
  STATE_ATTENTION,
  STATE_OK,
  STATE_UNKNOWN,
  isPrintingInstalled,
  printerLine,
  printerSetupStepKeys,
  probeFromCoverage,
  reportedCount,
  usagePercent,
  type InstalledModuleRef,
} from './system-health';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

/** Resolves a dotted i18n key against a catalogue; `undefined` when the key is not there. */
function lookup(catalogue: unknown, key: string): string | undefined {
  const value = key.split('.').reduce<unknown>(
    (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
    catalogue,
  );
  return typeof value === 'string' ? value : undefined;
}

/** Every leaf string of a catalogue, however deep it is nested. */
function allStrings(node: unknown): string[] {
  if (typeof node === 'string') return [node];
  if (!node || typeof node !== 'object') return [];
  return Object.values(node as Record<string, unknown>).flatMap(allStrings);
}

const printingInstalled: InstalledModuleRef[] = [
  { id: 'sales', status: 'active' },
  { id: PRINTING_MODULE_ID, status: 'active' },
];

describe('it talks about the printer, not about «the system»', () => {
  it('says the printer is not connected — not that the hub is down', () => {
    const line = printerLine('not_connected', printingInstalled);

    expect(line?.key).toBe('printer');
    const title = lookup(enCatalogue, line!.titleKey);
    expect(title).toBe('Printer not connected');
  });

  it('never claims the whole system is disconnected, in either language', () => {
    for (const probe of ['ready', 'not_connected', 'unknown'] as const) {
      const line = printerLine(probe, printingInstalled)!;
      for (const catalogue of [enCatalogue, esCatalogue]) {
        const sentences = [lookup(catalogue, line.titleKey), lookup(catalogue, line.detailKey)].join(' ');
        expect(sentences.toLowerCase()).not.toContain('system disconnected');
        expect(sentences.toLowerCase()).not.toContain('sistema desconectado');
      }
    }
  });

  it('has no «System disconnected» left anywhere in the catalogues to come back', () => {
    // Copy nobody renders is copy that gets rendered again by the next person who needs a badge.
    // The sentence was the bug; leaving it in the drawer keeps the bug one autocomplete away.
    for (const [name, catalogue] of [['en', enCatalogue], ['es', esCatalogue]] as const) {
      const strings = allStrings(catalogue).map((s) => s.toLowerCase());
      expect(strings, name).not.toContain('system disconnected');
      expect(strings, name).not.toContain('sistema desconectado');
      expect(strings, name).not.toContain('system connected');
      expect(strings, name).not.toContain('sistema conectado');
      // Same claim, shortened. A bare «Disconnected» next to a heading is the same verdict about
      // a whole machine, told in one word.
      expect(strings, name).not.toContain('disconnected');
      expect(strings, name).not.toContain('desconectado');
    }
  });

  it('has no machine-room status copy left to paste back either', () => {
    // «Bridge connection» / «The Bridge client is not running on this device» were the same
    // sentence in the same place, wearing the name of a process the owner has never heard of.
    for (const [name, catalogue] of [['en', enCatalogue], ['es', esCatalogue]] as const) {
      const strings = allStrings(catalogue).map((s) => s.toLowerCase());
      expect(strings, name).not.toContain('bridge connection');
      expect(strings, name).not.toContain('conexión bridge');
      expect(strings.some((s) => s.includes('bridge client')), name).toBe(false);
      expect(strings.some((s) => s.includes('cliente bridge')), name).toBe(false);
    }
  });

  it('speaks the trade, not the machine room: no Bridge, no localhost, no daemons', () => {
    for (const probe of ['ready', 'not_connected', 'unknown'] as const) {
      const line = printerLine(probe, printingInstalled)!;
      for (const catalogue of [enCatalogue, esCatalogue]) {
        const sentences = [lookup(catalogue, line.titleKey), lookup(catalogue, line.detailKey)].join(' ').toLowerCase();
        for (const jargon of ['bridge', 'localhost', 'daemon', 'websocket', 'puerto 12321']) {
          expect(sentences).not.toContain(jargon);
        }
      }
    }
  });
});

describe('nothing is said about a printer nobody has', () => {
  it('stays silent when the printing module is not installed', () => {
    expect(printerLine('not_connected', [{ id: 'sales', status: 'active' }])).toBeNull();
  });

  it('stays silent when printing is installed but switched off', () => {
    expect(printerLine('not_connected', [{ id: PRINTING_MODULE_ID, status: 'inactive' }])).toBeNull();
  });

  it('stays silent when the module list could not be read — an absence is not an answer', () => {
    expect(printerLine('not_connected', null)).toBeNull();
  });

  it('speaks as soon as printing is installed and running', () => {
    expect(printerLine('not_connected', printingInstalled)).not.toBeNull();
  });

  it('names the module and the screen that really exist, not ones we made up', () => {
    // Both are contracts owned elsewhere: the id and the `setup.route` of
    // `modules-workspace/modules/printing/module.json`. Pinned to the literals on purpose — a
    // constant that only ever agrees with itself would let the badge go quiet on every real hub
    // (or send the owner to a 404) without a single test noticing.
    expect(PRINTING_MODULE_ID).toBe('printing');
    expect(PRINTING_ROUTE).toBe('/m/printing/printing');
  });

  it('reads the module list the same way the badge does', () => {
    expect(isPrintingInstalled(printingInstalled)).toBe(true);
    expect(isPrintingInstalled([{ id: PRINTING_MODULE_ID, status: 'inactive_auto' }])).toBe(false);
    expect(isPrintingInstalled([])).toBe(false);
    expect(isPrintingInstalled(null)).toBe(false);
  });
});

describe('«I could not check» is its own state', () => {
  it('is never painted as working', () => {
    const line = printerLine('unknown', printingInstalled)!;

    expect(line.state).toBe(STATE_UNKNOWN);
    expect(line.tone).toBe('neutral');
    expect(line.tone).not.toBe('success');
  });

  it('carries no call to action: our failed probe is not the owner’s homework', () => {
    expect(printerLine('unknown', printingInstalled)!.action).toBeNull();
  });

  it('says out loud that we do not know, in both languages', () => {
    const line = printerLine('unknown', printingInstalled)!;
    expect(lookup(enCatalogue, line.titleKey)).toBe("We couldn't check the printer");
    expect(lookup(esCatalogue, line.titleKey)).toBe('No hemos podido comprobar la impresora');
  });

  it('is what coverage we could not read means — never «not connected»', () => {
    expect(probeFromCoverage(null)).toBe('unknown');
    expect(probeFromCoverage(undefined)).toBe('unknown');
  });

  it('keeps the two real answers apart', () => {
    expect(probeFromCoverage([{ role: 'receipt', waiting: 0, liveHosts: 1 }])).toBe('ready');
    expect(probeFromCoverage([{ role: 'receipt', waiting: 0, liveHosts: 0 }])).toBe('not_connected');
  });
});

// hub#1731 — the badge read «Printer ready» on a hub where NO printer had ever been registered,
// so the till was told everything was fine while the receipts piled up in the queue unread. The
// badge was drawn from the Bridge probe, which inside the installed app answers `online: true`
// unconditionally: it reported that the local print HOST was up, never that anybody was taking
// paper out. The only fact that answers the owner's question is per-role coverage.
describe('the printer badge answers «is my receipt coming out?» (hub#1731)', () => {
  it('with NOBODY registered for receipts it is NOT ready — it asks for attention', () => {
    // The reported case: a brand-new hub with the printing module on and no printer set up.
    // Coverage comes back EMPTY, which is a read answer and not an unread one: nobody is there.
    const line = printerLine(probeFromCoverage([]), printingInstalled)!;

    expect(line.state).toBe(STATE_ATTENTION);
    expect(line.tone).not.toBe('success');
    expect(lookup(enCatalogue, line.titleKey)).not.toBe('Printer ready');
    // And it says what to do, on the printing module's own screen.
    expect(line.action?.route).toBe(PRINTING_ROUTE);
  });

  it('a live host for ANOTHER station does not make the receipt printer ready', () => {
    // A kitchen printer draining kitchen orders says nothing about the receipt roll — and this is
    // exactly how a half-set-up restaurant would have kept the green badge.
    expect(probeFromCoverage([{ role: 'kitchen', waiting: 0, liveHosts: 2 }])).toBe('not_connected');
  });

  it('a station registered but NOT reporting is not ready either', () => {
    // `liveHosts` already excludes hosts past the TTL: a till that was unplugged stops covering.
    expect(probeFromCoverage([{ role: 'receipt', waiting: 3, liveHosts: 0 }])).toBe('not_connected');
  });

  it('is ready only when somebody is actually draining receipts', () => {
    const line = printerLine(
      probeFromCoverage([
        { role: 'receipt', waiting: 0, liveHosts: 1 },
        { role: 'kitchen', waiting: 0, liveHosts: 0 },
      ]),
      printingInstalled,
    )!;

    expect(line.state).toBe(STATE_OK);
    expect(lookup(enCatalogue, line.titleKey)).toBe('Printer ready');
  });

  it('coverage we could not read is never green (hub#375 still holds)', () => {
    const line = printerLine(probeFromCoverage(null), printingInstalled)!;
    expect(line.state).toBe(STATE_UNKNOWN);
    expect(line.tone).toBe('neutral');
    expect(line.action).toBeNull();
  });
});

describe('what needs doing comes with the way to do it', () => {
  it('offers the printing screen when the printer is not connected', () => {
    const line = printerLine('not_connected', printingInstalled)!;

    expect(line.state).toBe(STATE_ATTENTION);
    expect(line.tone).toBe('warning');
    expect(line.action?.route).toBe(PRINTING_ROUTE);
    expect(lookup(enCatalogue, line.action!.labelKey)).toBe('Set up printing');
    expect(lookup(esCatalogue, line.action!.labelKey)).toBe('Configurar la impresión');
  });

  it('tells the owner the till still charges — the receipt just comes out here', () => {
    const line = printerLine('not_connected', printingInstalled)!;
    expect(lookup(enCatalogue, line.detailKey)).toContain('keep charging');
    expect(lookup(esCatalogue, line.detailKey)).toContain('seguir cobrando');
  });

  it('says the same thing the state means — every state, both sentences', () => {
    // Not decoration: a green pill wearing the «not connected» sentence, or a «we could not check»
    // card promising that receipts come out on their own, is the lie back with a different key.
    // Each state is pinned to the words it is allowed to say.
    const sentences = (probe: 'ready' | 'not_connected' | 'unknown') => {
      const line = printerLine(probe, printingInstalled)!;
      return [lookup(enCatalogue, line.titleKey), lookup(enCatalogue, line.detailKey)];
    };

    expect(sentences('ready')).toEqual([
      'Printer ready',
      'Receipts come out on their own when you charge.',
    ]);
    expect(sentences('not_connected')).toEqual([
      'Printer not connected',
      'You can keep charging: the receipt opens on this screen and you print it from here.',
    ]);
    expect(sentences('unknown')).toEqual([
      "We couldn't check the printer",
      "We don't know whether it is connected — nothing else is affected. We will check again on our own.",
    ]);
  });

  it('offers nothing when the printer is ready: there is nothing to fix', () => {
    const line = printerLine('ready', printingInstalled)!;

    expect(line.state).toBe(STATE_OK);
    expect(line.tone).toBe('success');
    expect(line.action).toBeNull();
  });

  it('every sentence and every button it names exists in English and in Spanish', () => {
    for (const probe of ['ready', 'not_connected', 'unknown'] as const) {
      const line = printerLine(probe, printingInstalled)!;
      const keys = [line.titleKey, line.detailKey, ...(line.action ? [line.action.labelKey] : [])];
      for (const key of keys) {
        expect(lookup(enCatalogue, key), `${key} in en`).toBeTruthy();
        expect(lookup(esCatalogue, key), `${key} in es`).toBeTruthy();
      }
    }
  });
});

describe('a number nobody reported is not zero', () => {
  it('does not turn a missing metric into 0%', () => {
    expect(usagePercent(null)).toEqual({ known: false, value: null });
    expect(usagePercent(undefined)).toEqual({ known: false, value: null });
    expect(usagePercent({ fraction: null })).toEqual({ known: false, value: null });
    expect(usagePercent({})).toEqual({ known: false, value: null });
  });

  it('does not trust a reading that cannot be true', () => {
    expect(usagePercent({ fraction: Number.NaN })).toEqual({ known: false, value: null });
    expect(usagePercent({ fraction: Number.POSITIVE_INFINITY })).toEqual({ known: false, value: null });
    expect(usagePercent({ fraction: -0.2 })).toEqual({ known: false, value: null });
  });

  it('reports a real zero as a real zero', () => {
    expect(usagePercent({ fraction: 0 })).toEqual({ known: true, value: 0 });
  });

  it('rounds the fraction to whole percent', () => {
    expect(usagePercent({ fraction: 0.324 })).toEqual({ known: true, value: 32 });
    expect(usagePercent({ fraction: 0.996 })).toEqual({ known: true, value: 100 });
  });

  it('keeps «over the limit» as news, not as an unreadable metric', () => {
    expect(usagePercent({ fraction: 1.4 })).toEqual({ known: true, value: 100 });
  });

  it('does not turn a missing count into 0 either', () => {
    expect(reportedCount(null)).toEqual({ known: false, value: null });
    expect(reportedCount(undefined)).toEqual({ known: false, value: null });
    expect(reportedCount(Number.NaN)).toEqual({ known: false, value: null });
    expect(reportedCount(-1)).toEqual({ known: false, value: null });
  });

  it('reports a real count, zero included', () => {
    expect(reportedCount(0)).toEqual({ known: true, value: 0 });
    expect(reportedCount(12)).toEqual({ known: true, value: 12 });
  });

  it('names the unreadable metric instead of leaving a green gauge at zero', () => {
    expect(lookup(enCatalogue, 'system.health.notMeasured')).toBe("We couldn't read this");
    expect(lookup(esCatalogue, 'system.health.notMeasured')).toBe('No hemos podido leerlo');
  });
});

// ── Getting a printer answering, from where the user actually is (hub#480) ──────────────────────

describe('printerSetupStepKeys', () => {
  it('walks a browser through downloading and installing the app first', () => {
    expect(printerSetupStepKeys(false)).toEqual([
      'system.stepDownload',
      'system.stepInstall',
      'system.stepPair',
      'system.stepConfigure',
    ]);
  });

  it('does not tell the installed app to go and install itself', () => {
    // Inside `com.erplora.app` the first two steps are already done — that app IS the print host
    // (ADR-0196) — and the three buttons offering its installer were `window.open` calls that open
    // nothing there anyway. A step someone cannot take is a dead end with a number in front of it.
    expect(printerSetupStepKeys(true)).toEqual(['system.stepPair', 'system.stepConfigure']);
  });

  it('keeps both lists ending at the same place, in both languages', () => {
    for (const catalogue of [enCatalogue, esCatalogue]) {
      for (const key of printerSetupStepKeys(false)) {
        expect(lookup(catalogue, key), `${key} has no sentence`).toBeTruthy();
      }
    }
  });
});
