import type { LiveClient } from '@erplora/ui/sdk';

import type { AppHelp, HelpFlow, HelpScreen } from '../operations-help';

declare module 'vue-router' {
  interface RouteMeta {
    /** A screen of the Hub itself with help of its own (`base/platform_screens.py`). */
    help?: boolean;
  }
}

/** The app whose help is the one of the Hub's own screens, and the name it goes by until it is read. */
export const PLATFORM = 'base';
export const PLATFORM_NAME = 'ERPlora';

export interface HelpFlowGroup {
  screen: HelpScreen;
  flows: HelpFlow[];
}

/** What the window's content takes and hands on to its list of tasks: the help, the tab in view and the module's icon. */
export interface HelpViewProps {
  help: AppHelp;
  current?: HelpScreen;
  icon: string;
}

/** What both report: the title of the task last opened and the screen a link of the help goes to. */
export interface HelpViewEmits {
  expand: [title: string];
  go: [path: string];
}

const normalizedPath = (path: string): string => (path === '/' ? path : path.replace(/\/+$/, ''));

export function resolveScreen(screens: HelpScreen[], routePath: string): HelpScreen | undefined {
  const path = normalizedPath(routePath);
  return screens
    .filter((screen) => {
      const prefix = normalizedPath(screen.path);
      return path === prefix || path.startsWith(`${prefix}/`);
    })
    .sort((one, other) => other.path.length - one.path.length)[0];
}

/** The Hub's own screen in view: `pattern` is its route with the parameters unread. A hash that names no tab of the page
 *  opens the page's first tab, as the page itself does. */
export function resolvePlatformScreen(screens: HelpScreen[], pattern: string, hash: string): HelpScreen | undefined {
  const tabs = screens.filter((screen) => screen.path.split('#')[0] === pattern);
  return tabs.find((screen) => screen.path === `${pattern}${hash}`) ?? tabs[0];
}

const folded = (text: string): string =>
  text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase();

export function flowMatches(flow: HelpFlow, query: string): boolean {
  const needle = folded(query.trim());
  return !needle || folded(`${flow.title}\n${flow.steps}`).includes(needle);
}

const UNLISTED_SCREEN: HelpScreen = { id: 'unlisted', title: '', path: '', text: '' };

export function organizeFlows(help: AppHelp, currentId: string | undefined, query: string): HelpFlowGroup[] {
  const ordered = [...help.screens].sort((one) => (one.id === currentId ? -1 : 0));
  const groups = ordered.flatMap((screen) => {
    const flows = help.flows.filter((flow) => flow.screens.includes(screen.id) && flowMatches(flow, query));
    return flows.length ? [{ screen, flows }] : [];
  });
  const listed = new Set(help.screens.map((screen) => screen.id));
  const unlisted = help.flows.filter(
    (flow) => flow.screens.every((id) => !listed.has(id)) && flowMatches(flow, query),
  );
  return unlisted.length ? [...groups, { screen: UNLISTED_SCREEN, flows: unlisted }] : groups;
}

const cache = new Map<string, AppHelp>();

export function resetHelpCache(): void {
  cache.clear();
}

export function createHelpStore(client: LiveClient) {
  async function read(app: string, language: string): Promise<AppHelp> {
    const key = `${app}\0${language}`;
    const cached = cache.get(key);
    if (cached) return cached;
    const answer = await client.api.call('base.help.get', { app });
    cache.set(key, answer);
    return answer;
  }

  return { read };
}

export interface QuestionContext {
  flow?: string;
  app: string;
  screen: string;
}

export function assistantQuestion(
  context: QuestionContext,
  templates: { flow: string; screen: string },
): string {
  if (context.flow) return templates.flow.replace('{title}', context.flow);
  return templates.screen.replace('{app}', context.app).replace('{screen}', context.screen);
}

let lastHelpQuestion = '';

export function writeAssistantQuestion(draft: string, question: string): string {
  const current = draft.trimEnd();
  const unedited = lastHelpQuestion.length > 0
    && (current === lastHelpQuestion || current.endsWith(`\n\n${lastHelpQuestion}`));
  const base = unedited ? current.slice(0, -lastHelpQuestion.length).trimEnd() : current;
  lastHelpQuestion = question;
  return base.trim() ? `${base}\n\n${question}` : question;
}
