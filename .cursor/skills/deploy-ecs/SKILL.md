---
name: deploy-ecs
description: >-
  Sync Guideflow code to Huawei Cloud ECS via ecs-deploy/deploy.ps1.
  Use when the user asks to deploy, sync to ECS, 部署到云服务器, DryRun,
  or run ecs-deploy. Always DryRun first, show change list and risks,
  and wait for explicit user approval before real sync.
---

# Deploy Guideflow to Huawei Cloud ECS

Use the local-only tool under `ecs-deploy/` (gitignored; do not commit).

Working directory:

```powershell
cd D:\Project\guideflow\code\ecs-deploy
```

Config lives in `config.ps1` (copied from `config.example.ps1`). Never embed host IPs, keys, or secrets in this skill or in commits.

## Hard gate (required)

**Never** run a real sync until all of the following are done:

1. Run DryRun
2. Present the update list and risk notes to the user
3. Receive **explicit** approval in a later user message

Approval examples: `同意` / `确认部署` / `可以同步` / `approve` / `go ahead and deploy`.

Not approval: silence, `看看`, `先别`, vague “ok” about the plan only, or questions about the list.

If approval is missing or unclear → **stop**. Do not write to the remote.

## Workflow

### 1. Preconditions

- `ecs-deploy/config.ps1` exists and `$EcsHost` is set (not `YOUR_EIP`)
- SSH works for the configured user/host (prefer key-based auth)
- `rsync` available on PATH or via WSL (`wsl rsync`)

If config is missing, tell the user to copy `config.example.ps1` → `config.ps1` and fill values. Do not invent credentials.

### 2. DryRun (always first for deploy requests)

```powershell
cd D:\Project\guideflow\code\ecs-deploy
.\deploy.ps1 -DryRun
```

Optional before first-time / unfamiliar remotes:

```powershell
.\deploy.ps1 -Inventory
```

### 3. Report before asking for approval

After DryRun output, **must** show:

#### 更新清单

- Files that will be uploaded / updated
- Files that will be deleted on the remote (if any)
- Summarize clearly; paste or group the DryRun lines so the user can scan

#### 风险提示

List only risks that apply to this run (skip N/A items):

- Default sync uses rsync `--delete` — extra remote files (outside excludes) will be removed
- Without `-InstallDeps`, new Python deps in `requirements.txt` may be missing on the server
- Default restarts `guideflow` via systemd unless `-SkipRestart`
- Excludes are never uploaded and are not delete-excluded: `.env`, `data/`, `.venv/`, `ecs-deploy/`, `docs/临时文档/`, etc. (see `excludes.txt`)
- Knowledge base under `data/` must be updated separately per `docs/运维手册.md`
- First full server bring-up still follows `docs/华为云部署指南.md`

Then ask: whether to proceed with real sync, and with which flags if needed.

### 4. Real sync (only after explicit approval)

Default:

```powershell
cd D:\Project\guideflow\code\ecs-deploy
.\deploy.ps1
```

Allowed variants when the user requests them:

| Flag | Meaning |
|------|---------|
| `-NoDelete` | Do not delete remote extras |
| `-SkipRestart` | Sync without systemd restart |
| `-InstallDeps` | Remote `pip install -r requirements.txt` after sync |
| `-Force` | Skip the interactive delete confirmation on real sync |

After sync, report success/failure and whether the service restart ran.

## Forbidden

- Real `.\deploy.ps1` without a completed DryRun report + explicit user approval in this conversation
- `git add -f ecs-deploy` or committing `config.ps1` / deploy secrets
- Adding rsync `--delete-excluded`
- Putting EIP, passwords, or private key paths into git-tracked skill files

## References

- `ecs-deploy/README.md` — local tool usage
- `docs/运维手册.md` — day-2 ops, knowledge base copy
- `docs/华为云部署指南.md` — first-time ECS setup
