// A manager's approval on the client (BASE-G136; the old hub's HUB_SHELL-F51). An app wraps a command a manager may
// approve (one its `LiveAppConfig.approvals` names) in `withApproval(() => command.run(input))`: when the hub answers
// `requires_elevation`, the dialog «An approval is needed» asks who approves it (their PIN or badge) and the command is
// repeated once with the pass, which the SDK sends in `X-Elevation-Token` while `approvalPass` returns it (`main.ts`
// hands it to `createLiveClient`). «Cancel» hands back the original refusal, for the app to tell; a second question
// after approving is a refusal (the pass ran out, or another copy of the hub), never a second dialog. The same command
// repeated while the dialog is open (a double tap) gets the result of the one that opened it, and a different one is
// refused, not stacked.
import { ApiError } from '@erplora/ui/sdk';
import { shallowRef } from 'vue';

/** What the hub says can be approved: the command, what it does in words, and that very request's fingerprint. */
export interface ApprovalQuestion {
  operation: string;
  label: string;
  fingerprint: string;
}

/** Asks who approves `question`: the pass, or `null` when nobody did («Cancel»). */
export type AskApproval = (question: ApprovalQuestion) => Promise<string | null>;

/** The question the dialog is open for; `null` when none is. */
export const approvalQuestion = shallowRef<ApprovalQuestion | null>(null);

let pass: string | undefined;
let open: (ApprovalQuestion & { result: Promise<unknown> }) | null = null;

/** The pass of the command being repeated after its approval, for the SDK's `getElevationToken`. */
export function approvalPass(): string | undefined {
  return pass;
}

/** The question in a refusal that a manager can lift; `null` for any other failure. */
export function questionOf(error: unknown): ApprovalQuestion | null {
  if (!(error instanceof ApiError) || error.code !== 'requires_elevation') return null;
  const approval = error.details.approval as Partial<ApprovalQuestion> | undefined;
  if (!approval || typeof approval.operation !== 'string' || typeof approval.fingerprint !== 'string') return null;
  return { operation: approval.operation, label: String(approval.label ?? ''), fingerprint: approval.fingerprint };
}

/** Runs `run` and, when a manager can lift its refusal, asks for the approval and repeats it once with the pass. */
export async function withApproval<T>(run: () => Promise<T>, { ask = askInDialog }: { ask?: AskApproval } = {}): Promise<T> {
  try {
    return await run();
  } catch (error) {
    const question = questionOf(error);
    if (question === null) throw error;
    if (open !== null) {
      if (open.operation === question.operation && open.fingerprint === question.fingerprint) return open.result as Promise<T>;
      throw error;
    }
    const result = approveAndRepeat(run, question, error, ask);
    open = { ...question, result };
    try {
      return await result;
    } finally {
      open = null;
    }
  }
}

async function approveAndRepeat<T>(run: () => Promise<T>, question: ApprovalQuestion, refusal: unknown, ask: AskApproval): Promise<T> {
  approvalQuestion.value = question;
  let token: string | null;
  try {
    token = await ask(question);
  } finally {
    approvalQuestion.value = null;
  }
  if (!token) throw refusal;
  pass = token;
  try {
    return await run();
  } finally {
    pass = undefined;
  }
}

/** The dialog «An approval is needed» over the screen, until somebody approves or it is closed. */
async function askInDialog(question: ApprovalQuestion): Promise<string | null> {
  const [{ modalController }, { default: ApprovalDialog }] = await Promise.all([
    import('@ionic/vue'),
    import('../components/ApprovalDialog.vue'),
  ]);
  const modal = await modalController.create({ component: ApprovalDialog, componentProps: { question }, cssClass: APPROVAL_DIALOG_CLASS });
  await modal.present();
  const { data, role } = await modal.onDidDismiss<string>();
  return role === APPROVED && typeof data === 'string' ? data : null;
}

/** The role the dialog closes with once somebody approved (its data: the pass). */
export const APPROVED = 'approved';

/** The dialog's own class: from a tablet up it is as tall as its whole PIN pad (ApprovalDialog.vue), never Ionic's
 *  fixed 600×600 card, which cut the pad's last row, the 0 and erase. */
export const APPROVAL_DIALOG_CLASS = 'approval-dialog-modal';
