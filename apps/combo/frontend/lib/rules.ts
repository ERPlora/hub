// The sentence that states the rule the till applies to a course (WORKBOOK «Constructor del menú»):
// «Compulsory · pick 1 · up to 1 · no repeats». The obligation IS the minimum (1 or more): there is no
// separate switch, so an optional course never turns compulsory by accident (Square's footgun).
import type { GroupOut } from '../operations';

type Translate = (key: string, named?: Record<string, unknown>) => string;

export function courseRule(course: Pick<GroupOut, 'min_choices' | 'max_choices' | 'allow_repeat'>, t: Translate): string {
  const min = course.min_choices;
  const max = course.max_choices;
  const parts: string[] = [];
  if (min >= 1) parts.push(max === min ? t('combo.rule.required', { min }) : t('combo.rule.requiredRange', { min }));
  else parts.push(t('combo.rule.optional'));
  parts.push(max === 0 ? t('combo.rule.noCeiling') : t('combo.rule.max', { max }));
  parts.push(course.allow_repeat ? t('combo.rule.repeat') : t('combo.rule.noRepeat'));
  return parts.join(' · ');
}
