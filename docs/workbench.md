# Coding Workbench provisioning

Workbench accepts only server-provisioned repository mappings. Operators use repository and runtime IDs from the catalog; browser requests never carry a path, Git ref, executable, environment, or edge-node address.

## Controller configuration

Set `WORKBENCH_REPOSITORIES` to a JSON array before starting the backend:

```json
[
  {
    "workspace_id": "<workspace-uuid>",
    "name": "admin",
    "repository_path": "/srv/opencli-admin",
    "base_ref": "refs/heads/main",
    "worktree_root": "/srv/opencli-worktrees",
    "execution_node_url": "http://edge-coder-1:19823",
    "shared_filesystem_id": "opencli-source",
    "active": true
  }
]
```

The backend reconciles mappings for the authorized workspace when its Workbench catalog is read. `repository_path` and `worktree_root` must be absolute controller paths. `base_ref` must name a checked-out local branch (`refs/heads/...`), not `HEAD`, a remote-tracking ref, or a SHA.

## Runtime affinity

A coding runtime is shown only when its published `agent.runtime-binding.v1` declares both:

```json
{
  "execution_node_url": "http://edge-coder-1:19823",
  "shared_filesystem_id": "opencli-source"
}
```

The managed coding adapters are `codex` and `pi`; the edge node advertises only binaries it can actually launch. A Workbench binding uses one of those values for `runtime` and continues to accept only controller-supplied worktree and timeout configuration.

`execution_node_url` must equal the runtime's `agent_url`, and both values must exactly match the repository mapping. The named filesystem is an operator assertion that the controller-created worktree is mounted at the same path on that edge node. A mismatch fails before dispatch, so a central-only worktree is never sent to an arbitrary edge runtime.

## Confirmation

If the target already equals the checkpoint after an interrupted request, a retry verifies the configured branch is still clean and persists the proposal as applied instead of attempting a second merge. Target-state conflicts are recorded on the pending proposal for the operator to resolve and retry.

A proposal is a controller-created checkpoint. Confirmation rechecks that the configured branch is still checked out, points to the proposal base SHA, and has no staged or unstaged changes. It then fast-forwards that branch to the checkpoint. The result is a normal clean Git commit, so a later proposal can start from the new branch tip. Workbench never uses `reset --hard`.
