// The hub setup (vitest.setup.ts) mocks `@ionic/vue` with it for every test; a file that mocks `@ionic/vue` for
// another reason builds on it, as `ionicWithApprovalDialog` does.
/** The shared Ionic modal stub factory, dynamically imported by a test's hoisted `vi.mock` callback. */
export async function mockIonicModal(importOriginal: () => Promise<typeof import('@ionic/vue')>) {
  const { ionicVueWithModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return ionicVueWithModalStub(importOriginal);
}
