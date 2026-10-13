# replydesk: Acceptance Criteria

The project is done when every MUST below is met. Submission criteria come first: the published post is the deliverable.

## Submission (MUST)

- **D1.** A post is **published** on DEV before the deadline (Sun Oct 18, 2026, 11:59 PM PDT), using the challenge's submission template and its required tags.
- **D2.** The post includes every required template section:
  1. What I Built (what it does, who would pay, what problem it solves)
  2. Demo (a deployed link or a video)
  3. Code (the public GitHub repo, embedded)
  4. How I Built It (which open-source AI is used and how the project depends on it)
  5. Why Does Open Innovation Matter? (what a closed API couldn't do here)
- **D3.** The post includes these optional sections: My Agent Session, My First User, and Prize Categories (.tech Domain).
- **D4.** Every screenshot in the post renders on the live page.
- **D5.** The demo link opens a working demo.
- **D6.** The repo is public at `dev-brewery/replydesk`. Its first commit falls inside the challenge window (Oct 12 to 18, 2026), and the whole project was built inside that window.

## App (MUST)

- **A1.** An owner can enter a tone guide and paste one or more reviews, each with a star rating and text.
- **A2.** Every review is triaged as thank-you, fix-it, or needs-a-human.
- **A3.** Needs-a-human reviews (legal threats, safety or health claims, refund disputes, personal matters) get no drafted reply, only a short reason.
- **A4.** Every other review gets a draft reply written by the open-weight model in the voice of the tone guide.
- **A5.** Drafts contain no invented facts: no promises, discounts, names or policies that aren't in the tone guide or the review. A check enforces this. A draft that fails the check is retried, then replaced by a clearly labeled template reply.
- **A6.** The in-app model is GLM-5.3-Flash (open weights) through a configurable OpenAI-compatible endpoint. Endpoint and key exist only in gitignored local config, never in the repo.
- **A7.** Without a key, a fresh clone runs the demo offline from committed fixtures of a fictional business with synthetic reviews.
- **A8.** A static GitHub Pages demo renders from committed fixture output and is served at replydeskhq.tech, and the post links to it there.
- **A9.** The test suite passes offline, with network calls mocked.
- **A10.** The repo contains no real reviews, real customer or business names, secrets, real locations or other personal data anywhere in git history.
- **A11.** Every commit is made by the agent.

## Bonus (SHOULD)

- **B1.** A real local business owner uses replydesk on their own reviews, and the post's My First User section describes what happened. Their identity isn't in the repo.
- **B2.** The post links an exported agent session from a clean session.
