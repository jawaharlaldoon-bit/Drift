# Security model

## Trust boundaries

Incident messages, tool output, logs, model output, repository content, and HTTP responses
are untrusted. Google Cloud identity and locally configured allow-lists define authority.

## Controls

- Pub/Sub uses an OIDC token; production verifies audience, service-account email, and
  verified-email claim.
- The demo trigger requires a separate bearer secret.
- GitHub and Slack credentials are read from Secret Manager-backed environment variables.
- Secrets are redacted from logs, errors, evidence, and UI responses.
- GitHub tokens are limited to one repository and three required write permissions.
- Only configured prompt/policy paths can be changed; traversal and alternate separators
  are rejected.
- The candidate baseline hash must match the incident snapshot.
- Patches have a byte limit and high-risk candidates are blocked.
- Models cannot execute shell commands or call external services.
- Slack is notification-only; a Slack failure cannot undo a validated GitHub artifact.
- Drift has no merge, deployment, or production mutation capability.

## Prompt-injection containment

All agent instructions state that embedded log/model text is evidence, not instruction.
The deterministic layer ignores any model-suggested repository, branch, path, API method,
or credential. Security tests include injected instructions, path traversal, secret-shaped
content, oversized patches, and cross-repository targets.

## Operational checklist

- Rotate demo secrets after recording.
- Use a dedicated repository and Slack channel.
- Keep Cloud Run minimum instances at zero and cap maximum instances.
- Enable billing alerts before deployment.
- Review Cloud Logging for repeated failures and the Pub/Sub dead-letter topic.
- Freeze the submission tag and deployment during judging.
