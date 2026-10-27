// BASE-F108: the user menu's «Report a problem» opens base's dialog (ReportProblemDialog, beside the pane) without
// leaving the hub; the menu's entry only asks for it, the dialog closes itself.
import { afterEach, describe, expect, it } from 'vitest';

import { openReportProblem, reportProblemOpen } from './report-problem';

afterEach(() => {
  reportProblemOpen.value = false;
});

describe('report-problem', () => {
  it('is closed until the user menu asks for it', () => {
    expect(reportProblemOpen.value).toBe(false);
    openReportProblem();
    expect(reportProblemOpen.value).toBe(true);
  });
});
