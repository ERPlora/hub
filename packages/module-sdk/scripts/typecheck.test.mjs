// Contract test: the `@erplora/module-sdk` test files go through the TypeScript compiler.
//
// Regression test for ERPlora/hub#2086.
//
// WHY THIS EXISTS. The SDK suite runs with `node --experimental-transform-types`, which STRIPS the
// types instead of checking them, and `contract:check` only compares `src/index.ts` with its
// committed `.d.ts`. So a test that only asserts a type — «a recipe grant announces its `reason`»
// (hub#2069) — stayed green when the field vanished from the code AND from the contract at once:
// measured in the review of hub#2083, 228/228 green and `contract:check` exit 0. Only `tsc` over
// the test file noticed. This guard makes that `tsc` part of `pnpm verify` and proves it bites.
// It lives in the package and runs with its `test` script, so `packages/**` already triggers it.

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
    cpSync,
    mkdtempSync,
    readFileSync,
    rmSync,
    symlinkSync,
    writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const sdkDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(sdkDir, "..", "..");

function readJson(file) {
    return JSON.parse(readFileSync(file, "utf8"));
}

/** A throwaway copy of the SDK package (sharing its `node_modules`), removed after `fn`. */
function withSdkCopy(fn) {
    const dir = mkdtempSync(path.join(tmpdir(), "erplora-sdk-typecheck-"));
    try {
        cpSync(path.join(sdkDir, "src"), path.join(dir, "src"), { recursive: true });
        cpSync(path.join(sdkDir, "scripts"), path.join(dir, "scripts"), { recursive: true });
        cpSync(path.join(sdkDir, "package.json"), path.join(dir, "package.json"));
        symlinkSync(path.join(sdkDir, "node_modules"), path.join(dir, "node_modules"), "dir");
        return fn(dir);
    } finally {
        rmSync(dir, { recursive: true, force: true });
    }
}

/** Runs the package's `typecheck` entry point inside `dir`; returns { status, output }. */
function typecheck(dir) {
    const script = readJson(path.join(dir, "package.json")).scripts?.typecheck;
    assert.ok(script, "@erplora/module-sdk must declare a `typecheck` script");
    const run = spawnSync(script, { cwd: dir, shell: true, encoding: "utf8" });
    return { status: run.status, output: `${run.stdout}${run.stderr}` };
}

test("the root `verify` type-checks the module-sdk tests (hub#2086)", () => {
    const verify = readJson(path.join(repoRoot, "package.json")).scripts?.verify ?? "";
    assert.match(
        verify,
        /pnpm (-F|--filter) @erplora\/module-sdk typecheck\b/,
        "`pnpm verify` is what CI and the pre-push gate run; without the typecheck in it, a test " +
            "that only asserts a type stays green when the type disappears",
    );
});

test("module-sdk typecheck is clean on the real sources (hub#2086)", () => {
    const { status, output } = withSdkCopy(typecheck);
    assert.equal(status, 0, `typecheck must pass on the committed sources:\n${output}`);
});

test("a type removed from the SDK turns its type-only test red (hub#2086)", () => {
    // The exact mutant of hub#2086: drop the recipe grant's `reason` (hub#2069) from the code.
    // `flows.test.ts` only asserts it through the type, so nothing but `tsc` can notice.
    const { status, output } = withSdkCopy((dir) => {
        const index = path.join(dir, "src", "index.ts");
        const source = readFileSync(index, "utf8");
        const field = "    reason?: Record<string, string>;\n";
        assert.ok(source.includes(field), "the mutant's anchor moved: update this test");
        writeFileSync(index, source.replace(field, ""));
        return typecheck(dir);
    });
    assert.notEqual(status, 0, "removing `reason` must fail the typecheck");
    assert.match(output, /src\/flows\.test\.ts\(\d+,\d+\): error TS/);
});

test("a brand-new test file is type-checked too, not only the ones listed today (hub#2086)", () => {
    const { status, output } = withSdkCopy((dir) => {
        writeFileSync(
            path.join(dir, "src", "zz-probe.test.ts"),
            "import type { PlatformFailure } from './index.ts';\n" +
                "export const probe: PlatformFailure = { code: 'other', not_a_field: 1 };\n",
        );
        return typecheck(dir);
    });
    assert.notEqual(status, 0, "a test file added tomorrow must be covered by the same typecheck");
    assert.match(output, /src\/zz-probe\.test\.ts\(\d+,\d+\): error TS2353/);
});
