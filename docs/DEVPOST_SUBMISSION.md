# Devpost submission draft

## Inspiration

AI failures often happen when a tool returns nothing and the model fills the gap with a
confident answer. The alert is only the beginning of the work. We wanted an agent that
could carry the incident all the way to a safe, testable, human-reviewable resolution.

## What it does

Drift receives AI incident events asynchronously through Pub/Sub. It uses Gemini 3.5 Flash
and Google ADK to triage the failure, identify the evidence gap, route the response, create
a GitHub issue, generate a constrained policy fix, replay the failure and adversarial
cases, open a draft pull request when validation passes, and notify Slack. It records every
stage and external action in Firestore and never merges automatically.

## How we built it

- Gemini 3.5 Flash on Vertex AI
- Google ADK sequential coordinator
- Cloud Run services for Drift and the replay sandbox
- Pub/Sub with OIDC push and a dead-letter topic
- Firestore state and action receipts
- Secret Manager and structured Cloud Logging
- GitHub REST API and Slack incoming webhooks
- FastAPI, React, TypeScript, and Vite

## Challenges and learnings

The hard part was not generating a patch; it was making autonomous action safe and
repeatable. We separated model reasoning from tool authority, added repository/path/hash
constraints, made event and action identities durable, and required live replay evidence
before Drift can create a draft PR.

## Pre-existing work disclosure

Drift incorporates selected pre-existing Apache-2.0 infrastructure from work predating
the contest. Its
Taskmaster workflow, Pub/Sub ingestion, ADK/Gemini 3.5 path, GitHub and Slack actions,
proof-carrying validation, interface, cloud deployment, documentation, and submitted
behavior were created or substantially rewritten during this submission period. Details
are provided in the repository’s `licence/` folder.

## Submission checklist

- [ ] Taskmaster selected
- [ ] Hosted Operations Room URL
- [ ] Public repository URL
- [ ] Architecture diagram
- [ ] Reproducible README
- [ ] Public YouTube/Vimeo demo, no longer than four minutes
- [ ] Visible Cloud Run / Pub/Sub / Vertex AI proof
- [ ] Public build article
- [ ] Social post with `#AllThingsAgenticHackathon`
