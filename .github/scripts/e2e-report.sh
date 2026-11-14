#!/usr/bin/env bash
# The report of the Hub's nightly e2e run (nightly-e2e.sh): lists what came out red, from Playwright's JSON
# report, in its output, and keeps ONE open issue about it: a red night opens it (or comments on it when it
# is already open) and the first green night closes it.
#   RESULT=<success|anything else> SHA=<commit of main> RUN_DIR=<the night's folder> [REPORT=<json report>] \
#     [STEP=<the step before the specs that failed>] PUBLISH=true|false GH_REPO=<owner/repo> bash .github/scripts/e2e-report.sh
# Every result other than `success` is red. A missing or unreadable report is said, not hidden: the night
# stopped before or outside the specs, and STEP names where when it is known. Only PUBLISH=true writes
# issues; otherwise the output is all. A gh call that fails fails the report. RUN_DIR is written from ~ (the
# Mac's user path never reaches GitHub). Optional: DAY (the night's date, default today).
# The jq programs and the markdown are single-quoted on purpose: their $ and backticks are literal (SC2016).
# shellcheck disable=SC2016
set -euo pipefail

TITLE="Pruebas de navegador del Hub en rojo en la pasada nocturna"
: "${RESULT:?}" "${SHA:?}" "${RUN_DIR:?}"
REPORT="${REPORT:-}"
STEP="${STEP:-}"
PUBLISH="${PUBLISH:-false}"
DAY="${DAY:-$(date +%F)}"
short="${SHA:0:7}"
folder="$RUN_DIR"
case "$folder" in "$HOME"/*) folder='~'/"${folder#"$HOME"/}" ;; esac
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# The red tests and the run's own errors, one markdown line each, without colour codes; the first
# line of each error, cut at 200 characters.
LINES_JQ='
def plain: gsub("\u001b\\[[0-9;]*m"; "") | split("\n")[0] | .[0:200];
def project: if (.projectName // "") == "" then "" else "[\(.projectName)] " end;
def specs($path): (.specs[]? | {path: ($path + [.title]), spec: .}),
                  (.suites[]? as $suite | $suite | specs($path + [$suite.title]));
(.suites[]? | specs([]) | .path as $path | .spec as $spec | $spec.tests[]
  | select(.status == "unexpected")
  | ((.results | last | .error.message) // "" | plain) as $error
  | "- `\(project)\($spec.file):\($spec.line)` › \($path | join(" › "))"
    + (if $error == "" then "" else " — \($error)" end)),
(.errors[]? | "- Error de la ejecución: \(.message // "" | plain)")
'
STATS_JQ='.stats | "\(.unexpected) en rojo · \(.expected) bien · \(.skipped) saltadas"'

details="$work/details.md"
if [ -n "$STEP" ]; then
  printf 'La pasada no llegó a las specs: falló «%s». Lo que dijo está en `%s/night.log`.\n' "$STEP" "$folder" > "$details"
elif [ -n "$REPORT" ] && [ -s "$REPORT" ] && jq -e . "$REPORT" > /dev/null 2>&1; then
  {
    jq -r "$STATS_JQ" "$REPORT"
    echo
    jq -r "$LINES_JQ" "$REPORT"
  } > "$details"
  if ! grep -q '^- ' "$details" && [ "$RESULT" != success ]; then
    printf '\nEl informe no tiene ninguna prueba en rojo, pero la ejecución terminó en `%s`: `%s/night.log` dice por qué.\n' \
      "$RESULT" "$folder" >> "$details"
  fi
else
  printf 'La ejecución terminó en `%s` sin informe de las pruebas: lo que falló está antes o fuera de las specs (servidores, tiempo agotado). Lo dice `%s/night.log`.\n' \
    "$RESULT" "$folder" > "$details"
fi

# The open issue of exactly that title, if any (the newest when there were two): searched by its title, never
# among the latest issues, where a busy repo would bury it and a second one would be opened.
open_issue() {
  gh issue list --state open --search "\"$TITLE\" in:title" --limit 50 --json number,title \
    | jq -r --arg title "$TITLE" '[.[] | select(.title == $title) | .number] | max // empty'
}

if [ "$RESULT" = success ]; then
  printf '## Pruebas de navegador del Hub: en verde\n\nLa pasada del %s ha salido en verde (commit `%s`).\n' "$DAY" "$short"
  if [ "$PUBLISH" = true ]; then
    number="$(open_issue)"
    if [ -n "$number" ]; then
      gh issue close "$number" --reason completed \
        --comment "La pasada del $DAY ha salido entera en verde sobre \`main\` (commit \`$short\`). Se cierra."
    fi
  fi
  exit 0
fi

printf '## Pruebas de navegador del Hub: en rojo\n\nLa pasada del %s, commit `%s`, en `%s`.\n\n' "$DAY" "$short" "$folder"
cat "$details"
if [ "$PUBLISH" != true ]; then
  printf '\nSin publicar: no se escribe ninguna issue.\n'
  exit 0
fi

body="$work/body.md"
number="$(open_issue)"
if [ -n "$number" ]; then
  {
    printf 'La pasada del %s sigue en rojo, sobre `main` (commit `%s`); su registro y sus trazas, en `%s`.\n\n' \
      "$DAY" "$short" "$folder"
    cat "$details"
  } > "$body"
  gh issue comment "$number" --body-file "$body"
  exit 0
fi

{
  cat <<EOF
## Qué pasa
Cada noche se prueban solas, en un navegador, todas las pantallas del Hub sobre la última versión, y esta noche alguna ha fallado. Puede ser un fallo real que ya está en producción o una prueba que se ha quedado vieja: hasta que alguien lo mire no se sabe.

## Propuesta
Mirar cada prueba de la lista: si el fallo es del producto, arreglarlo con su prueba; si la prueba se quedó vieja, ponerla al día. Esta issue se cierra sola la primera noche en que la pasada salga entera en verde.

## Detalle técnico
- Pasada del $DAY sobre \`main\` (commit \`$short\`), en el Mac. El registro de la noche (\`night.log\`) y las trazas y capturas de cada fallo (\`test-results/\`), en \`$folder\`.
- Una spec se repite en una pila propia (\`tests/e2e/README.md\`, «Varias ejecuciones a la vez») con \`CI=1 pnpm e2e tests/e2e/<spec>\`, o con la misma pila de la noche: \`bash .github/scripts/nightly-e2e.sh --no-publish --spec tests/e2e/<spec>\`.

EOF
  cat "$details"
  cat <<EOF

## Origen
- Cómo se llegó: la pasada nocturna de las pruebas de navegador del Hub (\`.github/scripts/nightly-e2e.sh\`, que lanza launchd en el Mac).
- Sale de #877
- La introdujo una PR: no comprobado — la pasada no sabe qué cambio la rompió; se busca entre los commits desde la última noche en verde.

## Cómo se reproduce
- Test: las specs de la lista, que fallan sobre \`origin/main@$short\` (\`CI=1 pnpm e2e tests/e2e/<spec>\` en una pila propia).

## Flujo
- Flujo: ninguno — la pasada no sabe qué flujo prueba cada spec; el triaje lo pone al leerla.
EOF
} > "$body"
gh issue create --title "$TITLE" --label prio:P1 --body-file "$body"
