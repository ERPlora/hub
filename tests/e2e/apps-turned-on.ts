// What a spec file turned on in a business, so that its `afterAll` turns off that and nothing else (hub#480). Plain
// bookkeeping, without Playwright: helpers.ts drives it with Apps' own commands (`turnOnMissing`, `turnOffTurnedOn`).

/** Turns on, one by one and in their order, the apps of `needed` that `on` does not list, and appends each to
 *  `turnedOn` once `turnOn` came back: an app whose turning on failed is not recorded, and neither is one that was
 *  already on. */
export async function turnOnRecording(
  needed: readonly string[],
  on: ReadonlySet<string>,
  turnOn: (app: string) => Promise<void>,
  turnedOn: string[],
): Promise<void> {
  for (const app of needed.filter((id) => !on.has(id))) {
    await turnOn(app);
    turnedOn.push(app);
  }
}

/** Turns off what `turnedOn` recorded, last first (an app before what it needs), and drops each from the record once
 *  `turnOff` came back: an empty record turns nothing off, and one that could not be turned off stays recorded with
 *  those before it. */
export async function turnOffRecorded(turnedOn: string[], turnOff: (app: string) => Promise<void>): Promise<void> {
  while (turnedOn.length > 0) {
    await turnOff(turnedOn[turnedOn.length - 1]);
    turnedOn.pop();
  }
}
