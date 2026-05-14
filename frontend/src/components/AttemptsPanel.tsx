import { CheckCircle2, CircleSlash, RotateCcw } from 'lucide-react';
import { Attempt } from '../api';

export function AttemptsPanel({ attempts }: { attempts: Attempt[] }) {
  if (attempts.length === 0) {
    return <div className="empty-state"><RotateCcw size={18} /> 浏览器执行开始后会显示尝试记录。</div>;
  }

  return (
    <div className="attempt-list">
      {attempts.map((attempt) => (
        <article className="attempt-item" key={`${attempt.attempt}-${attempt.phase}`}>
          <header>
            <h3>尝试 {attempt.attempt}</h3>
            <span>{phaseLabel(attempt.phase)}</span>
          </header>

          <section>
            <h4>步骤</h4>
            <ol>
              {attempt.test_steps.map((step, index) => (
                <li key={`${attempt.attempt}-step-${index}`}>{String(step.description ?? step.action ?? '步骤')}</li>
              ))}
            </ol>
          </section>

          <section>
            <h4>结果</h4>
            <div className="attempt-results">
              {attempt.execution_results.map((result, index) => (
                <div className={`attempt-result ${result.ok ? 'pass' : 'fail'}`} key={`${attempt.attempt}-result-${index}`}>
                  {result.ok ? <CheckCircle2 size={16} /> : <CircleSlash size={16} />}
                  <span>{result.description ?? result.action ?? '步骤'}</span>
                  {result.error ? <small>{result.error}</small> : null}
                </div>
              ))}
            </div>
          </section>

          <section className="attempt-signals">
            <span>控制台错误：{attempt.console_errors.length}</span>
            <span>网络错误：{attempt.network_errors.length}</span>
            <span>截图：{attempt.screenshots.length}</span>
          </section>
        </article>
      ))}
    </div>
  );
}

function phaseLabel(phase: string) {
  const labels: Record<string, string> = {
    initial: '初始',
    retry: '重试',
    scenario: '场景'
  };
  return labels[phase] ?? phase;
}
