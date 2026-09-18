export function About() {
  return (
    <main className="section">
      <p className="kicker">Architecture</p>
      <h1>Evidence first, then a conversation.</h1>
      <p className="lede">
        The assistant searches an internal scientific knowledge base, adds external papers only when needed, and asks a
        language model to reason over that evidence. It will not invent citations.
      </p>
      <div className="panel">
        <pre className="debug">{`YOU DESCRIBE THE LAND
  → we remember your site variables
  → we search the knowledge base
  → if that is weak or you asked for studies, we search scientific literature
  → a language model reads the passages
  → you get a plain-language recommendation and separate source lists`}</pre>
      </div>
      <div className="split" style={{ marginTop: 28 }}>
        <div>
          <h3>What you should see</h3>
          <p>A natural answer, a specific recommendation, and why it may help.</p>
          <p>Knowledge-base sources and external papers kept apart.</p>
          <p>Uncertainty when the evidence is thin or only an abstract was available.</p>
        </div>
        <div>
          <h3>What it will not do</h3>
          <p>Invent percentages, DOIs, or page numbers.</p>
          <p>Call an internal synthesis an original FAO or IPBES report.</p>
          <p>Search the entire internet for every ordinary follow-up.</p>
        </div>
      </div>
    </main>
  );
}
