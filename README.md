# replydesk

A review-reply desk for small businesses: paste the raw copy from your Google
Business Profile or Yelp page, and replydesk triages every review (praise,
mixed, needs-a-human) and drafts a reply in your own voice — grounded in your
tone guide, with a verifier that rejects any draft inventing facts your paste
never contained. The offline core runs entirely from committed fixtures, and a
recorded demo renders the full flow without a network. Hosted demo and help:
[replydeskhq.tech](https://replydeskhq.tech/) ·
[recorded demo](https://replydeskhq.tech/demo/) ·
[help](https://replydeskhq.tech/help/).

The open-source core is model-agnostic: it ships pointed at GLM-5.3-Flash
(MIT weights) but speaks to **any OpenAI-compatible endpoint** — set
`LLM_BASE_URL` and `LLM_API_KEY` in a gitignored `.env` and it runs.

## Quickstart

Python 3.12, standard library only — no dependencies to install.

```bash
# offline demo, no key needed
py app.py --demo

# online mode: copy .env.example to .env and fill endpoint + key
py app.py --online

# test suite (offline, network mocked)
py -m unittest discover -s tests

# regenerate the committed demo fixtures from a live run
py tools/build_demo.py

# fresh-clone + privacy audit (exit 0 = all clear)
py tools/final_audit.py
```

## How it was built

replydesk was built in one week by a pi agent team — an orchestrator,
architect, and builder running GLM-5.3 and GLM-5.3-Flash — with every commit
authored by the agent and every decision journaled. See
[JOURNAL.md](JOURNAL.md) for the full decision log.

License: [MIT](LICENSE).
