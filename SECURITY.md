# Security policy

Thank you for helping keep TEJAS and Tejas AI safe for families.

## Report a problem privately

Please **do not** open a public issue for a security problem.
Use GitHub's private reporting instead: **Security → Report a vulnerability** on this repository.

Tell us what you found, how to reproduce it, and what it affects. We aim to reply within 7 days
and to ship a fix for serious issues within 30 days. We will credit you unless you ask us not to.

## What's in scope

- TEJAS OS build recipe, scripts and default settings
- Tejas AI: the home server, web app, desktop, Android and iOS apps
- The release downloads and how they are built

Problems in upstream software (Debian, KDE, Firefox, LibreOffice, Ollama, etc.) should go to
those projects; tell us too if TEJAS ships an affected version.

## Checking a download is genuine

Every ISO and app is built in public on GitHub Actions and signed with a build-provenance attestation:

```sh
gh attestation verify tejas-1.0-lite-amd64.iso --repo Jkrocks/JK
```

You can also compare the file's SHA-256 with the `.sha256` file next to it on the release page.
