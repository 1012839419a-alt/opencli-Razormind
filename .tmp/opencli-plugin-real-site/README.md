# opencli-plugin-real-site-case

Live Hacker News end-to-end adapter case for OpenCLI Admin.

## Install

```bash
# From local development directory
opencli plugin install file://D:\projects\opencli-admin\.tmp\opencli-plugin-real-site

# From GitHub (after publishing)
opencli plugin install github:<user>/opencli-plugin-real-site-case
```

## Commands

| Command | Type | Description |
|---------|------|-------------|
| `hn-live-case/top` | Pipeline | Fetch live Hacker News top stories |

## Development

```bash
# Install locally for development (symlinked, changes reflect immediately)
opencli plugin install file://D:\projects\opencli-admin\.tmp\opencli-plugin-real-site

# Verify commands are registered
opencli list | grep hn-live-case

# Run a command
opencli hn-live-case top --limit 3 -f json
```
