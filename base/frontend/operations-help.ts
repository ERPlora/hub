// Types of `base.help.get` for the SDK (`useLive`, `client.api.call`): the help window of a module. Written by hand, as
// the rest of base's (`operations/`); keep it in step with base/schemas/app_help.py and
// `frontend/generated/operations.json`. Every text is markdown for the assistant's markdown tree.

/** `base.HelpScreenOut`: one tab of the module (its menu entry); `text`, the summary of its WORKBOOK section. */
export interface HelpScreen {
  id: string;
  title: string;
  path: string;
  text: string;
}

/** `base.HelpFlowOut`: how a task is done; `screens` are the ids of the tabs it happens on. */
export interface HelpFlow {
  id: string;
  title: string;
  screens: string[];
  steps: string;
  failure: string;
  /** The YouTube video ids of the task's short videos, none when it has no videos. */
  videos: string[];
}

/** `base.AppHelpOut`: in `language`, the person's own or else the WORKBOOK's source language. */
export interface AppHelp {
  app: string;
  name: string;
  language: string;
  /** The module's YouTube video id, when it has one. */
  video: string | null;
  purpose: string;
  screens: HelpScreen[];
  flows: HelpFlow[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.help.get': { input: { app: string }; output: AppHelp };
  }
}
