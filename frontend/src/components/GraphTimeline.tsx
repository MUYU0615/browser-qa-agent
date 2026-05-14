import { CheckCircle2, Circle, Loader2, RotateCcw } from 'lucide-react';
import { RunStatus } from '../api';

const nodes = [
  'page_analyzer',
  'test_planner',
  'browser_executor',
  'observation_analyzer',
  'bug_classifier',
  'retry_planner',
  'reporter'
];

export function GraphTimeline({ currentNode, status }: { currentNode: string; status: RunStatus }) {
  const currentIndex = nodes.indexOf(currentNode);
  return (
    <div className="graph-list">
      {nodes.map((node, index) => {
        const active = node === currentNode;
        const completed = status === 'completed' || (currentIndex > -1 && index < currentIndex);
        const retry = node === 'retry_planner';
        return (
          <div className={`graph-node ${active ? 'active' : ''} ${completed ? 'complete' : ''}`} key={node}>
            <div className="node-icon">
              {active ? <Loader2 className="spin" size={18} /> : completed ? <CheckCircle2 size={18} /> : retry ? <RotateCcw size={18} /> : <Circle size={18} />}
            </div>
            <div>
              <strong>{node}</strong>
              <small>{describe(node)}</small>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function describe(node: string) {
  const labels: Record<string, string> = {
    page_analyzer: 'Inspect DOM, title, page signals',
    test_planner: 'Ask DeepSeek for safe QA steps',
    browser_executor: 'Run Playwright actions',
    observation_analyzer: 'Normalize raw observations',
    bug_classifier: 'Classify issues and severity',
    retry_planner: 'Retry safe subset if needed',
    reporter: 'Write Markdown report'
  };
  return labels[node] ?? node;
}
