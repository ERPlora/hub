// The Home's figures: the panels painted as the library's figure card (StatCard). A figure whose app declares the colour
// of its measure (`options.tone`) may head the board in the row in colour, where each colour shows once.
import type { StatCardTone } from '@erplora/ui/components';

import type { WidgetDef } from '../operations/home';
import type { WidgetView } from './home';

const FIGURE_KINDS: ReadonlySet<string> = new Set(['kpi', 'stat', 'sparkline']);
const LIVELY_MIN = 2;
const LIVELY_MAX = 4;

/** A panel that is one figure read from its operation. A stat that colours its figure by a severity keeps its own
 *  panel: the figure card never changes its colour by a state. */
export function isFigure(widget: WidgetDef): boolean {
  if (widget.component || !FIGURE_KINDS.has(widget.kind ?? '')) return false;
  return !(widget.kind === 'stat' && widget.map.severity);
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
}

/** What the figure card of a panel shows of its view: no value is its empty state. */
export function figureCard(view: WidgetView): FigureCard {
  switch (view.kind) {
    case 'kpi':
      return { value: view.value };
    case 'stat':
      return view.label ? { value: view.value, note: view.label } : { value: view.value };
    case 'sparkline':
      return { value: view.value ?? null, sparkline: view.series };
    default:
      return { value: null };
  }
}
