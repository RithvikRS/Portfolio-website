#!/usr/bin/env bash
set -uo pipefail
umask 077
source /home/opc/ampere-env.sh
OCI_BIN=/home/opc/bin/oci
INSTANCE_NAME=vantize-ampere-a1
PUBLIC_KEY=/home/opc/ampere-a1.pub
NOTIFIER=/opt/portfolio/scripts/ntfy-notify.py
RESULT=/home/opc/stack-latest-job.json
SUMMARY=/home/opc/stack-summary.log

exec 200>/tmp/ampere-launch.lock
flock -n 200 || exit 0

log() { printf '%s: %s\n' "$(date -u +%FT%TZ)" "$*" >> "$SUMMARY"; }
notify() { python3 "$NOTIFIER" "$@" 2>> "$SUMMARY"; }
stop_after_success() {
    log "$INSTANCE_NAME is $1. No further launch requests will be sent."
    # Keep polling the existing instance if ntfy is temporarily unavailable.
    if notify success "$1"; then
        local entries
        entries="$(crontab -l)" || return 1
        printf '%s\n' "$entries" | awk '!/^[^#]*\/home\/opc\/apply-stack\.sh([[:space:]]|$)/' | crontab -
    fi
}

# A failed list request must never be interpreted as an empty instance list.
if ! "$OCI_BIN" compute instance list --compartment-id "$COMPARTMENT_ID" \
    --display-name "$INSTANCE_NAME" \
    --query 'data[?"lifecycle-state"!=`TERMINATED` && "lifecycle-state"!=`TERMINATING`] | [0]."lifecycle-state"' \
    --raw-output > "$RESULT" 2>&1; then
    log 'Instance lookup failed; skipping launch requests.'
    notify error "$RESULT" || true
    exit 1
fi
EXISTING_STATE="$(cat "$RESULT")"
case "$EXISTING_STATE" in
    PROVISIONING|RUNNING) stop_after_success "$EXISTING_STATE"; exit 0 ;;
    ''|None|null) ;;
    *)
        printf 'An existing ARM instance has an unexpected lifecycle state; inspect the Oracle console.\n' > "$RESULT"
        log 'Existing instance requires attention; skipping launch requests.'
        notify error "$RESULT" || true
        exit 1 ;;
esac

if [[ ! -r "$PUBLIC_KEY" ]]; then
    printf 'Invalid ssh public key: dedicated ARM public-key file is missing.\n' > "$RESULT"
    notify error "$RESULT" || true
    exit 1
fi

for FD in FAULT-DOMAIN-1 FAULT-DOMAIN-2 FAULT-DOMAIN-3; do
    log "Requesting $INSTANCE_NAME in $FD."
    if "$OCI_BIN" compute instance launch \
        --compartment-id "$COMPARTMENT_ID" --availability-domain "$AD" --fault-domain "$FD" \
        --subnet-id "$SUBNET_ID" --image-id "$IMAGE_ID" --shape VM.Standard.A1.Flex \
        --shape-config '{"ocpus": 2, "memoryInGBs": 12}' --display-name "$INSTANCE_NAME" \
        --assign-public-ip true --ssh-authorized-keys-file "$PUBLIC_KEY" > "$RESULT" 2>&1; then
        # Successful submission is enough to stop launching; the next cron run can confirm state.
        STATE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("data",{}).get("lifecycle-state",""))' "$RESULT")"
        case "$STATE" in
            PROVISIONING|RUNNING) stop_after_success "$STATE"; exit 0 ;;
        esac
        log 'Launch returned an unexpected response; check existing instances on the next run.'
        notify error "$RESULT" || true
        exit 1
    fi
    if grep -qiE 'out of (host )?capacity' "$RESULT"; then
        log "$FD has no capacity."
    else
        log 'Launch needs attention; skipping further fault domains this cycle.'
        notify error "$RESULT" || true
        exit 1
    fi
    sleep 2
done
notify clear || true
