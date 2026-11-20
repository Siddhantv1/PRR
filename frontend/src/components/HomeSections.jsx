import { STAGE_LABELS } from './stages'

const REPO_URL = 'https://github.com/Siddhantv1/PRR'

// What each stage does, in the README's own terms.
const STAGE_NOTES = {
  dna_extractor:
    'Reads the repository and its recent merged pull requests, then writes the Project Constitution: error handling, naming, test patterns, imports, docs and red flags.',
  issue_analyst:
    'Reads the issue and plans the fix: root cause, affected files, related issues and pull requests.',
  contributor:
    'Writes the smallest correct change and a test for it, then runs the project’s tests.',
  maintainer:
    'Reviews the diff as a maintainer would, with blocking comments, suggestions and questions. It sends the fix back until it approves, up to two revision rounds by default.',
  output_generator:
    'Writes the final diff, the pull request title and body, and the review transcript.',
}

const OUTPUTS = [
  ['Live stream', 'Every tool call, result and agent note, as it happens.'],
  ['Review transcript', 'Each round of maintainer comments, through to approval.'],
  ['The diff', 'The final change, ready to copy.'],
  ['Pull request text', 'A title and body you can paste into GitHub.'],
]

function focusIssueField() {
  document.getElementById('issue-url')?.focus()
}

export function HomeSections() {
  return (
    <>
      <section className="home-section container what" id="what" aria-labelledby="what-title">
        <div>
          <h2 id="what-title">A patch that reads like the project wrote it</h2>
          <p className="home-section__lead">
            PRR takes a GitHub issue, fixes it, and reviews its own fix before you see it. First it
            studies the repository and its recent merged pull requests and writes down the house
            rules as a Project Constitution. The fix and the review are both held to it.
          </p>
        </div>
        <figure className="compare" aria-label="A plain patch compared with a PRR patch">
          <div className="compare__head">
            <span>--- a/plain-agent.patch</span>
            <span>+++ b/prr.patch</span>
          </div>
          <p className="compare__line del">written without reading the project</p>
          <p className="compare__line add">follows the project’s error handling and naming</p>
          <p className="compare__line add">adds a test in the project’s test style</p>
          <p className="compare__line add">goes through a maintainer review first</p>
        </figure>
      </section>

      <section className="home-section container" id="how" aria-labelledby="how-title">
        <h2 id="how-title">Five agents, one pull request</h2>
        <ol className="stages">
          {STAGE_LABELS.map(([key, label], index) => (
            <li key={key}>
              <span className="stages__num">{index + 1}</span>
              <h3>{label}</h3>
              <p>{STAGE_NOTES[key]}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="home-section container" id="get" aria-labelledby="get-title">
        <h2 id="get-title">What you watch, what you keep</h2>
        <dl className="outputs">
          {OUTPUTS.map(([term, detail]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{detail}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="home-section container" id="limits" aria-labelledby="limits-title">
        <h2 id="limits-title">Before you run it</h2>
        <ul className="limits">
          <li>
            It takes a public GitHub issue URL:{' '}
            <code>https://github.com/owner/repo/issues/123</code>.
          </li>
          <li>
            It clones the repository and runs its tests on this machine. Go projects need{' '}
            <code>go</code> on your <code>PATH</code>.
          </li>
          <li>It never opens the pull request. You copy the diff and the description yourself.</li>
          <li>The maintainer is simulated. Treat its review as a pre-review, not a real one.</li>
        </ul>
      </section>

      <section className="home-section container closing" aria-labelledby="closing-title">
        <h2 id="closing-title">Start with an issue</h2>
        <button type="button" className="btn" onClick={focusIssueField}>
          Paste an issue URL
        </button>
      </section>

      <footer className="site-footer">
        <div className="container site-footer__inner">
          <span>
            <span className="wordmark">prr</span> Pull-Request Robot
          </span>
          <a href={REPO_URL}>Source on GitHub</a>
        </div>
      </footer>
    </>
  )
}
