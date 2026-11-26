// The lines added to the check on screen: a product of the catalogue with its options of Modifiers, an open price, a
// service of Services and a menu of Menus. The first line opens the check (`sale.order.open`, with the title typed
// before, who serves it and the line sealed with the chosen professional) and the device remembers it; the next lines
// go to it; a second tap on a product raises its pending line (same professional, no note, discount or comp).
import { useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';

import { mergeableLine, mergeableServiceLine, plusOne } from '../../components/pos/till';
import { withApproval } from '../../lib/approval';
import type { ComboChoiceIn, OrderOut } from '../../operations';
import { type CheckWrites, toast } from './useCheckWrites';
import type { OpenLine, TillOptions, WriteResult } from './useTill';

type Opening = Pick<TillOptions, 'onOpened' | 'opening'>;
type Lines = CheckWrites & ReturnType<typeof useOpening>;

const staffOf = (staffId: string | null) => (staffId ? { staff_id: staffId } : {});

function useOpening({ check, pendingLabel, accept }: CheckWrites, options: Opening) {
  const open = useCommand('sale.order.open');
  const labelOf = () => ({ ...(pendingLabel.value ? { label: pendingLabel.value } : {}), ...options.opening?.() });

  async function opened(write: () => Promise<OrderOut>): Promise<void> {
    const created = await write();
    check.remember(created.id);
    pendingLabel.value = '';
    accept(created);
    options.onOpened?.(created.id);
  }

  return { open, labelOf, opened };
}

function useProductLines({ serial, order, check, accept, wordsOf, open, labelOf, opened }: Lines) {
  const addLine = useCommand('sale.order.add_line');
  const updateLine = useCommand('sale.order.update_line');

  function addProductLine(product: { id: string }, staffId: string | null, optionIds: readonly string[] = []): Promise<WriteResult> {
    // Only the ids travel: Modifiers values them on the server (a price from the browser buys nothing).
    const options = optionIds.length ? { option_ids: [...optionIds] } : {};
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        if (!id) {
          await opened(() => open.run({ ...labelOf(), lines: [{ product_id: product.id, ...staffOf(staffId), ...options }] }));
          return { ok: true } as const;
        }
        // A line with options is a dish of its own: it never raises another, nor is raised.
        const merge = order.value && !optionIds.length ? mergeableLine(order.value.lines, product.id, staffId) : undefined;
        accept(
          merge
            ? await updateLine.run({ order_id: id, line_id: merge.id, quantity: plusOne(merge.quantity) })
            : await addLine.run({ order_id: id, product_id: product.id, ...staffOf(staffId), ...options }),
        );
        return { ok: true } as const;
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') } as const;
      }
    });
  }

  const addProduct = (product: { id: string }, staffId: string | null, optionIds: readonly string[] = []) =>
    toast(addProductLine(product, staffId, optionIds));

  return { addProductLine, addProduct };
}

function useOpenLine({ serial, order, check, accept, wordsOf, open, labelOf, opened }: Lines) {
  const session = useSession();
  const addOpen = useCommand('sale.order.add_open_line');

  function addOpenLine(line: OpenLine, staffId: string | null): Promise<WriteResult> {
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        const typed = { ...line, ...staffOf(staffId) };
        if (!id && session.can('sale.sell_open_price')) {
          await opened(() => open.run({ ...labelOf(), open_lines: [typed] }));
          return { ok: true };
        }
        // Whoever may not sell at an open price opens the check empty and the line waits for a manager's approval.
        if (!id) await opened(() => open.run({ ...labelOf() }));
        const orderId = (order.value?.id ?? check.id.value) as string;
        accept(await withApproval(() => addOpen.run({ order_id: orderId, ...typed })));
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') };
      }
    });
  }

  return addOpenLine;
}

function useServiceLine({ serial, order, check, accept, wordsOf, open, labelOf, opened }: Lines) {
  const updateLine = useCommand('sale.order.update_line');
  const addServiceLine = useCommand('sale.order.add_service_line');

  function addService(service: { id: string }, staffId: string | null, unitPrice?: number): Promise<WriteResult> {
    const priced = unitPrice === undefined ? {} : { unit_price: unitPrice };
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        if (!id) {
          await opened(() => open.run({ ...labelOf(), service_lines: [{ service_id: service.id, ...priced, ...staffOf(staffId) }] }));
          return { ok: true };
        }
        const merge = unitPrice === undefined && order.value ? mergeableServiceLine(order.value.lines, service.id, staffId) : undefined;
        accept(
          merge
            ? await updateLine.run({ order_id: id, line_id: merge.id, quantity: plusOne(merge.quantity) })
            : await addServiceLine.run({ order_id: id, service_id: service.id, ...priced, ...staffOf(staffId) }),
        );
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') };
      }
    });
  }

  return addService;
}

function useComboLine({ serial, order, check, accept, wordsOf, open, labelOf, opened }: Lines) {
  const addCombo = useCommand('sale.order.add_combo_line');

  function addComboLine(combo: { id: string }, staffId: string | null, choices: readonly ComboChoiceIn[]): Promise<WriteResult> {
    // Only the choices travel: Menus prices the menu on the server. Each menu is a line of its own (its dishes
    // differ), so a second one never raises the first.
    const menu = { combo_id: combo.id, choices: [...choices], ...staffOf(staffId) };
    return serial(async () => {
      try {
        const id = order.value?.id ?? check.id.value;
        if (!id) {
          await opened(() => open.run({ ...labelOf(), combo_lines: [menu] }));
          return { ok: true };
        }
        accept(await addCombo.run({ order_id: id, ...menu }));
        return { ok: true };
      } catch (error) {
        return { ok: false, message: wordsOf(error, 'sale.pos.lineNotSaved') };
      }
    });
  }

  return addComboLine;
}

export function useAddLines(writes: CheckWrites, options: Opening) {
  const lines = { ...writes, ...useOpening(writes, options) };
  return {
    ...useProductLines(lines),
    addOpenLine: useOpenLine(lines),
    addService: useServiceLine(lines),
    addComboLine: useComboLine(lines),
  };
}
