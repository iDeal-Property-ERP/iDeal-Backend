# Chat realtime protocol

Chat clients connect to `GET /ws/v1/chat/` using `ws://` locally and `wss://`
in production. The upgrade request accepts the existing API access token in the
`Authorization: Bearer <access-token>` header. Browser clients may instead use
the `ideal_access` cookie. The server closes unauthenticated connections with
code `4401`.

The endpoint is deliberately an event stream, not a second write API. Clients
continue to use the documented REST endpoints for sending messages and then
refresh their authoritative state when an event arrives. This keeps retries,
idempotency (`client_id`), validation and error envelopes consistent across
web and mobile.

## Frames

After a successful connection the server sends:

```json
{"type":"chat.ready","latest_event_id":184,"heartbeat_seconds":25}
```

Clients persist the largest `event_id`, ignore duplicate or older events, and
immediately send a sync request:

```json
{"type":"chat.sync","after_event_id":184}
```

If an event cursor has expired, the server emits `chat.resync_required`. The
client must refresh chat summaries and the active conversation via REST, reset
its cursor, then send `chat.sync` again. It must not fill the gap with polling.
Send `{"type":"chat.ping"}` at least every 25 seconds while connected.

The durable event types are `chat.message.created`, `chat.conversation.updated`,
`chat.conversation.removed`, and `chat.read.updated`. They include an
`event_id`, `conversation_id`, `conversation_version`, and the corresponding
message or conversation payload. A client should fetch messages after its
known message ID and refresh the conversation summary rather than assuming an
event is a complete local snapshot.

Typing is transient and opt-in. Send
`{"type":"chat.typing.set","conversation_id":42,"is_typing":true}` and stop
within five seconds; the server broadcasts `chat.typing.updated` only to the
other permitted participant. Typing frames are never persisted or replayed.

## Operations and deployment

The ASGI server must serve both HTTP and WebSocket traffic, and all instances
must use the same Redis deployment for `CHANNEL_LAYERS` and task scheduling.
The proxy/load balancer must forward WebSocket upgrades and preserve the
`Authorization` header or the `ideal_access` cookie. Configure its idle timeout
above 30 seconds; 60 seconds is the application channel expiry default.

Required settings are `REDIS_URL`, optional `CHAT_CHANNEL_CAPACITY` (default
200), `CHAT_CHANNEL_EXPIRY_SECONDS` (default 60),
`CHAT_REALTIME_EVENT_RETENTION_DAYS` (default 7), and
`CHAT_REALTIME_REPLAY_LIMIT` (default 500). The daily Django-Q task
`prune-chat-realtime-events` removes expired durable events. Monitor socket
connects, reconnects, close codes, Redis channel errors, event backlog, and
REST refresh failures; alert on sustained replay/resync or authentication
close-code spikes.

Read receipts are visibility-based: clients send the highest incoming message
that has been at least 60% visible while the app is foregrounded. The server
clamps that watermark to an existing message, recomputes unread counts, and
broadcasts the changed receipt. Sending and read state are represented; there
is no delivered state.
