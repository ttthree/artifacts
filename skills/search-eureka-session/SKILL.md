---
name: search-eureka-sessions
description: Search local Eureka workspace session files by a user's natural-language description and return search-engine-style results with eureka:// deep links plus concise task/session summaries.
---

# Search Eureka Sessions

Use this skill when the user wants to find, reopen, or identify a past Eureka task/session/sub-agent from a description, keyword, feature, bug, file path, error, date, or rough memory.

## Workflow

1. Run the bundled search script from this skill directory:

   ```bash
   python3 scripts/search_sessions.py "user's search description"
   ```

   By default it searches both `~/.eureka/workspaces` and legacy `~/.craft-agent/workspaces`, then deduplicates matching workspace/session ids.

2. Return the script's Markdown results directly, keeping the clickable `eureka://workspaces/{workspaceId}/sessions/{sessionId}` links.

3. If there are too many weak matches, ask one focused follow-up question or rerun with more specific terms.

## Options

- Search one workspace:

  ```bash
  python3 scripts/search_sessions.py "query" --workspace-id 9df32373-5d69-dc49-bd69-e55a0acb599f
  ```

- Increase result count:

  ```bash
  python3 scripts/search_sessions.py "query" --limit 12
  ```

- Search a custom workspaces root:

  ```bash
  python3 scripts/search_sessions.py "query" --workspaces-root ~/.eureka/workspaces
  ```

- Search multiple custom roots:

  ```bash
  python3 scripts/search_sessions.py "query" --workspaces-root ~/.eureka/workspaces --workspaces-root ~/.craft-agent/workspaces
  ```

## Output Expectations

Present results like a web search engine:

- A clickable title using the Eureka deep link.
- Metadata such as session id, type, engine/model, workspace id, and updated time.
- A short summary of what the task/session appears to be about.
- A match snippet showing why it was found.

Do not paste raw session logs unless the user asks for details. Do not expose internal file paths unless useful for troubleshooting.

## Fallback

If Python is unavailable, inspect session metadata manually:

```bash
rg -n "query terms" ~/.eureka/workspaces/*/sessions/*/session.jsonl ~/.craft-agent/workspaces/*/sessions/*/session.jsonl
```

Then build links as:

```text
eureka://workspaces/{workspaceId}/sessions/{sessionId}
```
