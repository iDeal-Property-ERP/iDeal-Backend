---
name: ideal-bruno
description: Maintain the iDeal backend Bruno collection from the Django URL resolver and source schemas. Use for route inventory, request generation or updates, completeness validation, response examples, environment runs, secret checks, and stale-endpoint detection.
---

# iDeal Bruno

Maintain the collection at `docs/api/bruno` in the Backend repository. The backend
resolver, view annotations, Pydantic schemas, and tests are authoritative;
never use an old Postman collection as the endpoint inventory.

## Fast workflows

Run commands from the Backend checkout. The scripts may be added or updated
alongside this skill, so check `scripts/` for current `--help` options first.

- Inventory routes and schemas:
  `uv run python .agents/skills/ideal-bruno/scripts/bruno_tool.py inventory`
- Generate or refresh requests:
  `uv run python .agents/skills/ideal-bruno/scripts/bruno_tool.py generate`
  Review the diff and preserve manually captured examples before overwriting.
- Validate route/method, path/query/body, auth, examples, YAML, environments,
  duplicate names, secrets, and stale endpoints:
  `uv run python .agents/skills/ideal-bruno/scripts/bruno_tool.py validate`
- Add a captured response example by editing the request's `examples` list;
  keep the request, headers, status, and response body together. The validator
  must be run after manual example updates.
- Run locally with the selected environment when the Bruno CLI is installed:
  `bru run --env Local docs/api/bruno`

## Non-negotiable conventions

- Document application handlers only: GET, POST, PUT, PATCH, and DELETE;
  exclude framework-generated OPTIONS/transport behavior.
- Use concise human-readable request names such as `Create agent`, `Delete
  agent`, or `Handle Stripe webhook`; do not prefix names with HTTP methods or
  embed the full URL path.
- Keep request parameters and bodies inside Bruno's `http` block so the Bruno
  UI pre-populates the executable request. Group mobile domains below the
  single `Mobile` folder.
- Every request contains enabled path/query fields and a valid default body
  where applicable. Put required/nullable/default/enum/destructive notes in
  the request `docs` Markdown, never as comments inside JSON.
- Every request has a success example and source-appropriate failure examples
  (empty success, validation, auth/permission, not-found, conflict, or
  provider/webhook failures). Mark static fixtures separately from captured
  runtime responses.
- Keep `Local.yml`, `Dev.yml`, and `Prod.yml` variable names identical. Switch
  environments in Bruno; do not edit request URLs. Dev/Prod hosts remain
  explicit placeholders until deployment owners provide real hosts.
- Keep tokens, webhook secrets, credentials, and local file paths out of Git.
  Use secret environment variables or ignored `.env` values and run the
  validator's secret scan before handoff.

See [references/bruno-conventions.md](references/bruno-conventions.md) for
collection layout, variable names, example labels, and safe update rules.
