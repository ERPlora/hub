// Whether a scenario (assistant-scenario.ts) can be asked at all, by rules that are the same for every model, so a
// product defect or a model's missing sense is reported apart from the model's failures: the opening message, with its
// files, must be offered the tools of the job (the turn ranks the tools by the person's words), and a photo only reaches
// a model that sees images. Also the guard every scenario ends with: no fiscal record ever left the business. Pure, so Vitest
// proves it (assistant-precheck.test.ts).
import type { AttachedFile } from './assistant-fixtures.ts';
import type { Scenario } from './assistant-scenario.ts';
import { hubShellCommand, type ShellCommand } from './assistant-setup.ts';

export type ContentPart =
  | { type: 'text'; text: string }
  | { type: 'input_file'; filename: string; mime_type: string; data: string }
  | { type: 'image_url'; image_url: { url: string } };

/** The opening message's content as the chat sends it (`contentOf` and `forGateway` of @erplora/ui's Assistant). */
export function openingContent(text: string, files: AttachedFile[]): string | ContentPart[] {
  if (!files.length) return text;
  const parts: ContentPart[] = text ? [{ type: 'text', text }] : [];
  for (const file of files) {
    const data = file.buffer.toString('base64');
    if (file.mimeType.startsWith('image/')) parts.push({ type: 'image_url', image_url: { url: `data:${file.mimeType};base64,${data}` } });
    else parts.push({ type: 'input_file', filename: file.name, mime_type: file.mimeType, data });
  }
  return parts;
}

/** Why the scenario is not asked (null: it is): the tools its opening message (with its files) was not offered, or a
 *  photo the model cannot see. `offered` is null when the scenario names no tool its opening needs. */
export function notRunnable(scenario: Scenario, offered: string[] | null, vision: boolean): string | null {
  const missing = offered ? scenario.offered.filter((tool) => !offered.includes(tool)) : [];
  if (missing.length) return `not runnable: tools not offered on the ${scenario.attachments.length ? 'attached' : 'opening'} message (${missing.join(', ')})`;
  if (scenario.attachments.some((file) => file.kind === 'photo') && !vision) return 'not runnable: the model does not see images';
  return null;
}

/**
 * The Hub's side (`manage.py shell --hub a -c`): the tools the assistant's own turn offers the opening message of
 * `QA_OPENING_FILE` (its content, files included, as the chat sends it), asked as the owner of `a` in the scenario's
 * language with nothing pending: what the model would be given on the first round. Prints one line of JSON.
 */
export const OFFERED_TURN_PY = `
import json, os
from base.models import Membership
from base.permissions import permissions_for
from base.schemas.assistant import AssistantTurnIn
from live.context import OperationContext, Scope
from live.operations import get as get_operation

scope = Scope("host", "a")
member = Membership.objects.filter(host="a", role=Membership.Role.OWNER).select_related("user").first()
if member is None:
    raise SystemExit("the precheck runs as the owner of a, who has not signed in to it yet")
owner = member.user
ctx = OperationContext(scope=scope, actor=owner, permissions=permissions_for(owner, scope), language=os.environ["QA_OPENING_LANGUAGE"])
with open(os.environ["QA_OPENING_FILE"], encoding="utf-8") as handle:
    content = json.load(handle)
answer = get_operation("base.assistant.turn")(ctx, AssistantTurnIn.model_validate({"messages": [{"role": "user", "content": content}]}))
print(json.dumps([tool["name"] for tool in answer.model_dump(mode="json")["tools"]]))
`;

/** How the precheck runs from the Hub's checkout, the opening's content in `file`. */
export const offeredTurnCommand = (opening: { file: string; language: string }, env: Record<string, string | undefined>): ShellCommand =>
  hubShellCommand(OFFERED_TURN_PY, env, { QA_OPENING_FILE: opening.file, QA_OPENING_LANGUAGE: opening.language });

/** The offered tools by operation name, from the shell's last line. */
export function parseOfferedTurn(output: string): string[] {
  const names = JSON.parse(output.trim().split('\n').at(-1) ?? '[]') as string[];
  return names.map((name) => name.split('__').join('.'));
}

/** The fiscal records that ever left the business for the tax agency, or that it answered: always 0 in a scenario run. */
export const SENT_SQL = "select count(*) from verifactu_record where transmitted_at is not null or coalesce(csv, '') <> ''";
