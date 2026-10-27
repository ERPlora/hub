// BASE-F108: whether base's «Report a problem» dialog (ReportProblemDialog, beside the pane) is open. The user menu's
// entry opens it (`frontend/main.ts`, a `run` entry of `@erplora/ui/shell`); the dialog closes itself.
import { shallowRef } from 'vue';

export const reportProblemOpen = shallowRef(false);

export function openReportProblem(): void {
  reportProblemOpen.value = true;
}
