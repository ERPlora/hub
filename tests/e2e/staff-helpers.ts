// What the e2e of Staff share: how a spec takes away the people, schedules, time off and roles it made.
import { psql } from './helpers';

/** Deletes the people whose first name starts with `tag` (with their schedules and time off) and the roles named so. */
export function staffCleanUp(tag: string): void {
  const members = `select id from staff_member where first_name like '${tag}%'`;
  psql(
    [
      `delete from staff_timeoff where member_id in (${members})`,
      `delete from staff_scheduleday where schedule_id in (select id from staff_schedule where member_id in (${members}))`,
      `delete from staff_schedule where member_id in (${members})`,
      `delete from staff_member where first_name like '${tag}%'`,
      `delete from staff_role where name like '${tag}%'`,
    ].join('; '),
  );
}
