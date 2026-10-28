# GaoSeafood production release

Production is `/opt/1panel/apps/xboard/compose.yaml`, service `xboard`.
These files contain no credentials. Installed workers are root-owned; polling does
not install or execute a replacement worker from a newly fetched commit.

## Entry points

* `source-deploy.yml`: pull requests build AMD64 and ARM64 and run release-worker
  safety checks without production credentials. A push to `master` builds the
  exact commit, joins the private Tailscale network with OIDC, then connects to
  the VPS through a project-specific forced SSH command. The root-owned server
  worker receives that exact SHA and performs the existing backup, deployment,
  health-check, and rollback flow.
* `xboard-source-update.timer`: the existing five-minute source poller remains a
  fallback until the first GitHub Actions deployment succeeds and the running
  release is verified. Disable the timer after that handoff; keep the service
  and worker available for a deliberate recovery if GitHub Actions becomes
  unavailable.

Both entry points invoke the same root-owned worker and share
`/var/lib/xboard-release/release.lock`, so they cannot replace each other's
release concurrently. The GitHub workflow only deploys on `master`; the
`xboard-production` GitHub Environment must also restrict deployments to
`master`. The Tailscale credential is scoped to `auth_keys` and tagged
`tag:tingjian-ci`, whose saved network rule permits SSH to the VPS on TCP/22.

## Install after review

Back up the existing dispatcher, sudoers file, authorized-keys file, worker,
and units first. Install
`xboard-release.py` to `/usr/local/libexec/xboard-release.py` (root, 0755),
`xboard-auto-deploy` to `/usr/local/sbin/xboard-auto-deploy` (root, 0755), and the
service/timer to `/etc/systemd/system/` (root, 0644). Add the XBoard case to the
shared GitHub Actions dispatcher and sudoers allowlist, then install
`github-actions-deploy-xboard` as a root-owned forced-command wrapper. Add one
XBoard-only public key to the existing `tingjian-deploy` account, constrained to
the Tailscale address range and that wrapper. Never place the private key in this
repository. Set the actual public HTTPS site URL in
`/etc/github-deploy/xboard-public-url` (root, 0644). The public URL is not a
credential. The existing source mirror must point to
`https://github.com/GaoSeafood/Xboard.git`.

Create the GitHub Environment `xboard-production`, add variables
`TS_OAUTH_CLIENT_ID` and `TS_AUDIENCE`, store the matching private key as
`DEPLOY_SSH_KEY`, and restrict deployments to the `master` branch. The Tailscale
trust credential must match the GitHub OIDC subject for `GaoSeafood/Xboard` and
`xboard-production`.

After merging the reviewed source, verify that GitHub Actions deploys the exact
`master` SHA and that the public release marker and health checks match it. Only
then disable the fallback timer with `systemctl disable --now
xboard-source-update.timer`. Do not stop or remove it before the Actions release
passes verification. To restore polling during a GitHub outage, explicitly
enable and start the timer after checking that no release is running.

## Release guarantees

* A webhook builds its exact SHA, which must still belong to `master`. An older
  request cannot replace a newer running revision. The timer selects the current
  `master` once per attempt; it does not change the target midway through a build.
* Changed files are calculated against the running image's revision. Database,
  migration, schema, and `.env` changes stop for manual review. Documentation-only
  commits still advance the image revision, so a missed earlier application
  change cannot be hidden by a later workflow or documentation commit.
* Before replacing a container, the worker creates a root-only checkpoint in
  `backups/release-TIMESTAMP-PREVIOUS_SHA`: a consistent SQLite online backup with
  an integrity check, `.env`, Compose, and immutable previous image metadata.
  Each previous image gets its own checkpoint tag and is also retained as
  `localhost/github-deploy/xboard:rollback`. Never print or commit backup contents.
* The permanent Compose image is updated to the SHA tag, so a later 1Panel
  recreation keeps the selected release. Only the five known legacy theme mounts
  under `./releases/` are removed. Configuration/data/plugin mounts remain.
  Built-in theme templates and assets subsequently come from the same image.
* Acceptance requires the container image ID and revision, Octane/Horizon/Redis/
  Caddy process health, local and public HTTP, matching `/release.json`, rendered
  branded theme, and its referenced JS/CSS/images. Checks repeat after 15 seconds.
* Failed activation restores the old Compose with the previous immutable image
  ID and checks local/public HTTP. Database contents are not automatically rolled
  back, to preserve writes made during the release. Schema changes are blocked.

## Operations and failure recovery

`/var/lib/xboard-release/status.json` contains only release metadata, not customer
data. A failed SHA is not retried by every timer tick; investigate, then explicitly
run `/usr/local/sbin/xboard-auto-deploy --poll --retry`. A newer SHA gets its own
attempt. An interrupted build marked `building` can be retried by a later tick.
Release entry points are serialized; the Actions client allows 80 minutes.

For an emergency rollback, stop the timer and confirm no release is running.
Restore the checkpoint Compose but pin `services.xboard.image` to the checkpoint's
`previousImage` ID, then recreate only `xboard` and verify the public site. Restore
database/configuration backups only as a separate explicitly reviewed recovery.
Never prune checkpoint image tags or remove backups as part of normal deployment.

GitHub incident confirmed 2026-10-27: the dispatch endpoint returned HTTP 422,
`Actions has been disabled for this repository`, while Actions permissions were
enabled and workflow state active. Re-enabling the workflow did not resolve it.
The particular enforcement reason is not exposed by that API; the owner must
obtain it through GitHub Support. No support message is sent by these tools.
