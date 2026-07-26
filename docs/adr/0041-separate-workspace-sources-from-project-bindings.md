---
status: accepted
---

# Separate Workspace Sources from Project Source Bindings

This supersedes ADR-0030. Reusable external endpoints are Workspace-owned Sources, while each Project owns Source Bindings that narrow authorization and collection scope. Semantic Source and Binding edits create immutable revisions, and every published Workflow Version pins exact Source Binding Revisions so Automations cannot drift silently; credential rotation, health updates, and safety revocation remain immediately effective because security and operability take precedence over reproducibility.
