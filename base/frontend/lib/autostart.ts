// «Start on login» of the computer app (ERPlora/app HUB_APP-F27): the print queue lives in the hub and this device
// drains it, so a dedicated till that opens ERPlora with the session always has somewhere to print. The operating
// system keeps the setting (a LaunchAgent, a registry key, an autostart file) and the app relays it: the Hub keeps
// nothing and always shows what the system answered, never what was asked.
//
// The reading is also what says whether the setting exists: a browser has no app, Android's refuses the command on
// purpose and an app older than the command does not have it. The three mean «no setting», never «off».
import { nativeBridge } from '@erplora/ui/shell';

const READ = 'autostart_is_enabled';
const ENABLE = 'autostart_enable';
const DISABLE = 'autostart_disable';

/** What the operating system says now, or `null` where the setting does not exist. */
export async function readAutostart(win: object = window): Promise<boolean | null> {
  const bridge = nativeBridge(win);
  if (!bridge) return null;
  try {
    const enabled = await bridge.invoke(READ);
    return typeof enabled === 'boolean' ? enabled : null;
  } catch {
    return null;
  }
}

/** Turns it on or off and answers what the system reads back; rejects with the app's refusal. */
export async function switchAutostart(enabled: boolean, win: object = window): Promise<boolean> {
  const bridge = nativeBridge(win);
  if (!bridge) throw new Error('autostart: no installed app');
  const command = enabled ? ENABLE : DISABLE;
  const answer = await bridge.invoke(command);
  if (typeof answer !== 'boolean') throw new Error(`autostart: ${command} answered ${String(answer)}`);
  return answer;
}
