## ADDED Requirements

### Requirement: Skill correction detail view
The system SHALL render a correction detail view for any skill that has an open
proposal (`has_open_proposal = true`), reachable by clicking the "待复核" badge
in the `/skills` table.

#### Scenario: Skill has open proposal
- **WHEN** a skill row shows the "待复核" badge
- **THEN** the badge is a clickable link to `/skills/{skill_id}`
- **AND** the detail view loads the skill via `getSkill` and shows its name,
  domain, capability, version, evidence count, and the proposal body.

#### Scenario: Skill has no proposal
- **WHEN** a skill has no open proposal
- **THEN** the row shows an em-dash and the badge is not rendered.

### Requirement: Correction actions on the detail view
The detail view SHALL offer dismiss, rollback, and redistill actions backed by
the existing backend endpoints.

#### Scenario: Dismiss a correction proposal
- **WHEN** the operator clicks "dismiss" on a proposal
- **THEN** `dismissCorrection` is called with the skill id
- **AND** the view refreshes to show the proposal is gone, with a success toast.

#### Scenario: Rollback a skill
- **WHEN** the operator clicks "rollback"
- **THEN** `rollbackSkill` is called
- **AND** the skill row reflects the rolled-back version after refresh.

#### Scenario: Redistill a skill
- **WHEN** the operator clicks "redistill"
- **THEN** `redistillSkill` is called
- **AND** the view shows a pending/processing state until the backend confirms.

### Requirement: Error handling on correction actions
Correction actions SHALL surface backend errors inline rather than silently
failing.

#### Scenario: Backend rejects an action
- **WHEN** `dismissCorrection`, `rollbackSkill`, or `redistillSkill` returns an
  error
- **THEN** the detail view shows the normalized error message
- **AND** the action button re-enables so the operator can retry.
