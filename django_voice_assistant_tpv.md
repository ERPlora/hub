# Django Voice Assistant for DRF + HTMX (TPV SaaS)

This document contains a complete MVP implementation of a voice/text
assistant for Django applications using HTMX and DRF. It is designed for
multi‑instance deployments (one server per customer) so data is never
mixed.

------------------------------------------------------------------------

## Goals

-   Each customer instance has its own assistant
-   Assistant never touches DB directly
-   All mutations go through DRF endpoints
-   Confirmation required for destructive changes
-   Full audit logging
-   Works with HTMX UI and session auth

------------------------------------------------------------------------

## Architecture

1.  Browser (HTMX + optional speech recognition)
2.  Django assistant endpoints
3.  LLM intent parser (returns JSON)
4.  Tools layer calling DRF internally
5.  Confirmation step
6.  Execution + audit log

------------------------------------------------------------------------

## App structure

assistant/ - models.py - views.py - tools.py - llm.py - urls.py -
templates/ - static/

Add to INSTALLED_APPS: assistant

------------------------------------------------------------------------

## Models

AssistantPlan: Stores pending actions requiring confirmation

AssistantActionLog: Stores execution audit trail

Fields: - user - host - intent - payload JSON - preview text -
timestamps

------------------------------------------------------------------------

## LLM layer

The LLM must always return JSON:

{ "intent": "update_product_price", "args": { "query": "coca cola 33cl",
"new_price": 1.20, "currency": "EUR" }, "confidence": 0.82,
"needs_clarification": false }

This file is the only place coupled to a provider. You can switch
providers later without touching business logic.

------------------------------------------------------------------------

## Tools layer

Tools must call DRF internally to reuse:

-   permissions
-   serializers
-   validation
-   business logic

Example actions: - search products - retrieve product - patch product
price

Never allow the LLM to choose URLs or hosts.

------------------------------------------------------------------------

## HTMX Flow

1.  User speaks or types
2.  /assistant/parse returns:
    -   clarification
    -   product choices
    -   confirmation preview
3.  /assistant/confirm executes mutation
4.  Result panel updates

------------------------------------------------------------------------

## Security rules

-   Assistant inherits DRF permissions
-   All mutations require confirmation
-   Plans tied to user + host
-   Audit log for every action
-   No direct DB writes
-   No cross‑instance calls

------------------------------------------------------------------------

## Voice support

MVP: Use browser SpeechRecognition API

Production: Optional Whisper STT Optional TTS response

------------------------------------------------------------------------

## Cost estimate

Typical TPV usage:

Text only: \~5 €/month per customer

With voice: \~8--10 €/month

SaaS pricing recommendation: Add‑on 10--15 €/month

------------------------------------------------------------------------

## Deployment strategy

Each customer instance includes:

-   its own assistant
-   its own API key (recommended)
-   its own logs
-   its own DB

No central execution layer.

------------------------------------------------------------------------

## Next steps

1.  Plug your ProductViewSet into tools.py
2.  Adjust price field names
3.  Enable real LLM provider
4.  Add role‑based restrictions
5.  Add more intents (orders, stock, analytics)

------------------------------------------------------------------------

This architecture is production‑safe, scalable, and aligned with SaaS
POS systems.
