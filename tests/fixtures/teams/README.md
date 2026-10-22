# Teams activity fixtures

Real activities Teams posted to `/api/messages`, captured by `src/adapters/teams.py` (step 1:
print and return 200). Use them as test input for the Teams adapter instead of hand-written JSON.

## `message_personal.json`

A 1:1 (personal-scope) chat message to the dev bot, captured 2026-10-22 through ngrok.
Body only: the request headers, including `Authorization`, were not printed.

Identifiers were replaced before committing; the shape and prefixes are real:

| Placeholder | Stands for |
|---|---|
| `…aaaa` | Entra tenant id |
| `…bbbb` | Bot id = Entra app (client) id = `MICROSOFT_APP_ID` |
| `…cccc` | Sender's Entra object id |
| `…dddd` | Teams app (manifest) id |
| `29:1-test-user-teams-id` | Sender's Teams user id |
| `a:1-test-personal-conversation-id` | Personal conversation id |

## `installation_update_groupchat.json`

Sent when the bot was added to the "AI Learning Course" group chat, captured 2026-10-22. Same
placeholders as above, plus `19:test-group-chat-id@thread.v2` for the group chat id.

- `type` is `installationUpdate` and `action` is `add` (`remove` when the bot is taken out). No
  `text`: this is an event, not a message. Acknowledge it with 200; don't echo it.
- `conversation.conversationType` is `groupChat` and `isGroup` is `true`. The id has the
  `19:…@thread.v2` form, which contains `:` and `@`, so quote it before putting it in a URL.
- `conversation.name` is the chat's name. Personal chats have none.
- `from` has no `name` here, only the ids.
- The activity `id` is `f:…`. Don't use it as `replyToId`; for a welcome message, post a new
  activity to the conversation instead of replying to this one.
- `channelData.settings.selectedChannel.id` repeats the conversation id.
- This is the moment to remember the conversation for proactive stand-up messages:
  `serviceUrl`, `conversation.id` and `tenantId` are all here.

## Fields the adapter uses

| Field | Meaning | Use |
|---|---|---|
| `type` | `message`, or `installationUpdate` / `conversationUpdate` for events such as the bot being added | Dispatch |
| `id` | This activity's id | `replyToId` of the reply; dedup key (`update.chat_message_id`) |
| `text` | Plain text of the message | Input to the extractor |
| `serviceUrl` | Base URL to send replies to; region- and tenant-specific, ends in `/` | Reply URL. Take it from each activity, never hard-code it |
| `conversation.id` | Where to reply | Reply URL |
| `conversation.conversationType` | `personal` here; `channel` / `groupChat` in other scopes | Routing |
| `from` | The user | Becomes `recipient` in the reply |
| `recipient` | The bot | Becomes `from` in the reply |
| `from.aadObjectId` | Stable Entra user id | Map a Teams user to a team member |
| `conversation.tenantId` | Sender's tenant | Should equal `MICROSOFT_APP_TENANT_ID` |
| `timestamp` | UTC time Teams received it | Stand-up window checks |
| `localTimezone` | Sender's IANA timezone (`Asia/Calcutta`) | Scheduler, if members span zones |

Reply (step 3): `POST {serviceUrl}v3/conversations/{conversation.id}/activities/{id}` with a
bot token. `serviceUrl` already ends in `/`.

## Gotchas seen in this capture

- `text` keeps trailing whitespace (`"Hi, what's up "`). Strip before use.
- The HTML version arrives as an `attachments` entry (`text/html`, `&nbsp;`). It duplicates
  `text`; it is not a user attachment.
- `recipient.id` is `28:` + the bot id. `channelData.app.id` is the Teams **app** id, a different
  GUID. Don't confuse the two.
- `from.id` (`29:…`) is Teams-specific; use `aadObjectId` as the stable key for a person.
- In a channel the bot only receives messages that @mention it, and `text` then includes the
  mention markup. This capture is personal scope, so there is none.
