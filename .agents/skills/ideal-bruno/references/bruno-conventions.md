# Bruno conventions

## Collection layout

The collection root is `docs/api/bruno` in the Backend repository. Group requests by
API domain. Use one request file per application route/method, with stable,
human-readable names such as `Create agent` and `Delete agent`; do not include
the HTTP method or full URL path in the display name. Keep names unique across
the collection. Request URLs use
`{{base_url}}` and path values use named variables such as `{{pk}}`.

The expected environments are `Local`, `Dev`, and `Prod`. They must expose the
same variable names:

- `base_url`
- `access_token` and `refresh_token`
- representative IDs (`pk`, `photo_id`, `listing_id`, `property_id`, `user_id`)
- request helpers (`idempotency_key`, `sample_image`)
- provider values (`webhook_secret`, `webhook_signature`)

Local uses `http://127.0.0.1:8000`. Dev and Prod use clearly marked host
placeholders until deployment URLs are supplied. Values containing secrets or
credentials stay empty/secret or come from ignored `.env` files.

## Request and documentation rules

Use valid JSON or Bruno's multipart form syntax. Populate every known query,
path, and body field with a representative value, including nullable optional
fields when the schema allows them. Explain field semantics in request-level
Markdown docs with a compact table (`field`, `type`, `required`, `nullable`,
`default/enum`, `notes`). Call out destructive operations and provider signing
requirements there.

Store request `params` and `body` under the request's `http` block. This is the
structure Bruno uses to render the actual request body and parameters in the
UI. Keep all mobile subdomains under the top-level `Mobile` folder.

For manually parsed bodies (CSV import, multipart uploads, provider webhooks,
or `Body[dict]` handlers), inspect the owning view and schema before adding or
changing fields. Do not infer undocumented fields from the old collection.

## Response examples

Use these labels consistently where applicable: `success`, `empty success`,
`validation error`, `unauthorized`, `forbidden`, `not found`, `conflict`, and
`provider error`. A snapshot includes the request URL/method, request headers
and body, response status/status text, response headers, and response body.
Static source-derived fixtures must say so in docs; replace them with captured
Local/Dev runtime snapshots when credentials and services are available.

## Safe maintenance sequence

1. Run the route inventory and inspect the owning source for special handlers.
2. Generate/update requests, preserving hand-authored docs and captured
   examples unless the source contract actually changed.
3. Run the full validator, including stale-endpoint and secret scans.
4. Run representative requests with `Local`; then run the full collection when
   seeded fixtures and dependencies are available.
5. Report static validation separately from database, provider, upload, OTP,
   deployment, Dev, or Prod checks that could not run.
