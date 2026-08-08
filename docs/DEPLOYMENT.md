# Google Cloud deployment

## Prerequisites

- A Google Cloud project with billing and Artifact Registry.
- `gcloud` authenticated to the intended project.
- The public GitHub `jawaharlaldoon-bit/Drift` repository containing
  `demo_target/prompts/system.md`.
- A fine-grained GitHub token and Slack incoming webhook.

Enable APIs:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  firestore.googleapis.com pubsub.googleapis.com aiplatform.googleapis.com \
  logging.googleapis.com
```

Create the repository and secrets:

```bash
gcloud artifacts repositories create drift --repository-format=docker --location=us-central1
printf '%s' "$GITHUB_TOKEN" | gcloud secrets create drift-github-token --data-file=-
printf '%s' "$SLACK_WEBHOOK_URL" | gcloud secrets create drift-slack-webhook --data-file=-
printf '%s' "$DEMO_TRIGGER_TOKEN" | gcloud secrets create drift-demo-trigger --data-file=-
```

Never paste these values into Cloud Build substitutions or committed files.

## Deploy

The deployment targets Google Cloud project `data-shard-504916-r8` and the repository
substitutions are already configured. Run:

```bash
gcloud builds submit --config deploy/cloudbuild.yaml
pwsh deploy/configure-events.ps1 -ProjectId data-shard-504916-r8 -Region us-central1
```

The configuration script creates the event and dead-letter topics, an OIDC push identity,
the authenticated subscription, and the required Cloud Run invoker binding.

## Verify

```bash
gcloud run services describe drift-api --region us-central1
gcloud run services describe drift-demo-target --region us-central1
gcloud pubsub topics describe drift-incidents
curl "$(gcloud run services describe drift-api --region us-central1 --format='value(status.url)')/healthz"
```

The health response used in the demo must show:

- `reasoning_backend: gemini_adk`
- `gemini_model: gemini-3.5-flash`
- `state_backend: firestore`
- `action_mode: live`
- `live_actions_ready: true`

After capturing deployment proof, keep the UI available but scale idle services to zero.

## Cost controls

Both Cloud Run services are deployed with minimum instances `0`; the API is capped at three
instances and the deterministic replay target at two. Before recording the demo, create a
billing budget for the project with alerts at 50%, 90%, and 100%, then verify the alert
recipients in Cloud Billing. Keep the maximum instance caps in `deploy/cloudbuild.yaml`,
retain the Pub/Sub dead-letter limit of five deliveries, and delete unused Artifact Registry
images after judging. Never treat a budget as a hard service quota.

## Failure recovery

Required GitHub failures are retried three times inside one delivery. If they remain failed,
the API returns `503`; Pub/Sub redelivers with bounded backoff and moves the durable incident
to `drift-incidents-dlq` after five delivery attempts. Slack failures are recorded in the
action ledger but do not invalidate a successfully opened draft pull request. To replay a
DLQ incident, fix the external dependency, publish a new source event ID, and retain the old
failed run for audit history.
