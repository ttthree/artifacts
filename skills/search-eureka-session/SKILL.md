---
name: search-eureka-sessions
description: Search local Eureka workspace session files by a user's natural-language description using shell/read tools such as rg, find, head, and sed, then return search-engine-style eureka:// deep-link results with concise task/session summaries.
---

# Search Eureka Sessions

Use this skill when the user wants to find, reopen, or identify a past Eureka task/session/sub-agent from a description, keyword, feature, bug, file path, error, date, or rough memory.

## Workflow

Use the agent's own search and reading tools as the primary implementation. The goal is to combine fast local grep with model judgment, so the agent can handle fuzzy descriptions, synonyms, partial memories, and related concepts better than a fixed scoring script.

1. Identify session roots. Search current Eureka config first, then legacy config:

   ```bash
   find ~/.eureka/workspaces ~/.craft-agent/workspaces -path '*/sessions/*/session.jsonl' -type f 2>/dev/null
   ```

2. Derive multiple search terms from the user's description:

   - literal words from the user
   - likely synonyms and renamed terms
   - repo paths, error fragments, feature names, protocol names, IDs, dates, engine/model names
   - old and new product terms when relevant, such as `Eureka`, `.eureka`, `.craft-agent`, or legacy naming

3. Run several targeted `rg` searches over session files. Prefer `rg` over grep:

   ```bash
   rg -n -i 'term1|term2|phrase with spaces' ~/.eureka/workspaces/*/sessions/*/session.jsonl ~/.craft-agent/workspaces/*/sessions/*/session.jsonl
   ```

   If the query is vague, run several smaller searches instead of one overly broad expression. Use `--glob 'session.jsonl'` when searching from a workspace root.

4. For candidate sessions, read the first metadata line and nearby matching context:

  ```bash
   head -1 ~/.eureka/workspaces/{workspaceId}/sessions/{sessionId}/session.jsonl
   rg -n -i 'matched-term' ~/.eureka/workspaces/{workspaceId}/sessions/{sessionId}/session.jsonl
   sed -n '1,40p' ~/.eureka/workspaces/{workspaceId}/sessions/{sessionId}/session.jsonl
  ```

   Keep reads bounded. Do not dump entire large session files unless the user asks.

5. Use model judgment to rank candidates. Prefer sessions whose metadata or messages show the user's actual intent, not just incidental keyword matches. Consider:

   - metadata `name`, `preview`, `type`, `parentSessionId`, `workingDirectory`, `engine`, `model`, `lastUsedAt`
   - user messages as stronger evidence than tool noise
   - assistant messages as useful summaries
   - recency as a tiebreaker, not the primary signal
   - parent task plus sub-agent relationships when the match is a sub-agent

6. Build each result link:

   ```text
   eureka://workspaces/{workspaceId}/sessions/{sessionId}
   ```

7. Return results directly as Markdown, preserving clickable deep links.

## Output Format

Present results like a web search engine:

```markdown
1. [Title or session name](eureka://workspaces/{workspaceId}/sessions/{sessionId})
   `task/sub-agent` · `engine` · `model` · updated YYYY-MM-DD · workspace `{workspaceId}`
   Summary: one concise sentence about what this task/session did.
   Match: short evidence snippet explaining why this result matches.
```

Include 3-8 results by default. If no strong result exists, say that clearly and show the best weak candidates only if they may help.

## Optional Script Fallback

This skill includes `scripts/search_sessions.py` as a quick baseline search helper. Use it only as a fallback, sanity check, or broad first pass. Do not rely on it as the primary search when the user's request is fuzzy.

```bash
python3 scripts/search_sessions.py "user's search description"
```

The script searches both `~/.eureka/workspaces` and legacy `~/.craft-agent/workspaces`, deduplicates matching workspace/session ids, and prints Markdown links.

## Guardrails

- Do not expose raw session file paths unless useful for troubleshooting.
- Do not paste long raw session logs.
- Do not claim a result is certain if evidence is only a weak keyword match.
- Preserve the `eureka://workspaces/{workspaceId}/sessions/{sessionId}` URL exactly.

## Minimal Manual Fallback

If shell access is limited, ask the user for a workspace id or more keywords, then construct links from known ids:

```text
eureka://workspaces/{workspaceId}/sessions/{sessionId}
```
