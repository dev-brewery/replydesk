# replydesk

A review reply desk for small businesses. The owner pastes in their Google or Yelp reviews, and an open-weight model drafts a reply to each one in the owner's own voice, flags the reviews a human must handle, and keeps a reusable tone guide so every reply sounds like the same person.

## The challenge

DEV Hacktoberfest Open-Source AI Challenge, Week 2: "Side Hustle"
https://dev.to/devteam/join-the-hacktoberfest-open-source-ai-challenge-side-hustle-2550-in-prizes-across-18-winners-55ba

> "Build something with open-weight models or open-source AI that someone would actually pay for."

- Window: Mon Oct 12 to Sun Oct 18, 2026.
- Deadline: Sun Oct 18, 2026, 11:59 PM PDT.
- Winners announced the week of Oct 19.
- The project is new and built entirely inside the window, starting from the first commit.

## Who pays and why

Local shops, cafes, salons and contractors live on their reviews but rarely have time to answer them well. A late, defensive or copy-paste reply costs them customers. replydesk turns a stack of reviews into ready-to-post replies in minutes. Target price: about $9 a month per business.

## What it does

1. **Tone guide.** The owner describes how they talk (or pastes a few replies they've written before). replydesk saves that as a tone guide and reuses it for every draft.
2. **Paste reviews.** The owner pastes one or more reviews, each with its star rating and text.
3. **Triage.** Each review is sorted: thank-you, fix-it (a complaint the business can address), or needs-a-human (legal threats, safety or health claims, refund disputes, anything personal). Needs-a-human reviews get no drafted reply, only a note explaining why.
4. **Draft.** The model drafts a reply for every other review in the owner's voice. Replies never invent facts: no made-up promises, discounts, names or policies that aren't in the tone guide.
5. **Review and copy.** The owner edits each draft and copies it out to post.

## Open source at the core

- The in-app model is **GLM-5.3-Flash** (open weights, MIT license), called through any OpenAI-compatible endpoint. Endpoint and key live only in a gitignored local config.
- Because the weights are open, a business or a reseller can run replydesk on its own hardware, and customer reviews never have to leave it. A closed API can't offer that.
- The project is built by a pi coding agent team running GLM-5.3 and GLM-5.3-Flash.

## Demo

- The demo uses a **fictional business** with synthetic reviews written for the project. No real reviews are copied from any site.
- A static GitHub Pages demo renders from committed fixture output, so it works without a key.
- The demo is served at **replydeskhq.tech** (claimed through Hacktoberfest), entering the .tech Domain partner category.

## First user

A real local business owner tries replydesk on their own reviews during the week. Their identity stays private. The post calls them "a local business owner" unless they agree to be named.

## Out of scope

- Posting replies to Google, Yelp or any platform automatically.
- Scraping reviews from any site.
- Accounts, billing or a hosted backend.
- Any partner integration other than the .tech domain.
