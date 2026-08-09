import { formatRelativeTime } from "../lib/relativeTime";

export function RelativeTime({ date }: { date: string }) {
  return (
    <time dateTime={date} title={new Date(date).toLocaleString()}>
      {formatRelativeTime(date)}
    </time>
  );
}
