# POST — replydesk (DEV Hacktoberfest Week 2: "Side Hustle")

Status: DRAFT (full body written 2026-10-15; screenshots pending Friday).
Title (owner picks at publish): **"My first user said 'yeah, absolutely': shipping a review-reply product in five days with an agent team"**
Tags: `devchallenge`, `hf26challenge`.
Account: dev.to/devbrewery. Repo: github.com/dev-brewery/replydesk.
Images: `docs/*.png` via raw URLs, `?v=N` on replacement (DEV's image proxy caches by URL).
Everything below the line is the post body. Headings mirror the challenge's submission
template — re-verify exact headings in the DEV editor at publish (kit checklist item).

---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/devteam/join-the-hacktoberfest-open-source-ai-challenge-side-hustle-2550-in-prizes-across-18-winners-55ba)*

## What I Built

**replydesk** is a review-reply desk for small businesses. Local shops live and die by their Google and Yelp reviews, and answering them well is mind-numbing, never-ending work with an outsized effect on search ranking. replydesk turns a stack of reviews into ready-to-post replies that sound like the owner wrote them on their best day.

The flow: sign up at **[replydeskhq.tech](https://replydeskhq.tech/)**, describe how you talk (the *tone guide*), paste in your reviews — and replydesk triages every one into **thank-you**, **fix-it**, or **needs-a-human**. Legal threats, safety claims, and refund disputes never get an auto-draft; they get a plain reason and a human. Everything else gets a reply drafted in the owner's voice by **GLM-5.3-Flash**, an open-weight model (MIT license), then run through a fact-grounding check that rejects any promise, price, name, or policy that doesn't trace back to the tone guide or the review itself. Fail twice and you get a clearly-labeled template instead of an invented fact. You edit, you copy, you post it to Google. Nothing is ever posted for you.

Who pays: solo operators and small teams — the people for whom review-replying is real work but not a job. A founding member signed up this week at **$9/month** and asked where to send the payment.

## Demo

**Live product:** https://replydeskhq.tech/ — sign up, activate the founding trial (no card), paste reviews, draft replies.

**Recorded offline run** (no key, no network — the same pipeline on committed fixtures): https://replydeskhq.tech/demo/

![replydesk workspace with verified drafts](https://raw.githubusercontent.com/dev-brewery/replydesk/main/docs/workspace.png?v=1)

![The landing page: paste, triage, reply](https://raw.githubusercontent.com/dev-brewery/replydesk/main/docs/landing.png?v=2)

## Code

{% embed https://github.com/dev-brewery/replydesk %}

## How I Built It

The open-source core is **GLM-5.3-Flash** (open weights, MIT), called through any OpenAI-compatible endpoint — in the live demo it runs on my own hardware, published through an accountless tunnel. Because the weights are open, the whole product can run inside a business's four walls; reviews never have to leave.

Three deliberate design choices make it trustworthy enough to charge for:

1. **Deterministic triage.** A rule table — not the model — decides what needs a human. The LLM can refine thank-you↔fix-it on a star-rating fall-through, but it has no vote on escalation. A model can't talk the app out of flagging a lawyer letter.
2. **A fact-grounding verifier.** Every model draft is checked: numbers, names, and commitment phrases must trace to the tone guide, the review, or the business profile. Violations trigger one retry with the violations quoted back, then a labeled template fallback. When the model invented a "10% off" that nobody offered, the check caught it.
3. **The tone guide is the product.** My first user's first draft was wordy — his words, "a fair amount of almost saying it twice." We added *"don't be too wordy, get to the point, always sign off with 'God bless'"* to his guide and re-drafted: the reply came back tight and signed off in his voice.

The build itself was done by an **agent team**: an orchestrator (GLM-5.3, max thinking) briefing and verifying, an architect (GLM-5.3, high) designing, and a builder (GLM-5.3-flash, low) writing every line and every commit — every commit in the repo carries the builder's sign-off. The suite is **240+ tests, fully offline, network always mocked**. The session with my first user was transcribed locally with open-source whisper.

## Why Does Open Innovation Matter?

Reviews are other people's personal data — names, complaints, bad days. A closed API means shipping that text to someone else's pricing page forever. Open weights mean the inference endpoint is a config line: the business, or a reseller serving small businesses, can run replydesk on their own hardware and the reviews never leave the building. That's not a feature I could bolt onto a closed-API product; it's the reason this can be sold to people who answer their own phones. It also means no lock-in: any OpenAI-compatible model drops in. And the agent team that built it — open-weight GLM models in an open harness — is the same bet one layer up.

## My Agent Session

The entire repo was built by the agent team described above, one task per commit, every acceptance verified by the orchestrator before the next brief. The full decision log — every ruling, every caught defect, the honest post-mortems (including two sub-agent push hangs and a missing `__main__` that made the server a silent no-op) — ships in the repo as [`JOURNAL.md`](https://github.com/dev-brewery/replydesk/blob/main/JOURNAL.md), and every commit carries `Signed-off-by: GLM-5.3-flash (via pi)`.

## My First User

A local business owner signed up at **replydeskhq.tech**, activated the founding trial, and pasted in a real review from his own Google Business Profile. The whole session was recorded as a voice memo (22 minutes, transcribed with an open-source whisper model running locally).

The moment that made the week: his first draft came out wordy — his own read was "a fair amount of almost saying it twice." We added two lines to his tone guide — *don't be too wordy, get to the point, always sign off with "God bless"* — and re-drafted. The reply came back tight and signed off in his voice. His reaction:

> "See, I like that. I suck at putting all this together — but now reading this… I like it."

That's the product thesis in one sentence: not writing his reviews *for* him — sounding like him on his best day.

- **Did they pay? Would they?** He activated the founding trial ($9/month, invoiced later, no card), and asked directly: **"Yeah, absolutely — we just have to set something up, a payment plan."**
- **What did they ask for next?** Notifications: *"How am I going to get notified that I get a new review? That's going to be my catch."* A review watcher that pings him is the first thing on the roadmap.
- **Where it rubbed (honestly):** pasting his reviews didn't parse on the first try — he'd copied from his own Google Business dashboard, whose copy shape differs from the public Maps page (literal `star` words instead of icons). He fell back to typing `5 | review text` lines, which worked immediately — and the parser learned the dashboard shape the same day; both surfaces now paste cleanly.

His identity stays private — he is "a local business owner" — and the voice memo never leaves my devices.

## Prize Categories

- **Best Use of a .tech Domain** — the product is live at **[replydeskhq.tech](https://replydeskhq.tech/)**, a .tech domain claimed through Hacktoberfest, serving the sign-up product itself (not a redirect): landing, accounts, founding-plan trial, and drafting.
