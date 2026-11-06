# Accounts, passwords, and notes

Open **Service access** in the portfolio admin dashboard. Sign in as the infrastructure owner with MFA. Create a separate account for each person, save its generated password at creation, and give it privately to the account owner. A new account receives only the services you select. The console preserves administrator accounts and restricts grant changes to **Outline notes** and **Password vault**.

## Onboard a family member or friend

1. Open [Service access](https://rithvik.ddns.net/admin/access/) and create the account with the person's own email address. Select the services they need.
2. Give them their username, initial password and the direct link to their service through a private channel. The infrastructure dashboard is for administrators.
3. Have them start sign-in at that service and register their own authenticator at the Authelia prompt. Authelia writes enrollment messages to the manager's private `.auth/data/notifications.txt`. Verify the recipient and relay only their current enrollment message privately. Each person scans their own QR and enters a fresh code.
4. To review or change access later, return to **Service access**, update the person's grants and save. Use the offboarding steps below when removing access.

## First sign-in

Open the notes workspace as the owner before granting notes access to anyone else. Outline assigns the first sign-in to the initial workspace administrator. In workspace settings disable public sharing, leave default member permissions restricted, and choose who can invite others. Use Personal documents for individual work and restricted collections or explicit document invitations for collaboration. Test view, edit, and revocation with separate accounts. Server operators can access stored note contents.

Signing out of Outline returns you to its sign-in page. Select Authelia to sign in again with your portfolio session. On the web vault's first screen, enter the email listed on your Authelia account in Service access.

Open the vault and choose enterprise SSO using the same Authelia account, then set a unique master password to unlock the personal vault. The web vault uses SSO-only signup behind an MFA-protected browser proxy. This setup supports browser access. Keep personal recovery material offline and test an encrypted export using a disposable item before storing important secrets. Each user controls their own vault. Access grants authorize login; the owner console cannot unlock another person's vault.

Open [Outline](https://notes.144.24.135.201.sslip.io/) or the [web vault](https://vault.144.24.135.201.sslip.io/). Each browser first visits the portfolio Authelia issuer. A valid MFA session can satisfy both the edge proxy and the application's own OIDC client. Each service uses dedicated client credentials and an exact callback. Native iPhone ntfy keeps its own read-only account.

## Offboarding

Clear the person's service grants, then save. To block all future logins, also disable the account. The file backend watches the directory and refreshes identity information every minute. Each edge proxy holds its own session for up to five minutes. End active application sessions and remove workspace membership, sharing links, API keys, and integrations inside the affected application. Already opened connections can outlive a browser session. Someone who previously decrypted or exported data may retain a copy.

## Deployment and recovery

Run `python3 scripts/setup-family-services.py` on the manager as the portfolio checkout owner before the first deployment. The helper migrates the original account list only on first initialization and creates private client keys in `.secrets/family/` and matching hashes under `.auth/secrets/`. The live user directory is `.auth/secrets/directory/users.yml`. Keep its manager bind directory owner-only. The access console mounts only this directory and uses an unpublished overlay shared with Caddy.

Pin PostgreSQL, Outline attachments and Vaultwarden SQLite/files to the approved Ampere worker. Create `/srv/swarm/notes_db`, `/srv/swarm/outline`, `/srv/swarm/notes_cache`, and `/srv/swarm/vaultwarden` on its mounted application disk before deployment. PostgreSQL requires its container data owner, Outline uses UID 1001, and Vaultwarden uses its container data owner. Use the existing worker storage labeling and restore procedure. Redis persists its queue on the same worker and uses the private backend overlay.

Run the full private cluster backup after configuration changes. Restore the manager's directory, matching OIDC hashes and secrets, application encryption keys, the PostgreSQL data directory, attachments, and Vaultwarden data including its RSA keys. Keep a coordinated worker snapshot with writers stopped. Rehearse restoration offline before relying on it. Use a member-only account to test private notes and vault isolation after a restore.
