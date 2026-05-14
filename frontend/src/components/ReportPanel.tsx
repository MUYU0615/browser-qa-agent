export function ReportPanel({ report }: { report: string }) {
  if (!report) {
    return <div className="empty-state">The Markdown report appears when the run completes.</div>;
  }
  return <pre className="report-text">{report}</pre>;
}
