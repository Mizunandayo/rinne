<!-- rinne/SECURITY.md -->
# Security Policy

## Reporting

Open a GitHub Security Advisory on this repository. Do not open a public issue
for a suspected vulnerability.

## Controls in this repository

| Control | Where |
|---|---|
| Secret scanning, pre-commit | `.githooks/pre-commit` + `.gitleaks.toml` (fails closed) |
| Secret scanning, full history | `.github/workflows/ci.yml`, `secrets` job |
| No long-lived cloud credentials | Workload Identity Federation, `infra/scripts/bootstrap-wif.ps1`. No service-account JSON key is ever downloaded, stored, or written to disk |
| Least privilege | One dedicated service account per Cloud Run service. The default compute service account (project Editor) is used by nothing |
| Network boundary | Only `rinne-web` is public. `rinne-physics` and `rinne-agent` are `--no-allow-unauthenticated`, reached with ID tokens minted from the Cloud Run metadata server |
| Install-time script execution | Blocked by default via pnpm `onlyBuiltDependencies`. Additions require review |
| Dependency pinning | Exact versions, `pnpm-lock.yaml` and `uv.lock` committed |
| Vulnerability scanning | `pnpm audit` and `pip-audit` block CI; Artifact Registry scans images; Dependabot opens PRs weekly |
| Contract enforcement | Every cross-service payload validated against `packages/contracts` at both ends |
| Deploy from CI | Manual dispatch only. A merged pull request cannot reach production by itself |

## Out of scope

Denial of service against a scale-to-zero demo deployment.
