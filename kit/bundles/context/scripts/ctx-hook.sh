#!/usr/bin/env bash
# ctx-hook.sh: prompt_submit hook of the context bundle. Thin wrapper so the rendered
# hook command stays a single script path: runs `ctx.py hook --client <tool>`.
# Never blocks a prompt: ctx.py exits 0 on any error.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/ctx.py" hook "$@"
