# Private notifications

Run ntfy on the AMD server at **https://ntfy.144.24.135.201.sslip.io**. Caddy handles HTTPS; ntfy handles API and app authentication. The `arm-provisioning` topic carries ARM provisioning alerts.

| Account | Access |
| --- | --- |
| `iphone` | Read `arm-provisioning` |
| `arm-publisher` | Publish to `arm-provisioning` |
| Anonymous clients | No topic access |

Both accounts have the regular user role. Neither can access another topic or manage other accounts. Keep Authelia off this hostname: the native app needs ntfy authentication rather than browser sign-in redirects.

## Set up an iPhone

1. Install [ntfy from the App Store](https://apps.apple.com/app/ntfy/id1625396347). Allow notifications when prompted.
2. Open your normal SSH session to the AMD server and run:

   ```sh
   cat /opt/portfolio/.ntfy/iphone.txt
   ```

   This displays the server, topic, username, and generated password. Save the password in your password manager; keep the output out of screenshots, Git, and workflow logs.

3. In ntfy, open **Settings → Users → Add user**. Enter the service URL `https://ntfy.144.24.135.201.sslip.io`, username `iphone`, and the password from SSH. Save.
4. Return to the subscription list and tap **+**. Enter topic `arm-provisioning`, enable **Use another server**, and enter the same service URL. Tap **Subscribe**. Do not leave the server set to `https://ntfy.sh`.
5. In iPhone **Settings → Notifications → ntfy**, enable **Allow Notifications**, **Lock Screen**, **Banners**, and **Sounds**. If using Focus or Scheduled Summary, allow ntfy through Focus and keep it out of the summary for prompt alerts.
6. Lock the phone, then run this command in your AMD SSH session:

   ```sh
   python3 /opt/portfolio/scripts/ntfy-notify.py test
   ```

   Look for **ntfy test** on the lock screen. This tests delivery without running an Oracle launch request. The iPhone account cannot publish; send tests from SSH.

The server retains messages for seven days. A message already in the topic can confirm authenticated reading, but use a new test after subscribing to check background delivery.

## How iPhone delivery works

The ARM script publishes to ntfy over the server's loopback interface. ntfy stores the message and sends a wake-up request through `https://ntfy.sh` and Apple's push system. The phone then fetches the text directly from your HTTPS server using its saved credentials.

The upstream request contains a message ID and a hash of the topic URL, rather than the notification text. Keep `upstream-base-url: https://ntfy.sh` enabled for timely background alerts. See [ntfy's iOS delivery documentation](https://docs.ntfy.sh/config/#ios-instant-notifications).

## ARM notification policy

- **No host capacity:** keep retrying every five minutes, without sending notifications. Try the three fault domains in sequence.
- **Instance provisioning or running:** send **ARM instance claimed**, then remove the provisioning cron entry. Provisioning means Oracle accepted the instance; it does not guarantee the server is ready for SSH yet.
- **Authentication, SSH key, quota, or unexpected failures:** send **ARM provisioning needs attention**. Send each error category at most once per 24 hours after successful delivery. Capacity-only cycles clear the current error condition but preserve that cooldown; alternating error categories also keep their own cooldowns.
- **ntfy unavailable:** persist up to six pending alerts (one per error category plus one success), retain the cron entry, and retry at the start of the next run even if Oracle later returns only capacity failures. Label alerts delayed by a minute or more so you can distinguish earlier failures. An existing instance prevents additional launches. A failed instance lookup also prevents launch requests.

The notifier saves pending records before sending and saves delivery history after each successful response. A lost HTTP response or process crash after server acceptance can still cause a duplicate on retry; delivery is at least once, not exactly once. Keep `.ntfy/arm-notifications.json` during routine deployments.

Messages use fixed summaries. Raw Oracle output, OCIDs, credentials, and private keys stay out of notifications. Inspect `~/stack-latest-job.json` and `~/stack-summary.log` over SSH for details. The original provisioning parameters stay at `VM.Standard.A1.Flex`, 2 OCPUs, and 12 GB RAM.

`/home/opc/apply-stack.sh` launches `deploy/arm/apply-stack.sh` from this checkout. Keep the existing identifiers in `/home/opc/ampere-env.sh` and OCI credentials in their private locations. Use `/home/opc/ampere-a1.pub` for the dedicated ARM public key. Do not pass the AMD `authorized_keys` file: it contains SSH entry options for the restricted GitHub Actions key, which Oracle's instance key input rejects. Connect to the new ARM instance with the matching ARM private key on your PC.

## Install on another server

1. Point an ntfy hostname at the server and set `NTFY_DOMAIN` in its private `.env.production`. Set `NTFY_UID` and `NTFY_GID` if the checkout owner is not `1000:1000`. Allow inbound TCP 80/443 for Caddy.
2. Run these commands from the checkout as its owner:

   ```sh
   python3 scripts/setup-ntfy.py prepare
   python3 scripts/setup-ntfy.py validate
   sudo docker compose --env-file .env.production -f compose.production.yaml up -d --no-deps --force-recreate --wait ntfy
   python3 scripts/setup-ntfy.py configure
   sudo docker compose --env-file .env.production -f compose.production.yaml up -d --no-deps caddy
   python3 scripts/setup-ntfy.py check
   ```

   The first start creates the database with deny-all access. Configuration then creates the two regular accounts and grants topic permissions. Repeating setup preserves their passwords.

3. Copy only your ARM **public** key to `/home/opc/ampere-a1.pub`. Keep the existing OCI environment and credentials private. Back up the original `/home/opc/apply-stack.sh`, then replace it with:

   ```sh
   #!/usr/bin/env bash
   exec bash /opt/portfolio/deploy/arm/apply-stack.sh
   ```

   Keep its executable permission and the existing five-minute cron entry. Review the instance name, paths, and shape in the repository script before enabling it for another account. Deploying the portfolio does not create or re-enable the provisioning cron job.

After setup, the normal portfolio deployment prepares ntfy files, validates the candidate settings in an offline disposable container, recreates ntfy to apply `server.yml` changes, reconciles access, and tests HTTPS and topic permissions before app image cleanup. The validation container uses temporary databases and publishes no ports. Recreation briefly interrupts ntfy; credentials, cached messages, and notification state persist. Merge all the corresponding local files into `main` before the next deployment; the deployment script rejects conflicting server edits.

## Private storage and maintenance

`.ntfy/` is ignored by Git. It contains the databases in `data/`, the two account credential files, the iPhone login sheet, and notification state. Use the [private-state backup and restore guide](BACKUPS.md) to archive it with the other services. The helper stops ntfy and locks ARM/notifier writers so SQLite, credentials, pending alerts, and cooldown timestamps stay together. Never copy private data into the repository or an image.

ntfy runs as UID/GID 1000 by default, with a read-only root filesystem, a 128 MiB memory cap, rotating logs, and a seven-day message cache. Its API port binds only to `127.0.0.1:2586`; Caddy exposes HTTPS publicly. Attachments, email, calls, and public signup stay disabled. The notification network connects only Caddy and ntfy.

Use these commands in the AMD SSH session:

```sh
cd /opt/portfolio
sudo docker compose --env-file .env.production -f compose.production.yaml ps ntfy
sudo docker compose --env-file .env.production -f compose.production.yaml logs --tail 50 ntfy
python3 scripts/setup-ntfy.py check
python3 -m unittest discover -s tests -p 'test_*.py'
```

The tests fake Oracle commands and notification delivery; they never provision a real instance. A successful server test cannot confirm that iOS displayed an alert, so complete the locked-phone test too.

If connection alerts repeat within 24 hours, check that the notifier includes the cooldown fix and that `.ntfy/arm-notifications.json` remains writable and persists between runs. Do not delete it to silence alerts; that resets suppression. Read the category and timestamps over SSH, keeping credentials private. Ordinary no-capacity results never generate a new alert.

If messages arrive only while the app is open, check iOS notification permissions, the saved server URL and user, ntfy logs for upstream errors, and the `upstream-base-url` setting. Avoid sharing logs publicly without reviewing them. If the AMD public IP changes, update `NTFY_DOMAIN`, redeploy, and update both the server credentials entry and subscription URL on the phone.

Before starting a new, deliberate ARM provisioning cycle after a prior success, archive `.ntfy/arm-notifications.json` and review existing Oracle instances. This state suppresses duplicate success notifications. Do not re-enable cron just to test alerts; use `ntfy-notify.py test`.
