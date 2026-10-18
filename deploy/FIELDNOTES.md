# Blog and learning notebook

Use **Fieldnotes** to write blog posts and learning notes in your browser. Sign in with the same administrator account as the dashboard. Fieldnotes runs inside the Node app and stores writing in private files, with no additional container or database service.

| Page | Address | Visibility |
| --- | --- | --- |
| Writing editor | [Fieldnotes](https://rithvik.ddns.net/admin/notes/) | Administrator only |
| Blog | [Blog](https://rithvik.ddns.net/blog/) | Published blog posts only |
| Learning notebook | [Learning notes](https://rithvik.ddns.net/learn/) | Published learning notes only |

## Write and publish

1. Open the dashboard and select **Open Fieldnotes**. Your existing shared session is reused.
2. Select **New entry**. Choose Blog post or Learning note, then add a title, optional summary, and up to eight comma-separated tags.
3. Write in Markdown. Headings, emphasis, links, lists, task checkboxes, tables, and fenced code blocks work. Select **Preview** to see the sanitized result.
4. Select **Save draft**, or press Ctrl+S / Cmd+S. Saving is manual; wait for the saved confirmation before closing the tab. Unsaved content lives only in the current tab, with a navigation warning. It is not automatically stored in the browser or server.
5. Select **Publish entry**, then confirm. Blog posts appear under `/blog/`; notes under `/learn/`. Both types start private, and publishing either makes it visible to everyone.
6. After publishing, **Save draft** keeps subsequent changes private. **Publish update** replaces the public version with the saved draft. The first publication date stays the same. Changing the entry type and publishing moves it to the other collection; its old collection URL stops working.

Search the library by title, tag, or Markdown content. Use filters for posts, notes, drafts, published writing, or trash. Public search includes only published versions; publish an entry to add it to a public collection.

**Unpublish** removes the public version immediately and keeps the draft. **Move to trash** also unpublishes it. Use the Trash filter and **Restore draft** to recover a private draft. There is no permanent-delete button. Previously downloaded copies and search-engine caches cannot be recalled.

The editor detects conflicting saves from another tab and refuses to overwrite newer writing. Copy or download your unsaved text, then reload the entry and reconcile it. If your session expires, keep the editor tab open, sign in through Overview in another tab, and retry the save. Do not refresh a tab containing unsaved work.

## Files and persistence

| File or directory | Purpose |
| --- | --- |
| `server/notes.mjs` | Public pages, private API, editor HTML, sanitized Markdown |
| `server/notes-store.mjs` | Validation, atomic writes, revisions, draft/public snapshots |
| `js/notes.js`, `css/notes.css` | Browser editor and writing-page styling |
| `tests/notes.test.mjs` | Authorization, CSRF, isolation, sanitization, conflicts and persistence |
| `scripts/setup-notes.py` | Creates/verifies private storage without resetting entries |
| `/opt/portfolio/.notes/` | One JSON file per entry, including draft, published snapshot, and trash state |

Production binds `.notes/` to `/writing` and sets `NOTES_DATA_DIR=/writing`. The directory is mode 700, owned by UID/GID 1000; entry files are mode 600. Node runs as UID/GID 1000. The rest of its container remains read-only. The setup helper refuses mismatched ownership or a symlink. On a different host, explicitly align the deployment user and Node container ownership before using this configuration.

The store serializes writes in one process, checks revision numbers, writes a temporary file, syncs it, and atomically renames it. Linux also syncs the directory. On startup, malformed data stops the app rather than silently losing entries. Run one app instance per storage directory; shared writers/replicas are unsupported. The library is bounded to 250 entries including trash, 64 KiB of UTF-8 Markdown per entry, 140-character titles, 320-character summaries, and eight 32-character tags.

Keep writing in `.notes/` as **runtime data**, separate from Git and the image. A Git push, image build, redeployment, restart, or ordinary Compose down/up preserves it. Keep the directory out of Git, Docker builds, and the public-file allowlist. Do not delete it or replace it with an empty backup. Use Markdown and manual publishing; the editor does not support image uploads, embeds, comments, scheduled publication, WYSIWYG formatting, or multi-user editing.

Local `compose.yaml` explicitly disables writing storage and authenticated editing; it previews the public pages with empty collections. Direct Node development can set `NOTES_DATA_DIR` to a private directory, but the editor still requires the trusted authentication integration. Do not enable a public authentication bypass to preview it.

## Shared login and Caddy

`/admin/notes/` and `/admin/notes/api/*` use the existing protected `/admin/*` Caddy handler and Authelia access rule. Caddy removes incoming identity headers and forwards verified ones. Node independently checks the exact proxy peer, administrator username, and `admins` group. Mutations require JSON, the exact public Origin, and a custom request header; cross-site requests are rejected. Private responses are never cached and are marked noindex.

`/blog/*` and `/learn/*` use the existing public fallback to `app:4173`. They read only the published snapshot, never the draft. All writing responses use `Cache-Control: no-store` so unpublishing applies to subsequent requests immediately. HTML is sanitized after Markdown parsing; scripts, styles, images, and embedded widgets are excluded. No external image fetch or server-side URL fetch is performed.

Reuse the existing Caddy routes and shared login for Fieldnotes. Set the domain through production `DOMAIN` and redeploy after changing it. If adding a separate application, follow the [Caddy guide](DOCKER.md#caddy-changes-and-new-sites).

## Redeploy

Commit and push changes to `V2`, then merge its PR into `main` to start the automatic deployment. Follow the run in GitHub Actions. For a manual deployment, run inside Oracle SSH:

```sh
bash /opt/portfolio_redeploy.sh
```

Use the script to prepare `.notes/`, build the app, run checks, and update services while preserving writing. It checks both public writing pages and the signed-out export gate. Sign in again after Authelia restarts. Reconcile any server files that differ from `origin/main` before retrying a deployment.

## Export, backup, and restore

**Download Markdown** saves the current editor text, including unsaved changes. **Export library** downloads JSON containing all saved drafts, published versions, and trash. Keep that export private. It is a data export, not a complete server backup. There is no browser import tool in this version; a full restore uses the original `.notes/` files.

For a consistent complete private-state archive on Oracle, briefly stop the three services that write private state. This also pauses the public app:

```sh
cd /opt/portfolio
umask 077
backup=$(mktemp -d /home/opc/.config/portfolio-deploy/private-state-XXXXXXXX)
dc() { sudo docker compose --env-file .env.production -f compose.production.yaml "$@"; }
dc stop app auth portainer
sudo tar -czf "$backup/private-state.tar.gz" .env.production .auth .portainer .notes
sudo chmod 600 "$backup/private-state.tar.gz"
dc start app auth portainer
dc ps
```

If the archive command fails, start the services again before troubleshooting. Also preserve the matching source version and Caddy named volumes for a full migration. Copy the private archive to separate, secure storage; on-instance backups alone do not survive loss of the VM.

To restore, stop the affected services and preserve the current directories as a separate recovery point. Check the archive's contents, extract it into a staging directory, and restore the matching private directories with owners/modes intact. Do not overlay a library backup onto newer files: entries absent from the backup could otherwise remain published. Replace the directory as a unit while the app is stopped. Start services with the compatible source/image version and check public/private visibility. Never mix an old Authelia encryption key with an unmatched database.

For an earlier Fieldnotes recovery point, inspect `/home/opc/.config/portfolio-deploy/fieldnotes-stage3-DtZPMrmu/`. Use `private-after.tar.gz` for the private state from that backup. The image `rithvik-portfolio:before-fieldnotes-stage3` predates writing support and cannot restore later writing. Create fresh private-state backups regularly; manual recovery archives do not update automatically.

## Checks and troubleshooting

- A signed-out visit to `/admin/notes/` or its export endpoint must redirect to login or return 401. Forged identity headers must not bypass login.
- A saved private draft must not appear in public search or at its article URL. Save-after-publish changes stay private until Publish update.
- After saving, restart the app to verify the draft persists. Do not edit `.notes/` files while the app runs; the process holds its own in-memory snapshot.
- For storage errors, inspect app logs and directory ownership. Preserve text in the editor and download it before troubleshooting.
- For a 409 conflict, copy the local text and reload the newer server version. Repeating the same stale save will not resolve it.
- Monitor memory with `free -m` and `sudo docker stats --no-stream`. Follow the [AMD memory guidance](DOCKER.md#manage-memory-on-the-amd-server) when configuring package maintenance.

Implementation references: [Marked](https://marked.js.org/) and [sanitize-html](https://github.com/apostrophecms/apostrophe/tree/main/packages/sanitize-html). The lockfile pins Marked 18.1.0 and sanitize-html 2.18.0; review updates before changing them.
