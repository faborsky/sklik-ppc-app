#!/bin/bash
# OPTIONAL: run the Sklik PPC App with tokens resolved by the 1Password CLI.
#
# You do not need this script. Plain tokens in .env + ./run.sh work exactly as
# before. This is an opt-in alternative for people who keep their tokens in
# 1Password: .env then holds secret references such as
#
#     SKLIK_API_TOKEN=op://<vault>/<item>/<field>
#
# and `op run` resolves them into the environment of this one process — the
# long-lived token is never written to disk. Everything after the script name
# is passed to ./run.sh unchanged:
#
#     ./run-op.sh campaigns --json
#
# Several 1Password accounts signed in? Tell `op` which one to use — this
# script does not pick one for you:
#
#     OP_ACCOUNT=my.1password.com ./run-op.sh campaigns
#
# Details and gotchas: README.md, section "Tokeny ve správci hesel".

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

if ! command -v op > /dev/null 2>&1; then
    echo "ERROR: 1Password CLI (op) not found. Install it" \
         "(https://developer.1password.com/docs/cli/get-started/) or use" \
         "./run.sh with plain tokens in .env." >&2
    exit 127
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "ERROR: $SCRIPT_DIR/.env not found. Run ./setup.sh first, then put" \
         "your op:// references into .env (see .env.example)." >&2
    exit 1
fi

exec op run --env-file="$SCRIPT_DIR/.env" -- "$SCRIPT_DIR/run.sh" "$@"
