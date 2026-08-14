// "Report an issue" on an assistant answer (hub#946). Required by Microsoft Store policy
// 11.16: users must be able to report inappropriate AI-generated content. The report goes
// to the hub runtime (`POST /api/assistant/report`), which forwards it for review — with
// the SAME header helper as the chat stream (`runtimeHeaders()`: the local session
// `X-Hub-Session` is the runtime's permission authority, ARQUITECTURA.md §2.9).
import { RUNTIME_URL, runtimeHeaders } from './runtime';

export interface AssistantReport {
  /** Stable id of the reported assistant message (client-generated UUID). */
  messageId: string;
  /** Full text of the reported AI answer. */
  assistantMessage: string;
  /** The closest preceding user message, if any. */
  userMessage?: string;
  /** Optional free-text comment from the report dialog. */
  comment?: string;
}

/** Sends the report to the runtime. Throws on any non-2xx response. */
export async function reportAssistantMessage(report: AssistantReport): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/assistant/report`, {
    method: 'POST',
    headers: {
      ...runtimeHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message_id: report.messageId,
      assistant_message: report.assistantMessage,
      user_message: report.userMessage ?? '',
      comment: report.comment ?? '',
    }),
  });
  if (!res.ok) {
    throw new Error(`assistant report → ${res.status}`);
  }
}
