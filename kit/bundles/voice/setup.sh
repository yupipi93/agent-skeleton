#!/bin/bash
# setup.sh: interactive configuration of the voice bundle, run by `bin/skeleton setup voice`.
# The wizard lives in scripts/notify-setup.sh (also runnable on its own).
set -u
exec /bin/bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/notify-setup.sh" "$@"
