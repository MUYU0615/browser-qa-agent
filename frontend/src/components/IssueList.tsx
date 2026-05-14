import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Issue } from '../api';

export function IssueList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) {
    return <div className="empty-state"><CheckCircle2 size={18} /> No issues yet.</div>;
  }

  return (
    <div className="issue-list">
      {issues.map((issue, index) => (
        <article className="issue-item" key={`${issue.kind}-${index}`}>
          <div className={`severity severity-${issue.severity}`}>{issue.severity}</div>
          <h3><AlertTriangle size={16} /> {issue.kind}</h3>
          <p>{issue.message}</p>
          {stepsFor(issue).length ? (
            <ol>
              {stepsFor(issue).map((step) => <li key={step}>{step}</li>)}
            </ol>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function stepsFor(issue: Issue) {
  const steps = issue.reproduction_steps;
  if (Array.isArray(steps)) return steps;
  if (typeof steps === 'string') {
    return steps.split('\n').map((step) => step.trim()).filter(Boolean);
  }
  return [];
}
