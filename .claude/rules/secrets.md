# The `.secrets/` Directory Contract

API credentials belong to the repository you are working in, never to the
skills. The skills are shared — linked into many repositories from one
checkout — so a key stored alongside them would be a key shared with every
project and, if that checkout is public, with everyone.

## Layout

```
<your-repo>/.secrets/          mode 700, gitignored
  keys.json                    mode 600
```

```json
{
  "pangram": "...",
  "serpapi": "...",
  "semantic_scholar": "...",
  "ollama": "..."
}
```

YAML (`keys.yaml`) works the same way when PyYAML is installed. Keys beginning
with `_` are treated as comments. Service names are the short forms above, not
the environment-variable names.

## Discovery

A script walks up from the working directory to find the nearest `.secrets/`,
the same rule `writing-voice/` uses. Absent, nothing changes — a missing
`.secrets/` is a normal state, not an error, and every script still accepts its
key by flag or environment variable.

## Resolution order

| Order | Source | Use for |
|---|---|---|
| 1 | `--api-key` on the command line | one-off runs, CI |
| 2 | the service's environment variable | existing setups, shared shells |
| 3 | `.secrets/` discovered by walking up | the normal case |

Explicit always wins, so adding a `.secrets/` file never changes what an
existing command does.

## Refusals

The loader refuses rather than reads when the directory is unsafe:

- **Not gitignored, inside a repository.** One `git add -A` would commit the
  keys. This is not hypothetical — a Claude OAuth token sat tracked in a public
  repository for five months because nothing refused.
- **Group- or world-readable.** Credentials are `700`/`600` or they are not
  credentials.
- **A placeholder value.** Better to stop than to send `REPLACE-ME` to an API
  and read the failure as a service outage.

Outside a git repository there is nothing to check, and that is allowed —
unknown is not treated as unsafe.

## Handling

Add `.secrets/` to `.gitignore` **before** creating the directory. Doing it
afterwards leaves a window, and that window is how this goes wrong.

A key value is never printed, logged, or included in an error message. Errors
name the service and the places searched. Parser errors report the path and the
error type only, because a parser that quotes the offending content is quoting
the key.

Never paste a key into a chat, an issue, or a commit message. A key that has
been through any of those is disclosed; rotate it rather than filing it.

## Consumers

`scripts/pangram.py`, `update-references/scripts/scholar.py`, and
`update-references/scripts/semantic_scholar.py` resolve through
`scripts/credentials.py`. `python3 <surface>/scripts/credentials.py` reports
which services are configured, printing names and status, never values.
