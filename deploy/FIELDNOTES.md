# Blog and learning notebook

Stage 3 adds **Fieldnotes**, a browser editor inside the existing Node app. It uses the same Authelia administrator login as the dashboard. There is no additional container, database service, or password. This keeps the Oracle 1 GB VM's footprint small.

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

Titles and tags are searchable in the library, along with Markdown content. Public search sees only published versions. Use filters for posts, notes, drafts, published writing, or trash. The public pages begin empty; no sample personal articles are published for you.

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

Writing is **runtime data**, separate from Git and the image. A Git push, image build, redeployment, restart, or ordinary Compose down/up preserves it. `.notes/` is ignored by Git, excluded from Docker builds, and inaccessible through the public-file allowlist. Do not delete that directory or replace it with an empty backup. No image uploads, embeds, comments, scheduled publication, WYSIWYG formatting, or multi-user editing are included in this stage.

Local `compose.yaml` explicitly disables writing storage and authenticated editing; it previews the public pages with empty collections. Direct Node development can set `NOTES_DATA_DIR` to a private directory, but the editor still requires the trusted authentication integration. Do not enable a public authentication bypass to preview it.

## Shared login and Caddy

`/admin/notes/` and `/admin/notes/api/*` use the existing protected `/admin/*` Caddy handler and Authelia access rule. Caddy removes incoming identity headers and forwards verified ones. Node independently checks the exact proxy peer, administrator username, and `admins` group. Mutations require JSON, the exact public Origin, and a custom request header; cross-site requests are rejected. Private responses are never cached and are marked noindex.

`/blog/*` and `/learn/*` use the existing public fallback to `app:4173`. They read only the published snapshot, never the draft. All writing responses use `Cache-Control: no-store` so unpublishing applies to subsequent requests immediately. HTML is sanitized after Markdown parsing; scripts, styles, images, and embedded widgets are excluded. No external image fetch or server-side URL fetch is performed.

There are **no new Caddy blocks, DNS records, certificates, or OAuth clients** for this stage. A new domain is derived from production `DOMAIN` through `PUBLIC_ORIGIN`; redeploy after changing it. If adding a separate future application, follow the [Caddy guide](DOCKER.md#caddy-changes-and-new-sites).

## Redeploy

Commit local changes, merge `V2` into `main`, push, then run inside Oracle SSH:

```sh
bash /opt/portfolio_redeploy.sh
```

The script prepares `.notes/`, builds the Node app and dependencies, runs checks/tests, reconciles the existing services, and verifies both public writing pages and the signed-out export gate. It preserves existing writing. Sign in again because Authelia is recreated. Stage 3 files were copied to the server before the local commit/merge; merge matching files before the next normal pull, or the script will stop on differences.

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

To restore, stop the affected services, preserve the current directories as a separate recovery point, extract the verified archive into a staging directory, and restore the matching private directories with owners/modes intact. Do not overlay a library backup onto newer files: entries absent from the backup could otherwise remain published. Replace the directory as a unit while the app is stopped. Start services with the compatible source/image version and check public/private visibility. Never mix an old Authelia encryption key with an unmatched database.

The pre-stage-3 recovery point is `/home/opc/.config/portfolio-deploy/fieldnotes-stage3-DtZPMrmu/`, with source and consistent auth/Portainer archives. The prior image is `rithvik-portfolio:before-fieldnotes-stage3`. It predates writing data and cannot restore writing created afterward. The same directory also contains `private-after.tar.gz`, a consistent backup of the completed integration including the private getting-started note; the temporary verification entry is archived separately. These are manual recovery points; scheduled backups have not been configured.

## Checks and troubleshooting

- A signed-out visit to `/admin/notes/` or its export endpoint must redirect to login or return 401. Forged identity headers must not bypass login.
- A saved private draft must not appear in public search or at its article URL. Save-after-publish changes stay private until Publish update.
- After saving, restart the app to verify the draft persists. Do not edit `.notes/` files while the app runs; the process holds its own in-memory snapshot.
- For storage errors, inspect app logs and directory ownership. Preserve text in the editor and download it before troubleshooting.
- For a 409 conflict, copy the local text and reload the newer server version. Repeating the same stale save will not resolve it.
- Monitor this small VM with `free -m` and `sudo docker stats --no-stream`. The DNF cache timer mitigation from the earlier outage remains in effect.

Implementation references: [Marked](https://marked.js.org/) and [sanitize-html](https://github.com/apostrophecms/apostrophe/tree/main/packages/sanitize-html). The lockfile pins Marked 18.1.0 and sanitize-html 2.18.0; review updates before changing them.

Deployment validation on 8 October 2026: all 19 app tests passed locally and inside the production image; live shared login and full Portainer OAuth remained working. Fieldnotes passed signed-out/forged-header rejection, CSRF rejection, private-draft exclusion, public publication and draft isolation, unpublish, trash/restore, export, and restart persistence. Browser save/preview/publish/unpublish checks passed. A private getting-started note remains in the editor; public collections contain no test or sample articles.
