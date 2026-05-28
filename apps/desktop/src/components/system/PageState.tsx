export type PageStateTone = "loading" | "empty" | "error" | "success";

interface PageStateProps {
  tone: PageStateTone;
  title: string;
  body: string;
  meta?: string;
}

export function PageState({ tone, title, body, meta }: PageStateProps) {
  return (
    <section className={`state-panel ${tone}`}>
      <span className={`status-dot ${tone}`} />
      <div>
        {meta ? <p className="state-meta">{meta}</p> : null}
        <h2>{title}</h2>
        <p>{body}</p>
      </div>
    </section>
  );
}

