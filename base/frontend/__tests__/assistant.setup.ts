// The Hub's second Vitest setup file (`test.setupFiles` in vite.config.ts; proven by vitest.setup.test.ts): before each
// test the shared assistant of @erplora/ui is configured as main.ts configures it when the Hub boots (`HUB_ASSISTANT`),
// so a page or a component that mounts its panel, its button or a dictation finds base's routes, operations and words.
// Imported when each test starts, after the file's own imports: imported at the top, it would load base's modules and
// @erplora/ui's components before the file's `vi.mock`s apply (a mocked `IonModal` would not reach them).
import { beforeEach } from 'vitest';

import { configureAssistant } from '../../../packages/ui/src/components/Assistant/config';

beforeEach(async () => {
  const { HUB_ASSISTANT } = await import('../lib/assistant-hub');
  configureAssistant(HUB_ASSISTANT);
});
