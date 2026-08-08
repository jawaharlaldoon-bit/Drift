# Four-minute demo script

## 0:00–0:30 — The friction

“A tool timeout turned into a destructive production recommendation. An alert alone still
leaves an engineer to reconstruct the evidence, write a ticket, draft a safe change, test
it, and notify the team. Drift completes that workflow.”

Show the empty Operations Room and the four-step Event → Triage → Replay → Draft PR strip.

## 0:30–0:55 — Unedited trigger and cloud proof

Show the Cloud Run `drift-api` revision and Pub/Sub topic, then return to the `.run.app`
URL. Trigger the protected demo. Keep the recording continuous.

## 0:55–1:45 — Autonomous investigation

Follow the live timeline:

- event claimed in Firestore;
- Gemini 3.5 Flash / ADK triage;
- missing deployment evidence identified as the root cause;
- GitHub incident created;
- Slack receives the detection message.

Emphasize that the log text is treated as untrusted evidence.

## 1:45–2:45 — Proof-carrying remediation

Show the allow-listed policy diff. Then show four replay cases moving from the weak
baseline to a 100% candidate pass rate. Open the real GitHub draft PR and point to the
before/after evidence, linked issue, and explicit human boundary.

## 2:45–3:20 — Actions across systems

Open Slack and show the final notification. Return to the action ledger and show that each
external operation has a durable idempotency receipt. Explain that Pub/Sub redelivery
cannot recreate completed actions.

## 3:20–4:00 — Architecture and close

Show the architecture diagram and Cloud Run proof panel.

“Drift uses Gemini 3.5 Flash and Google ADK to reason, but deterministic policy owns every
credential and action. It never merges. It turns operational drift into a tested,
reversible decision a human can trust.”
