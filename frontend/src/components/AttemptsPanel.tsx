import { CheckCircle2, CircleSlash, RotateCcw } from 'lucide-react';
import { Attempt } from '../api';

export function AttemptsPanel({ attempts }: { attempts: Attempt[] }) {
  if (attempts.length === 0) {
    return <div className="empty-state"><RotateCcw size={18} /> Attempts will appear after browser execution starts.</div>;
  }

  return (
    <div className="attempt-list">
      {attempts.map((attempt) => (
        <article className="attempt-item" key={`${attempt.attempt}-${attempt.phase}`}>
          <header>
            <h3>Attempt {attempt.attempt}</h3>
            <span>{attempt.phase}</span>
          </header>

          <section>
            <h4>Steps</h4>
            <ol>
              {attempt.test_steps.map((step, index) => (
                <li key={`${attempt.attempt}-step-${index}`}>{String(step.description ?? step.action ?? 'Step')}</li>
              ))}
            </ol>
          </section>

          <section>
            <h4>Results</h4>
            <div className="attempt-results">
              {attempt.execution_results.map((result, index) => (
                <div className={`attempt-result ${result.ok ? 'pass' : 'fail'}`} key={`${attempt.attempt}-result-${index}`}>
                  {result.ok ? <CheckCircle2 size={16} /> : <CircleSlash size={16} />}
                  <span>{result.description ?? result.action ?? 'Step'}</span>
                  {result.error ? <small>{result.error}</small> : null}
                </div>
              ))}
            </div>
          </section>

          <section className="attempt-signals">
            <span>Console errors: {attempt.console_errors.length}</span>
            <span>Network errors: {attempt.network_errors.length}</span>
            <span>Screenshots: {attempt.screenshots.length}</span>
          </section>
        </article>
      ))}
    </div>
  );
}
