import { Fragment, useEffect, useRef, useState } from "react";
import type { TeamResponse } from "@fplmodell/api-client";
import { api, type ChatLine, type PageCall } from "./api";
import { Icon } from "./icons";
import { useWorkspace } from "./Workspace";

type Line = ChatLine | { role: "notice"; text: string };

/** Pages whose content is not already in the team state the chat receives. */
const VIEW_CALLS: Record<string, PageCall[]> = { timeline: [{ tool: "timeline" }] };

/** **bold** is the only markup the chat is asked to use. */
function Formatted({ text }: { text: string }) {
  return <>{text.split(/\*\*(.+?)\*\*/g).map((part, index) => index % 2 ? <strong key={index}>{part}</strong> : <Fragment key={index}>{part}</Fragment>)}</>;
}

/** Ask Claude about the team: it sees the forecast, the squad, every computed result and the open page. */
export function Chat({ team, view, label }: { team: TeamResponse; view: string; label: string }) {
  const workspace = useWorkspace();
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    api.chatHistory(team.session_id).then(result => { if (active) { setLines(result.messages); setEnabled(result.enabled); } }).catch(() => undefined);
    return () => { active = false; };
  }, [team.session_id]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [lines, status, open]);

  const priciest = [...team.squad].sort((a, b) => (b.price ?? 0) - (a.price ?? 0))[0]?.name;
  const suggestions = [
    "Should I roll my transfer or make a move this week?",
    "Who should I captain, and how close is it?",
    ...(priciest ? [`I'm thinking of selling ${priciest}. Pros and cons?`] : []),
    `Explain what this page shows and what you would do.`,
  ];
  const constraints = workspace.constraints;
  const sees = [label, `GW${team.target_event}`, `${team.horizon} GW`, team.risk_profile,
    ...(constraints.locked_ids.length ? [`${constraints.locked_ids.length} locked`] : []),
    ...(constraints.excluded_ids.length ? [`${constraints.excluded_ids.length} excluded`] : [])].join(" · ");

  const send = async (question = draft.trim()) => {
    if (!question || busy) return;
    setDraft(""); setError(""); setBusy(true); setStatus("Sending");
    setLines(current => [...current, { role: "user", text: question }, { role: "assistant", text: "" }]);
    const append = (text: string) => setLines(current => [...current.slice(0, -1), { role: "assistant", text: current[current.length - 1].text + text }]);
    const calls = [...(workspace.pageCalls.current[view] ?? VIEW_CALLS[view] ?? []),
      ...(workspace.inspected != null ? [{ tool: "player", args: { player_id: workspace.inspected } }] : [])];
    const savedPlans = workspace.plans.map(({ name, kind, summary, metrics, created, event, horizon }) => ({ name, kind, summary, metrics, created, event, horizon }));
    let failure = "";
    try {
      await api.chat(team.session_id, { message: question, page: { view, label, calls, saved_plans: savedPlans }, ...constraints }, event => {
        if (event.type === "text") { setStatus(""); append(event.text); }
        else if (event.type === "status") setStatus(event.text);
        else if (event.type === "notice") setLines(current => [{ role: "notice", text: event.text }, ...current.slice(-2)]);
        else if (event.type === "error") failure = event.message;
      });
    } catch (err) { failure = err instanceof Error ? err.message : "The chat failed."; }
    if (failure) { // the server rolled the turn back, so the question goes back in the box
      setLines(current => current.slice(0, -2));
      setDraft(question); setError(failure);
    }
    setBusy(false); setStatus("");
  };
  const reset = () => { setError(""); api.resetChat(team.session_id).then(() => setLines([])).catch(err => setError(err instanceof Error ? err.message : "Could not start a new chat.")); };

  return <>
    <button className="chat-toggle" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="chat-panel">
      {open ? <Icon.Close size={18} /> : <Icon.Compass size={18} />}<span>{open ? "Close" : "Ask Claude"}</span>
    </button>
    {open && <section id="chat-panel" className="chat-panel" aria-label="Chat about your team" onKeyDown={event => { if (event.key === "Escape") setOpen(false); }}>
      <header>
        <div><strong>Ask about your team</strong><small title="What the chat can see right now">Sees: {sees}</small></div>
        <span className="chat-actions">
          <button className="secondary" onClick={reset} disabled={busy || !lines.length}>New chat</button>
          <button className="secondary" onClick={() => setOpen(false)} aria-label="Close chat"><Icon.Close size={15} /></button>
        </span>
      </header>
      <div className="chat-log" aria-live="polite">
        {!lines.length && <div className="chat-empty">
          <p>Claude sees the forecast for every player, your squad, finances and chips, every result the app has computed for you and the page you have open. It can run the transfer search, planner and comparisons itself.</p>
          {!enabled && <p className="chat-error">Add <code>ANTHROPIC_API_KEY</code> to the <code>.env</code> file in the project folder to use the chat.</p>}
          {suggestions.map(text => <button key={text} className="chat-suggestion" onClick={() => void send(text)} disabled={busy}>{text}</button>)}
        </div>}
        {lines.map((line, index) => <div key={index} className={`chat-line chat-${line.role}`}>
          {line.role === "assistant" && !line.text && busy && index === lines.length - 1 ? <span className="spinner" /> : <Formatted text={line.text} />}
        </div>)}
        {status && <p className="chat-status">{status}…</p>}
        <div ref={end} />
      </div>
      {error && <p className="chat-error" role="alert">{error}</p>}
      <form className="chat-input" onSubmit={event => { event.preventDefault(); void send(); }}>
        <textarea aria-label="Message" rows={2} value={draft} maxLength={4000} placeholder="E.g. I want to sell Haaland – what do I lose?"
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} />
        <button className="primary" type="submit" disabled={busy || !draft.trim()}>{busy ? "…" : "Send"}</button>
      </form>
    </section>}
  </>;
}
