# Use Appliance-First Local Owner Authentication

Status: accepted

OpenCLI's default deployment is a personally operated appliance running on a workstation, NAS,
or capable home router. The first human-facing security ceremony is therefore device claim, not
organization sign-in. A new installation presents a one-time claim code, creates one local owner,
establishes an HTTP-only server session, and then uses that local account for ordinary console
access. The internal Workspace and RBAC models remain authorization boundaries; they are not the
default login concept shown to a personal operator.

OIDC remains supported as an optional advanced capability for deployments that deliberately enable
team or enterprise identity. It must not block first use, appear as an error when unconfigured, or
remove the last usable local owner. Passkeys, TOTP, trusted-device approval, and vendor-assisted
remote access are post-claim enhancements rather than prerequisites for an offline-capable local
installation.

Human and machine credentials stay separate:

- Local owner sessions authenticate browser HTTP requests and are stored only as opaque,
  revocable server-side sessions with HTTP-only cookies.
- `API_AUTH_TOKEN` continues to authenticate Agents, MCP, CLI, WebSocket, and service-to-service
  traffic. It is never requested by the ordinary browser login form or stored in browser storage.
- `BOOTSTRAP_ADMIN_TOKEN` is a break-glass migration and recovery credential. It is not a daily
  login mechanism and is hidden from the normal login path.
- The one-time device claim code authorizes only the unclaimed-to-active transition. A database
  uniqueness constraint and transaction ensure that concurrent callers cannot create two first
  owners; after the first claim, the code has no effect.

The persistent Setup Center decision remains intact. Device claim is a one-time ownership and
security boundary, while the Setup Center continues to report and repair models, Connections,
Plugins, delivery channels, and execution resources throughout the appliance lifetime.

Consequences:

- New installations open on "Set up this device" and create a local owner before entering Studio.
- Existing installations keep OIDC and recovery access during migration. After the operator adds a
  fresh claim code to deployment configuration, they can create the local owner without
  invalidating OIDC subjects, Workspace memberships, data volumes, or Fleet clients.
- Unsafe cookie-authenticated mutations require an explicit same-origin CSRF header in addition to
  `SameSite` cookie policy.
- noVNC is not made public merely to improve LAN convenience; it requires an authenticated console
  proxy before it can be safely exposed beyond loopback.
- The current Studio Workspace and governance Workspace models are not merged by this decision.
  Appliance-first presentation may hide that distinction, but data ownership changes require a
  separate migration.

Rejected alternatives:

- Automatically inserting the Bootstrap token into the page retains a permanent bearer secret and
  only hides the underlying problem.
- Trusting all LAN clients without login is unsafe because the API can reach browser profiles,
  platform cookies, and the Docker control plane.
- Making OIDC the default requires an external identity provider and contradicts offline-capable,
  single-owner installation.
