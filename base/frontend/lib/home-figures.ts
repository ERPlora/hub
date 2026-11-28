// The Home's figures: the panels painted as the library's figure card (StatCard). A figure whose app declares the colour
// of its measure (`options.tone`) may head the board in the row in colour, where each colour shows once. A stat's state
// (its severity) is said apart, in words: it never changes the colour of the figure.
import type { StatCardStatus, StatCardStatusTone, StatCardTone } from '@erplora/ui/components';

import type { WidgetDef } from '../operations/home';
import type { WidgetView } from './home-panels';

const FIGURE_KINDS: ReadonlySet<string> = new Set(['kpi', 'stat', 'sparkline']);
const STATUS_TONES: ReadonlySet<string> = new Set<StatCardStatusTone>(['success', 'warning', 'danger']);
const LIVELY_MIN = 2;
const LIVELY_MAX = 4;

/** A panel that is one figure read from its operation, not a component of its app. */
export function isFigure(widget: WidgetDef): boolean {
  return !widget.component && FIGURE_KINDS.has(widget.kind ?? '');
}

/** The colour of data of the panel's measure, when its app declares one of the six. */
export function figureTone(widget: WidgetDef): StatCardTone | undefined {
  const tone = widget.options.tone;
  return typeof tone === 'number' && Number.isInteger(tone) && tone >= 1 && tone <= 6 ? (tone as StatCardTone) : undefined;
}

/** The row in colour that heads the board: its first figures with a colour, in the board's order, one per colour and
 *  four at most; none with fewer than two. */
export function livelyRow(board: readonly WidgetDef[]): WidgetDef[] {
  const row: WidgetDef[] = [];
  const tones = new Set<StatCardTone>();
  for (const widget of board) {
    const tone = isFigure(widget) ? figureTone(widget) : undefined;
    if (tone === undefined || tones.has(tone)) continue;
    tones.add(tone);
    row.push(widget);
    if (row.length === LIVELY_MAX) break;
  }
  return row.length >= LIVELY_MIN ? row : [];
}

export interface FigureCard {
  value: string | null;
  note?: string;
  sparkline?: number[];
  status?: StatCardStatus;
}

/** What the figure card of a panel shows of its view: no value is its empty state. */
export function figureCard(view: WidgetView): FigureCard {
  switch (view.kind) {
    case 'kpi':
      return { value: view.value };
    case 'stat':
      if (view.label && STATUS_TONES.has(view.severity)) {
        return { value: view.value, status: { tone: view.severity as StatCardStatusTone, label: view.label } };
      }
      return view.label ? { value: view.value, note: view.label } : { value: view.value };
    case 'sparkline':
      return { value: view.value ?? null, sparkline: view.series };
    default:
      return { value: null };
  }
}
