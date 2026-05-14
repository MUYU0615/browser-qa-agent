import { RunEvent } from '../api';

export function EventLog({ events }: { events: RunEvent[] }) {
  if (events.length === 0) {
    return <div className="empty-state">No events yet.</div>;
  }
  return (
    <ol className="event-log">
      {events.slice().reverse().map((event) => (
        <li key={`${event.at}-${event.node}-${event.message}`}>
          <time>{new Date(event.at).toLocaleTimeString()}</time>
          <strong>{event.node}</strong>
          <span>{event.message}</span>
        </li>
      ))}
    </ol>
  );
}
