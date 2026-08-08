# Building Drift: from AI incident to evidence-backed pull request

> This article was created for the purpose of entering the All Things Agentic Hackathon.

Most incident agents stop at summarization. Drift begins where the alert ends: it routes
the incident, creates durable work in GitHub, generates a constrained candidate, proves the
candidate against replay cases, and sends the result to the team.

## The architectural decision that mattered

Gemini and ADK own interpretation. Deterministic code owns authority. The model can explain
a root cause and propose replacement content, but it cannot choose another repository,
change the branch, execute commands, read secrets, merge code, or skip replay validation.

## Event-driven by default

Pub/Sub decouples producers from Drift and provides at-least-once delivery. Firestore
claims make that delivery safe, while per-action receipts prevent duplicate GitHub and
Slack work after a completed run.

## Proof before pull request

The original failure and adversarial cases execute against both the baseline and candidate
policy. Only a strict improvement with every candidate case passing can create a draft PR.

Add the final public repository, live application, architecture image, and demo video URLs
before publishing.
