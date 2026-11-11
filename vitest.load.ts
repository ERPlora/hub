// The time budgets of the hub's Vitest run follow the machine's load (hub#765). On a loaded Mac a test that reads
// files, imports a module cold or starts a process runs many times slower than idle — Microsoft Defender's endpoint
// extension authorises each open and stat, and with every core busy it barely gets the CPU to: measured at load ~80
// over 15 cores, CPU work ran 10 times slower and walking the hub's sources 170 times — and fell red at Vitest's fixed
// 5 s with nothing broken. vite.config.ts reads the scale once, when the run starts, and stretches the test, hook and
// `expect.poll` budgets by it; vitest.setup.ts stretches `vi.waitFor`'s. A test that really hangs still fails, by
// its stretched budget (vitest.setup.test.ts proves it).
import { availableParallelism, loadavg } from 'node:os';

declare module 'vitest' {
  export interface ProvidedContext {
    /** How many times slower than idle the machine ran when the run started (`loadScale`), for the setup. */
    loadScale: number;
  }
}

/** `vi.waitFor`'s own budget when a test names none. */
const WAIT_FOR_TIMEOUT = 1_000;

type WaitForOptions = number | { timeout?: number; interval?: number } | undefined;

/** How many times slower than idle the machine runs a test now: 1 while its load (the busier of the last minute and
 *  the last five: a run lasts minutes) stays at half its cores or less, and twice the load per core above that —
 *  the CPU slowdown measured at load ~80 over 15 cores. Reading files slows more than that, and the margin of each
 *  budget over what its test takes idle covers it. 1 when the machine reports no load (Windows) or no number. */
export function loadScale(load: readonly number[] = loadavg(), cores: number = availableParallelism()): number {
  const scale = (2 * Math.max(load[0] ?? 0, load[1] ?? 0)) / cores;
  return Number.isFinite(scale) && scale > 1 ? scale : 1;
}

/** The options of a `vi.waitFor` with its budget, its own or the default second, stretched by `scale`. */
export function scaleWaitFor(options: WaitForOptions, scale: number): WaitForOptions {
  if (typeof options === 'number') return Math.round(options * scale);
  return { ...options, timeout: Math.round((options?.timeout ?? WAIT_FOR_TIMEOUT) * scale) };
}
