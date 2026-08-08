const FEATURES = [
  {
    title: 'Business questionnaire',
    text: 'Answer a few targeted questions and KapexAI builds a rich context around your idea — customers, location and vision.',
  },
  {
    title: 'SWOT analysis',
    text: 'Get a structured Strengths, Weaknesses, Opportunities and Threats breakdown of your business in seconds.',
  },
  {
    title: 'Live web research',
    text: 'Ask about competitors, markets or pricing and the assistant researches the web for you, with cited sources.',
  },
  {
    title: 'Actionable strategy',
    text: 'Turn your idea into a visual, step-by-step business plan that is affordable and accessible to everyone.',
  },
]

export function Features() {
  return (
    <section className="features" id="features">
      <h2 className="features-title">Your business, understood.</h2>
      <div className="features-grid">
        {FEATURES.map((feature) => (
          <article className="feature-card" key={feature.title}>
            <h3>{feature.title}</h3>
            <p>{feature.text}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
