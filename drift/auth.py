"""OIDC verification for public Cloud Run routes receiving authenticated Pub/Sub pushes."""

from __future__ import annotations

import asyncio

from .config import Settings


async def verify_pubsub_authorization(authorization: str | None, settings: Settings) -> None:
    if settings.drift_env != "production":
        return
    if not settings.pubsub_audience or not settings.pubsub_service_account:
        raise PermissionError("Pub/Sub OIDC verification is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise PermissionError("missing Pub/Sub bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    def verify() -> dict:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        return id_token.verify_oauth2_token(token, Request(), settings.pubsub_audience)

    claims = await asyncio.to_thread(verify)
    if claims.get("email") != settings.pubsub_service_account:
        raise PermissionError("unexpected Pub/Sub service account")
    if claims.get("email_verified") is not True:
        raise PermissionError("Pub/Sub service account email is not verified")
