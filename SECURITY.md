# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private reporting:
[Report a vulnerability](https://github.com/jaypetez/famlobster/security/advisories/new).

Include steps to reproduce and the impact you expect. You can expect an initial response within a week.

## Scope notes

FamLobster holds a Telegram bot token, an Anthropic API key and Google OAuth tokens in its environment. If you believe any of these were exposed (for example in a log or a commit), rotate them immediately.

Only the latest release on `main` is supported.
