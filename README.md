![Banner image](https://user-images.githubusercontent.com/10284570/173569848-c624317f-42b1-45a6-ab09-f0ea3c247648.png)

# n8n - Secure Workflow Automation for Technical Teams

> **Note:** This is a fork of `n8n-io/n8n` that tracks upstream `master` and
> carries one user-facing patch: **AWS system credentials on the AWS (IAM)
> credential**. The implementation is *inspired by* (not a strict copy of)
> [PR #18026](https://github.com/n8n-io/n8n/pull/18026) — see
> [🔧 AWS System Credentials Support](#-aws-system-credentials-support) below.

n8n is a workflow automation platform that gives technical teams the flexibility of code with the speed of no-code. With 400+ integrations, native AI capabilities, and a fair-code license, n8n lets you build powerful automations while maintaining full control over your data and deployments.

![n8n.io - Screenshot](https://raw.githubusercontent.com/n8n-io/n8n/master/assets/n8n-screenshot-readme.png)

## 🔧 AWS System Credentials Support

This fork lets the **AWS (IAM)** credential resolve to the deployment's **ambient
AWS identity** (env vars, IRSA, EKS Pod Identity, ECS task role, EC2 instance
role) instead of static access/secret keys. Turn on **Credential Type → Systems**
on the credential and set `N8N_AWS_SYSTEM_CREDENTIALS_ACCESS_ENABLED=true` on the
instance — every AWS node using that credential (S3, SES, Textract, Transcribe,
Bedrock, …) then authenticates with no static keys stored.

### Lineage & honesty about it

The idea comes from [PR #18026](https://github.com/n8n-io/n8n/pull/18026), but
this is **not** that PR. Two things changed:

- The original PR gated the feature behind its own `CREDENTIALS_ALLOW_SYSTEM`
  env var. This fork **drops that variable** and reuses upstream's official
  `N8N_AWS_SYSTEM_CREDENTIALS_ACCESS_ENABLED` setting, to stay aligned with the
  way n8n shipped system credentials (see the
  [AWS STS credentials docs](https://docs.n8n.io/integrations/builtin/credentials/aws/#sts-credentials-choose-one-method)).
- The resolution chain reuses upstream's `getSystemCredentials()` helper rather
  than carrying a parallel implementation.

### How this differs from stock n8n

Upstream n8n **does** ship system-credential resolution (including IRSA and EKS
Pod Identity) on a separate **AWS (Assume Role)** credential
([PR #20626](https://github.com/n8n-io/n8n/pull/20626), IRSA added in
[PR #22316](https://github.com/n8n-io/n8n/pull/22316)), and most AWS nodes now
accept it. Two gaps remain that this fork closes:

1. **The AWS (Assume Role) credential always performs an extra `STS.AssumeRole`
   hop** into a *target* role — it **requires** a `Role ARN`, `External ID`, and
   session name. There is no way to use the ambient role (ECS task role / IRSA /
   instance role) *directly* as the identity without assuming a second role.
2. **Some nodes still don't expose the Assume Role credential at all** — they
   declare only the **AWS (IAM)** credential, so on stock n8n they can reach the
   ambient role *nowhere* and require static keys.

   IAM-only nodes (upstream `master`, verified 2026-06-09):

   | Node | Affected versions |
   |---|---|
   | AWS Cognito | all |
   | AWS IAM | all |
   | AWS Transcribe | all |
   | AWS S3 | v1 only (default is v2, which supports Assume Role) |

The fork adds **Credential Type → Systems** to the **AWS (IAM)** credential, so
the ambient identity resolves *directly* on the credential every AWS node
already accepts.

| | Stock n8n — AWS (Assume Role) | This fork — AWS (IAM) → Systems |
|---|---|---|
| Static keys required | No (with system creds) | No |
| Mandatory `STS.AssumeRole` hop | **Yes** — needs `Role ARN` + `External ID` | **No** — ambient role *is* the identity |
| Env / IRSA / Pod Identity / ECS / EC2 | ✅ | ✅ (same `getSystemCredentials()` chain) |
| Covers Cognito / IAM / Transcribe / S3 v1 | **No** (IAM-credential-only nodes) | ✅ |
| Gating env var | `N8N_AWS_SYSTEM_CREDENTIALS_ACCESS_ENABLED` | `N8N_AWS_SYSTEM_CREDENTIALS_ACCESS_ENABLED` |

**Benefit:** the ambient role (ECS task role, EKS Pod Identity / IRSA service
account, EC2 instance role) becomes the effective identity *directly* — no
static keys, no `Role ARN` to maintain, and no self-assume round-trip just to
call AWS as yourself — and it works even on the nodes (Cognito, IAM, Transcribe,
S3 v1) that upstream leaves static-key-only.

> ℹ️ **IRSA vs EKS Pod Identity:** both work in this fork *and* in stock n8n —
> they share the same resolver chain (`environment → IRSA → Pod Identity → ECS
> container metadata → EC2 IMDS`). The fork's contribution is exposing that
> chain on the **AWS (IAM)** credential, not adding IRSA support.

### Configuration

1. **Enable system-credential access on the instance** (off by default):

   ```bash
   N8N_AWS_SYSTEM_CREDENTIALS_ACCESS_ENABLED=true
   ```

2. **Give the runtime an AWS identity** — pick whatever your platform provides;
   the chain auto-detects in this order:

   | Source | What to provide |
   |---|---|
   | Environment | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` |
   | IRSA (EKS) | service account annotated with `eks.amazonaws.com/role-arn` (sets `AWS_ROLE_ARN` + `AWS_WEB_IDENTITY_TOKEN_FILE`) |
   | EKS Pod Identity | Pod Identity association (sets `AWS_CONTAINER_CREDENTIALS_FULL_URI`) |
   | ECS / Fargate | task role (sets `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI`) |
   | EC2 | instance profile (IMDSv2-aware) |

3. **In the editor:** create or edit an **AWS (IAM)** credential, set
   **Credential Type → Systems**, save. The access-key fields disappear; the
   credential now uses the ambient identity. Existing **IAM Access Key**
   credentials are untouched (`accessKey` stays the default).

## Key Capabilities

- **Code When You Need It**: Write JavaScript/Python, add npm packages, or use the visual interface
- **AI-Native Platform**: Build AI agent workflows based on LangChain with your own data and models
- **Full Control**: Self-host with our fair-code license or use our [cloud offering](https://app.n8n.cloud/login)
- **Enterprise-Ready**: Advanced permissions, SSO, and air-gapped deployments
- **Active Community**: 400+ integrations and 900+ ready-to-use [templates](https://n8n.io/workflows)

## Quick Start

Try n8n instantly with [npx](https://docs.n8n.io/hosting/installation/npm/) (requires [Node.js](https://nodejs.org/en/)):

```
npx n8n
```

Or deploy with [Docker](https://docs.n8n.io/hosting/installation/docker/):

```
docker volume create n8n_data
docker run -it --rm --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

Access the editor at http://localhost:5678

## Resources

- 📚 [Documentation](https://docs.n8n.io)
- 🔧 [400+ Integrations](https://n8n.io/integrations)
- 💡 [Example Workflows](https://n8n.io/workflows)
- 🤖 [AI & LangChain Guide](https://docs.n8n.io/advanced-ai/)
- 👥 [Community Forum](https://community.n8n.io)
- 📖 [Community Tutorials](https://community.n8n.io/c/tutorials/28)

## Support

Need help? Our community forum is the place to get support and connect with other users:
[community.n8n.io](https://community.n8n.io)

## License

n8n is [fair-code](https://faircode.io) distributed under the [Sustainable Use License](https://github.com/n8n-io/n8n/blob/master/LICENSE.md) and [n8n Enterprise License](https://github.com/n8n-io/n8n/blob/master/LICENSE_EE.md).

- **Source Available**: Always visible source code
- **Self-Hostable**: Deploy anywhere
- **Extensible**: Add your own nodes and functionality

[Enterprise Licenses](mailto:license@n8n.io) available for additional features and support.

Additional information about the license model can be found in the [docs](https://docs.n8n.io/sustainable-use-license/).

## Contributing

Found a bug 🐛 or have a feature idea ✨? Check our [Contributing Guide](https://github.com/n8n-io/n8n/blob/master/CONTRIBUTING.md) for a setup guide & best practices.

## Join the Team

Want to shape the future of automation? Check out our [job posts](https://n8n.io/careers) and join our team!

## What does n8n mean?

**Short answer:** It means "nodemation" and is pronounced as n-eight-n.

**Long answer:** "I get that question quite often (more often than I expected) so I decided it is probably best to answer it here. While looking for a good name for the project with a free domain I realized very quickly that all the good ones I could think of were already taken. So, in the end, I chose nodemation. 'node-' in the sense that it uses a Node-View and that it uses Node.js and '-mation' for 'automation' which is what the project is supposed to help with. However, I did not like how long the name was and I could not imagine writing something that long every time in the CLI. That is when I then ended up on 'n8n'." - **Jan Oberhauser, Founder and CEO, n8n.io**
