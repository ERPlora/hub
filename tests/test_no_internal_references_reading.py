"""What the scan reads of each kind of file and how it names what it finds."""

from test_no_internal_references import SECTION_SIGN, found_lines, internal_references, is_code


def test_an_end_to_end_spec_keeps_its_capture_keys_but_not_its_comments(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    lines = (
        "// The flows of the people (@TASK) at three sizes",
        "const KEY = '@FIX';",
        'const atEverySize = captureAtEverySize("@TASK");',
        "await capture(page, `@TASK-${key}-${vp.label}`);",
        " * a capture `@TASK-<key>-<size>` stays for the eye",
        "test('@FIX: the panel opens', async ({ page }) => {",
        "test.describe(`@TASK review`, () => {",
        "await go('http://localhost/'); // the @PHASE page",
        "await shot('a'); // it's @FIX, isn't it",
    )
    text = "\n".join(lines).replace("@TASK", "APP" + "-BASE-9").replace("@FIX", "FIX" + "-HUB-SOME-KEY")
    spec.write_text(text.replace("@PHASE", "fase" + " 2") + "\n", encoding="utf-8")
    found = internal_references(["tests/e2e/some.spec.ts"], root=tmp_path)
    assert [line.split(":")[1] for line in found] == ["1", "5", "6", "7", "8", "9"]


def test_outside_the_end_to_end_specs_a_string_literal_is_read_too(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "keys.ts").write_text("const KEY = 'FIX" + "-HUB-SOME-KEY';\n", encoding="utf-8")
    (tmp_path / "tests" / "e2e").mkdir(parents=True)
    (tmp_path / "tests" / "e2e" / "seed.py").write_text('"""The seed (APP' + '-BASE-2)."""\n', encoding="utf-8")
    found = internal_references(["base/keys.ts", "tests/e2e/seed.py"], root=tmp_path)
    assert [line.split(":")[0] for line in found] == ["base/keys.ts", "tests/e2e/seed.py"]


def test_a_patch_comment_that_points_at_a_plan_is_caught(tmp_path):
    patch = "patches/@scope__package@1.0.0.patch"
    (tmp_path / "patches").mkdir()
    comment = "+         * ERPlora patch: the queue of PLAN-HUB " + SECTION_SIGN + "84."
    (tmp_path / patch).write_text("+        /**\n" + comment + "\n+         */\n", encoding="utf-8")
    assert is_code(patch)
    assert internal_references([patch], root=tmp_path) == [f"{patch}:2: {comment}"]


def test_each_reference_is_named_by_file_and_line(tmp_path):
    (tmp_path / "clean.py").write_text("total = round(amount, 2)\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python\n# see PLAN " + SECTION_SIGN + "3\n", encoding="utf-8")
    assert internal_references(["clean.py", "Dockerfile"], root=tmp_path) == [
        "Dockerfile:2: # see PLAN " + SECTION_SIGN + "3"
    ]


def test_a_task_id_with_an_underscore_is_caught_in_a_spec_comment_but_not_in_its_capture_key(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    task = "FIX" + "-CASH_REGISTER-SETUP-HOOKS"
    lines = (
        f"// Cash register's hooks of the Home ({task}).",
        f"const KEY = '{task}';",
        f"await capture(page, `{task}-CASH_REGISTER-F01-${{vp.label}}`);",
        "test('CASH_REGISTER-F01: the cash panel opens', async ({ page }) => {});",
    )
    spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["tests/e2e/some.spec.ts"], root=tmp_path)) == [1]


def test_an_end_to_end_title_reads_the_constant_it_interpolates(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    task = "FIX" + "-HUB-SOME-KEY"
    lines = (
        f"const KEY = '{task}';",
        "const ENTRIES = 21;",
        "const PLACE = 'Terrace A';",
        "test(`${KEY}: the panel opens`, async ({ page }) => {",
        "  await capture(page, `${KEY}-${size.label}`);",
        "});",
        "test(`${ENTRIES} entries at ${PLACE}: one jump at most`, async () => {});",
        "test(`at ${size.label}: the panel opens`, async () => {});",
        "test.describe(`${KEY} at three sizes`, () => {});",
        "test(",
        "  `${KEY}: the panel closes`,",
        "  async () => {},",
        ");",
        "/** The screen in the three sizes (`${KEY}-<size>`). */",
    )
    spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["tests/e2e/some.spec.ts"], root=tmp_path)) == [4, 9, 11]
