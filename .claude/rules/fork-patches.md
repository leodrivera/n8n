# Fork patch manifest

This fork (`leodrivera/n8n`) tracks `upstream/master` continuously on the
`workflows` branch and carries a small set of patches on top. Most patches live
in **fork-only files** that upstream never touches, so they never conflict. A
few patches edit **upstream-owned source files** — those are the only place a
sync conflict can arise.

This file is the authoritative inventory of those upstream-owned edits. It has
two consumers:

1. **The auto-resolve job** (`.github/workflows/sync-from-upstream.yml`) — the
   Claude step reads this file to resolve conflicts with the fork's real intent
   instead of guessing.
2. **Humans** resolving a conflict manually, and a **drift check** that flags
   when the fork starts patching a new upstream file not listed here.

> Keep this file in sync with reality. If you add or remove a patch on an
> upstream-owned file, update the table below in the same change.

## Golden rule for resolving these conflicts

**Preserve BOTH sides.** The fork's edits are additive (extra imports, an extra
credential option, a swapped credential-acquisition call). Upstream edits the
same files for unrelated reasons. A correct resolution almost always keeps the
upstream change AND re-applies the fork's addition on top — not one or the
other. Only drop a side when the two changes are genuinely mutually exclusive,
and then prefer upstream's structure with the fork's addition grafted on.

Never resolve a conflict by deleting the fork's `credentialType` option, the
fork credential helpers, or the fork repo-URL/runtime-config wiring.

## Conflict-prone upstream files

### Feature: AWS "Systems" credential option

Adds a `credentialType: 'accessKey' | 'systemCredential'` choice to the AWS IAM
credential. `systemCredential` delegates to upstream's own
`getSystemCredentials()` (gated by `N8N_AWS_SYSTEM_CREDENTIALS_ACCESS_ENABLED`).
Default `accessKey` keeps upstream behaviour, so the change is backward
compatible. The heavy lifting (`common/aws/system-credentials-utils.ts`) is
**upstream code** — the fork only adds the UI option and the wiring helpers.

| Upstream file | Fork edit | Resolution rule |
|---|---|---|
| `packages/nodes-base/credentials/common/aws/utils.ts` | Adds exports `getAwsSecurityHeaders(...)` and `getAwsCredentialProvider(...)` | Keep both fork helpers AND any upstream additions. Merge import lines (e.g. `assertSupportedAwsRegion` from upstream + fork imports) into one block. |
| `packages/nodes-base/credentials/common/aws/types.ts` | Adds `credentialType?: 'accessKey' \| 'systemCredential'` to the AWS creds type | Keep the fork field; merge with any upstream field additions. |
| `packages/nodes-base/credentials/Aws.credentials.ts` | Adds the `credentialType` property + `displayOptions: { credentialType: ['accessKey'] }` guards hiding key fields under `systemCredential` | Keep the fork `credentialType` property and ALL `displayOptions` guards. Re-apply guards to any new/changed upstream properties too. |
| `packages/nodes-base/nodes/Aws/Textract/GenericFunctions.ts` | Swaps explicit key headers for `getAwsSecurityHeaders(credentials)`; adds the import | Keep fork import + `getAwsSecurityHeaders` call alongside upstream changes (e.g. `assertSupportedAwsRegion`). |
| `packages/nodes-base/nodes/Aws/Transcribe/GenericFunctions.ts` | Same swap as Textract | Same as Textract. |
| `packages/@n8n/nodes-langchain/nodes/llms/LmChatAwsBedrock/LmChatAwsBedrock.node.ts` | `credentials: getAwsCredentialProvider(credentials)` instead of inline keys; imports `getAwsCredentialProvider` + `AwsIamCredentialsType` from `n8n-nodes-base/dist/credentials/common/aws/*` | Keep fork import + `getAwsCredentialProvider(...)` call; merge with upstream changes to the client/model config. |
| `packages/@n8n/nodes-langchain/nodes/embeddings/EmbeddingsAwsBedrock/EmbeddingsAwsBedrock.node.ts` | Same swap as LmChatAwsBedrock | Same as LmChatAwsBedrock. |

### Feature: fork branding / runtime UI config

Lets the built image point at the fork's repo URL and inject runtime config
(version, Sentry, repo URL) without rebuilding the frontend.

| Upstream file | Fork edit | Resolution rule |
|---|---|---|
| `packages/cli/src/constants.ts` | `N8N_VERSION = process.env.N8N_VERSION \|\| n8nPackageJson.version` | Keep the `process.env.N8N_VERSION \|\|` prefix. |
| `packages/frontend/editor-ui/src/app/constants/urls.ts` | `N8N_MAIN_GITHUB_REPO_URL` points at `leodrivera/n8n` | Keep the fork URL value. |
| `packages/cli/src/server.ts` | Adds a `/<rest>/config.js` route serving runtime frontend config (Sentry DSN, version, repo URL from `N8N_MAIN_GITHUB_REPO_URL`) | Keep the fork route + its imports; merge with upstream server changes. |
| `packages/frontend/editor-ui/src/app/components/AboutModal.vue` | Renders `N8N_MAIN_GITHUB_REPO_URL` instead of the hard-coded n8n URL | Keep the fork binding (`:to="N8N_MAIN_GITHUB_REPO_URL"`). |
| `docker/images/n8n/Dockerfile` | Adds OCI label build args + runtime env (`N8N_VERSION`, `N8N_MAIN_GITHUB_REPO_URL`) | Mostly append-only; keep the fork args/env, merge with upstream Dockerfile changes. |

## Fork-only files (never conflict — do not list above)

These exist only in the fork; upstream has no version, so they cannot conflict:

- `.github/workflows/*` not in the whitelist are auto-deleted on sync. The kept
  ones (`sync-from-upstream.yml`, `auto-rebase-iam.yml`, `publish-ghcr.yml`,
  `trigger-rebase-on-release.yml`) are fork-authored.
- `release_update.py` and related release scripts.
- `.claude/rules/*` (this file).

## Drift

If a sync conflict appears in an upstream file **not** in the tables above, the
fork has started patching new surface. Add it here (with intent + resolution
rule) as part of resolving that conflict, and consider whether the patch can
live in a fork-only module instead of editing upstream source.
