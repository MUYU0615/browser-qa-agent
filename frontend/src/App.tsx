import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Activity, Bot, Bug, FileText, Globe, ListChecks, Loader2, Play, Terminal, Workflow } from 'lucide-react';
import { createRun, getReport, getRun, Run } from './api';
import { EventLog } from './components/EventLog';
import { GraphTimeline } from './components/GraphTimeline';
import { IssueList } from './components/IssueList';
import { ReportPanel } from './components/ReportPanel';
import { ScreenshotGallery } from './components/ScreenshotGallery';
import { LlmCallPanel } from './components/LlmCallPanel';
import { AttemptsPanel } from './components/AttemptsPanel';

const terminalStatuses = new Set(['completed', 'failed']);

export default function App() {
  const [url, setUrl] = useState('http://localhost:3000');
  const [run, setRun] = useState<Run | null>(null);
  const [report, setReport] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const runStatusLabel = useMemo(() => {
    if (!run) return 'No run';
    return `${run.status} / ${run.current_node}`;
  }, [run]);

  useEffect(() => {
    if (!run || terminalStatuses.has(run.status)) return;
    const timer = window.setInterval(async () => {
      const next = await getRun(run.id);
      setRun(next);
      if (next.report_path) {
        setReport(await getReport(next.id));
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [run]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setReport('');
    try {
      const created = await createRun(url);
      setRun(created);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function refreshReport() {
    if (!run) return;
    setReport(await getReport(run.id));
    setRun(await getRun(run.id));
  }

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <div className="eyebrow"><Workflow size={16} /> LangGraph Browser QA</div>
          <h1>Browser QA Agent</h1>
        </div>
        <div className={`status-pill status-${run?.status ?? 'idle'}`}>
          {run?.status === 'running' ? <Loader2 className="spin" size={16} /> : <Activity size={16} />}
          {runStatusLabel}
        </div>
      </section>

      <section className="control-band">
        <form className="url-form" onSubmit={onSubmit}>
          <label htmlFor="target-url"><Globe size={16} /> Target URL</label>
          <input id="target-url" value={url} onChange={(event) => setUrl(event.target.value)} />
          <button type="submit" disabled={busy || !url}>
            {busy ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            Start QA Run
          </button>
        </form>
        {error && <div className="error-line">{error}</div>}
      </section>

      <section className="dashboard-grid">
        <div className="panel graph-panel">
          <PanelTitle icon={<Workflow size={18} />} title="Graph Execution" />
          <GraphTimeline currentNode={run?.current_node ?? 'queued'} status={run?.status ?? 'queued'} />
        </div>
        <div className="panel">
          <PanelTitle icon={<Bug size={18} />} title="Issues" />
          <IssueList issues={run?.issues ?? []} />
        </div>
        <div className="panel wide">
          <PanelTitle icon={<FileText size={18} />} title="Screenshots" />
          <ScreenshotGallery screenshots={run?.screenshots ?? []} />
        </div>
        <div className="panel">
          <PanelTitle icon={<Terminal size={18} />} title="Run Log" />
          <EventLog events={run?.events ?? []} />
        </div>
        <div className="panel wide">
          <PanelTitle icon={<Bot size={18} />} title="LLM Calls" />
          <LlmCallPanel calls={run?.llm_calls ?? []} />
        </div>
        <div className="panel wide">
          <PanelTitle icon={<ListChecks size={18} />} title="Attempts" />
          <AttemptsPanel attempts={run?.attempts ?? []} />
        </div>
        <div className="panel report-panel wide">
          <PanelTitle icon={<FileText size={18} />} title="Report" action={run?.report_path ? refreshReport : undefined} />
          <ReportPanel report={report} />
        </div>
      </section>
    </main>
  );
}

function PanelTitle({ icon, title, action }: { icon: React.ReactNode; title: string; action?: () => void }) {
  return (
    <div className="panel-title">
      <span>{icon}{title}</span>
      {action && <button className="icon-button" onClick={action} aria-label="Refresh report"><Activity size={16} /></button>}
    </div>
  );
}
