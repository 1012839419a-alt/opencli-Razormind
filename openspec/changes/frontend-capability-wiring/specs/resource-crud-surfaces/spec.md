## ADDED Requirements

### Requirement: Agent creation form
The `/agents` page SHALL replace its dead empty state with a working create
form.

#### Scenario: Create an agent
- **WHEN** the operator clicks "新建智能体" on `/agents`
- **THEN** a form opens with name, description, and profile fields
- **AND** submitting calls `createAgent` and the new agent appears in the list.

#### Scenario: Cancel creation
- **WHEN** the operator cancels the create form
- **THEN** no API call is made and the list is unchanged.

### Requirement: Agent edit and delete actions
Each agent row SHALL offer edit and delete actions backed by
`updateAgent`/`deleteAgent`.

#### Scenario: Edit an agent
- **WHEN** the operator clicks edit on an agent row
- **THEN** the same form opens pre-filled and submitting calls `updateAgent`.

#### Scenario: Delete an agent
- **WHEN** the operator confirms delete on an agent row
- **THEN** `deleteAgent` is called and the row is removed from the list after
  refresh.

### Requirement: Provider management UI
The `/providers` page SHALL offer create, edit, delete, and test actions in
addition to the current read-only `PrimaryModelCard`.

#### Scenario: Add a provider
- **WHEN** the operator clicks "添加 Provider"
- **THEN** a form (name, type, base URL, key placeholder) calls `createProvider`
  and the provider appears in the model card / list.

#### Scenario: Test a provider
- **WHEN** the operator clicks "测试" on a provider
- **THEN** `testProvider` is called and the result (reachable / unreachable) is
  shown inline.

### Requirement: Schedule CRUD
The `/schedules` page SHALL support create, update, and delete of schedules via
the existing wrappers.

#### Scenario: Create a schedule
- **WHEN** the operator clicks "新建调度"
- **THEN** a form (cron, target, enabled) calls `createSchedule`.

#### Scenario: Delete a schedule
- **WHEN** the operator confirms delete on a schedule row
- **THEN** `deleteSchedule` is called and the row disappears.

### Requirement: Records detail and bulk actions
The `/records` page SHALL support detail view, single delete, batch delete, and
clear-all via `getRecord`/`deleteRecord`/`batchDeleteRecords`/`clearAllRecords`.

#### Scenario: Batch delete selected records
- **WHEN** the operator selects multiple records and clicks "批量删除"
- **THEN** `batchDeleteRecords` is called with the selected ids.

#### Scenario: Clear all records
- **WHEN** the operator confirms "清空全部"
- **THEN** `clearAllRecords` is called after an explicit confirmation dialog.

### Requirement: Source management
The `/sources` page SHALL support create, delete, connectivity test, and
credential management via the existing source wrappers.

#### Scenario: Test source connectivity
- **WHEN** the operator clicks "测试连接" on a source
- **THEN** `testSourceConnectivity` is called and the result is shown.

#### Scenario: Manage credentials
- **WHEN** the operator opens credential management on a source
- **THEN** `listSourceCredentials`/`storeSourceCredential`/`deleteSourceCredential`
  are available.

### Requirement: Plan run and health
The `/plans` page SHALL support create/edit/delete and run actions, plus a
health indicator via `getPlanHealth`.

### Requirement: Node detail and delete
The `/nodes` page SHALL support a detail view (events + stats) and delete via
`getNodeEvents`/`getNodeStats`/`deleteNode`.
