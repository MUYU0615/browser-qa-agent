import { Bot, CheckCircle2, CircleSlash, Code2 } from 'lucide-react';
import { LlmCall } from '../api';

export function LlmCallPanel({ calls }: { calls: LlmCall[] }) {
  if (calls.length === 0) {
    return <div className="empty-state"><Bot size={18} /> No LLM call has been recorded yet.</div>;
  }

  return (
    <div className="llm-call-list">
      {calls.map((call, index) => (
        <article className="llm-call" key={`${call.at}-${call.node}-${index}`}>
          <header>
            <div>
              <h3>{call.node} / {call.purpose}</h3>
              <p>{new Date(call.at).toLocaleTimeString()} · {call.model} · {call.base_url}</p>
            </div>
            <div className={`llm-status ${call.called_model ? 'called' : 'fallback'}`}>
              {call.called_model ? <CheckCircle2 size={16} /> : <CircleSlash size={16} />}
              {call.called_model ? 'Model called' : 'Fallback'}
            </div>
          </header>

          {call.fallback_reason ? <div className="fallback-line">Fallback reason: {call.fallback_reason}</div> : null}

          <section className="llm-block">
            <h4><Code2 size={15} /> Prompt</h4>
            <pre>{call.prompt}</pre>
          </section>

          <section className="llm-block">
            <h4><Code2 size={15} /> Raw Output</h4>
            <pre>{call.raw_output || '(no raw model output)'}</pre>
          </section>

          <section className="llm-block">
            <h4><Code2 size={15} /> Parsed Output</h4>
            <pre>{JSON.stringify(call.parsed_output, null, 2)}</pre>
          </section>
        </article>
      ))}
    </div>
  );
}
