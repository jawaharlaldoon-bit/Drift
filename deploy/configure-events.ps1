param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$ProjectId,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Region
)

$ErrorActionPreference = 'Stop'
$topic = 'drift-incidents'
$deadLetterTopic = 'drift-incidents-dlq'
$subscription = 'drift-incidents-cloud-run'
$serviceAccountName = 'drift-pubsub-push'
$serviceAccount = "$serviceAccountName@$ProjectId.iam.gserviceaccount.com"
$projectNumber = gcloud projects describe $ProjectId --format 'value(projectNumber)'
$pubsubServiceAgent = "service-$projectNumber@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud config set project $ProjectId | Out-Null

gcloud pubsub topics describe $topic --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) { gcloud pubsub topics create $topic --project $ProjectId }
gcloud pubsub topics describe $deadLetterTopic --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) { gcloud pubsub topics create $deadLetterTopic --project $ProjectId }

gcloud iam service-accounts describe $serviceAccount --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create $serviceAccountName --project $ProjectId --display-name 'Drift PubSub push identity'
}

gcloud iam service-accounts add-iam-policy-binding $serviceAccount --project $ProjectId `
    --member "serviceAccount:$pubsubServiceAgent" `
    --role roles/iam.serviceAccountTokenCreator | Out-Null

$apiUrl = gcloud run services describe drift-api --project $ProjectId --region $Region --format 'value(status.url)'
if (-not $apiUrl) { throw 'drift-api is not deployed in the requested project and region.' }

gcloud run services add-iam-policy-binding drift-api --project $ProjectId --region $Region `
    --member "serviceAccount:$serviceAccount" --role roles/run.invoker | Out-Null

gcloud run services update drift-api --project $ProjectId --region $Region `
    --update-env-vars "PUBSUB_AUDIENCE=$apiUrl,PUBSUB_SERVICE_ACCOUNT=$serviceAccount" | Out-Null

gcloud pubsub subscriptions describe $subscription --project $ProjectId 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud pubsub subscriptions create $subscription --project $ProjectId `
        --topic $topic `
        --push-endpoint "$apiUrl/v1/events/pubsub" `
        --push-auth-service-account $serviceAccount `
        --push-auth-token-audience $apiUrl `
        --dead-letter-topic $deadLetterTopic `
        --max-delivery-attempts 5 `
        --min-retry-delay 10s `
        --max-retry-delay 120s
}

gcloud pubsub topics add-iam-policy-binding $deadLetterTopic --project $ProjectId `
    --member "serviceAccount:$pubsubServiceAgent" --role roles/pubsub.publisher | Out-Null
gcloud pubsub subscriptions add-iam-policy-binding $subscription --project $ProjectId `
    --member "serviceAccount:$pubsubServiceAgent" --role roles/pubsub.subscriber | Out-Null

Write-Output "Drift event delivery configured: $topic -> $apiUrl/v1/events/pubsub"
