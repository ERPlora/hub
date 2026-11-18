/** The shared Ionic modal stub factory, dynamically imported by a test's hoisted `vi.mock` callback. */
export async function mockIonicModal(importOriginal: () => Promise<typeof import('@ionic/vue')>) {
  const { ionicVueWithModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return ionicVueWithModalStub(importOriginal);
}
