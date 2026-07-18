# ecs-deploy parameter quick reference

Run from `ecs-deploy/`:

| Parameter | Meaning |
|-----------|---------|
| `-Inventory` | List remote file tree → `last-remote-inventory.txt` (read-only) |
| `-DryRun` | Simulate sync; no remote writes, no restart |
| `-NoDelete` | Do not delete remote files missing locally |
| `-SkipRestart` | Skip `systemctl restart guideflow` |
| `-InstallDeps` | After sync, remote `pip install -r requirements.txt` |
| `-Force` | Skip delete confirmation on real sync |
| `-HostName` / `-User` / `-RemotePath` / `-ProjectRoot` | Override `config.ps1` |

Env overrides: `GUIDEFLOW_ECS_HOST`, `GUIDEFLOW_ECS_USER`, `GUIDEFLOW_ECS_REMOTE`, `GUIDEFLOW_PROJECT_ROOT`.
