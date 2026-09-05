// Free-port probe for the e2e bench (ERPlora/hub#1517) — run as a CHILD PROCESS on purpose.
//
// Playwright loads `playwright.config.ts` SYNCHRONOUSLY: `loadUserConfig` in
// `playwright/lib/common/index.js` does `object = object["default"]` with no `await`, so a config
// that resolves its ports with a Promise hands Playwright a pending Promise instead of a config.
// Binding a socket is asynchronous in Node, so the only way to answer "which ports are free?"
// synchronously is to ask another process and block on it (`execFileSync` in `bench-ports.ts`).
//
// Usage: node free-port-probe.mjs <first> <last> <start> <count> [excluded...]
// Sweeps upward from <start>, wrapping inside [<first>, <last>], and prints <count> free ports one
// per line. Ports found are HELD OPEN until the whole set is collected, so the set is free at ONE
// instant rather than each port at a different one; the sweep itself never revisits a port.
import { createServer } from 'node:net';

const [first, last, start, count] = process.argv.slice(2, 6).map(Number);
const excluded = new Set(process.argv.slice(6).map(Number));

for (const [name, value] of [
  ['first', first],
  ['last', last],
  ['start', start],
  ['count', count],
]) {
  if (!Number.isInteger(value)) {
    process.stderr.write(`free-port-probe: <${name}> must be an integer, got ${String(value)}\n`);
    process.exit(2);
  }
}
if (first > last || start < first || start > last || count < 1) {
  process.stderr.write(
    `free-port-probe: bad window — first=${first} last=${last} start=${start} count=${count}\n`,
  );
  process.exit(2);
}

/** Resolves to a LISTENING server on `port`, or to null when the port is taken. */
function tryListen(port) {
  return new Promise((resolve) => {
    const server = createServer();
    // Any bind error (EADDRINUSE, EACCES on a privileged port) means "not ours": move on.
    server.once('error', () => resolve(null));
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

const span = last - first + 1;
const held = [];
const ports = [];

for (let step = 0; step < span && ports.length < count; step += 1) {
  const port = first + ((start - first + step) % span);
  if (excluded.has(port)) continue;
  const server = await tryListen(port);
  if (server === null) continue;
  held.push(server);
  ports.push(port);
}

// Release before printing: the caller binds these itself, and a probe still holding them would
// hand back ports that are busy the moment they are used.
await Promise.all(held.map((server) => new Promise((done) => server.close(done))));

if (ports.length < count) {
  process.stderr.write(
    `free-port-probe: only ${ports.length} of ${count} ports free in ${first}-${last}\n`,
  );
  process.exit(1);
}

process.stdout.write(`${ports.join('\n')}\n`);
