// `useAgendaActions`: what the agenda's row actions do (WORKBOOK «Agenda»; APPOINTMENT-F03 to F11, F17).
// Confirm, Start, Complete and No-show run at once (the server judges the state); Cancel and Delete ask
// first (their dialogs read `target`); History opens the history; Edit hands the row to the page's panel;
// Charge («Go to the check» while it is open) opens the appointment's check in the till
// (`appointment.appointment.charge`, one per appointment) and goes to Sell, which shows it
// (`/sale/pos?order=<id>`). A drag moves the appointment; an overlap asks «Book anyway» first. Every refusal is told
// on the page (`notice`), never swallowed; the agenda itself changes through its live lists.
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { type Ref, ref, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import type { AppointmentRow } from '../operations';
import { useT } from './useT';

export interface Notice {
  tone: 'success' | 'danger' | 'info';
  text: string;
}

export interface Move {
  /** The new start, business wall clock (`2026-10-19T11:00`). */
  start: string;
  /** The new professional; `undefined` keeps it, `null` is refused by the server (nobody). */
  staffId?: string | null;
}

export interface AgendaActions {
  notice: Ref<Notice | null>;
  target: Ref<AppointmentRow | null>;
  cancelOpen: Ref<boolean>;
  deleteOpen: Ref<boolean>;
  historyOpen: Ref<boolean>;
  overlap: Ref<string | null>;
  deleting: ReturnType<typeof useCommand<'appointment.appointment.delete'>>;
  run(action: string, row: AppointmentRow): Promise<void>;
  move(row: AppointmentRow, move: Move): Promise<void>;
  confirmDelete(): Promise<void>;
  confirmOverlap(): Promise<void>;
}

const AT_ONCE = {
  confirm: 'appointment.appointment.confirm',
  start: 'appointment.appointment.start',
  complete: 'appointment.appointment.complete',
  no_show: 'appointment.appointment.mark_no_show',
} as const;

export function useAgendaActions(options: { onEdit: (row: AppointmentRow) => void }): AgendaActions {
  const t = useT();
  const router = useRouter();
  const notice = ref<Notice | null>(null);
  const target = shallowRef<AppointmentRow | null>(null);
  const cancelOpen = ref(false);
  const deleteOpen = ref(false);
  const historyOpen = ref(false);
  const overlap = ref<string | null>(null);
  let pendingMove: { row: AppointmentRow; move: Move } | null = null;

  const commands = {
    confirm: useCommand(AT_ONCE.confirm),
    start: useCommand(AT_ONCE.start),
    complete: useCommand(AT_ONCE.complete),
    no_show: useCommand(AT_ONCE.no_show),
  };
  const charge = useCommand('appointment.appointment.charge');
  const deleting = useCommand('appointment.appointment.delete');
  const reschedule = useCommand('appointment.appointment.reschedule');

  const refused = (error: unknown): void => {
    notice.value = { tone: 'danger', text: (error as ApiError)?.message ?? t('appointment.actions.error') };
  };

  async function run(action: string, row: AppointmentRow): Promise<void> {
    notice.value = null;
    target.value = row;
    if (action in commands) {
      try {
        await commands[action as keyof typeof commands].run({ id: row.id });
      } catch (error) {
        refused(error);
      }
      return;
    }
    if (action === 'cancel') cancelOpen.value = true;
    else if (action === 'delete') {
      deleting.error.value = null;
      deleteOpen.value = true;
    } else if (action === 'history') historyOpen.value = true;
    else if (action === 'edit') options.onEdit(row);
    else if (action === 'charge') {
      try {
        const opened = await charge.run({ id: row.id });
        await router.push({ path: '/sale/pos', query: { order: opened.order_id } });
      } catch (error) {
        refused(error);
      }
    }
  }

  async function sendMove(row: AppointmentRow, move: Move, confirmOverlap: boolean): Promise<void> {
    try {
      await reschedule.run({
        id: row.id,
        start: move.start,
        ...(move.staffId !== undefined ? { staff_id: move.staffId } : {}),
        confirm_overlap: confirmOverlap,
      });
      notice.value = { tone: 'success', text: t('appointment.grid.moved') };
    } catch (error) {
      if ((error as ApiError)?.code === 'appointment.overlap_needs_confirmation') {
        pendingMove = { row, move };
        overlap.value = (error as ApiError).message;
        return;
      }
      refused(error);
    }
  }

  async function move(row: AppointmentRow, change: Move): Promise<void> {
    notice.value = null;
    await sendMove(row, change, false);
  }

  async function confirmOverlap(): Promise<void> {
    const waiting = pendingMove;
    overlap.value = null;
    pendingMove = null;
    if (waiting) await sendMove(waiting.row, waiting.move, true);
  }

  async function confirmDelete(): Promise<void> {
    if (!target.value) return;
    try {
      await deleting.run({ id: target.value.id });
    } catch {
      return; // The dialog says why.
    }
    deleteOpen.value = false;
  }

  return { notice, target, cancelOpen, deleteOpen, historyOpen, overlap, deleting, run, move, confirmDelete, confirmOverlap };
}
