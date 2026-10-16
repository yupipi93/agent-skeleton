# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private
reporting instead: on the repository page, open **Security > Report a vulnerability**.
Include what you found, how to reproduce it, and the impact you expect. You should get a
first answer within a week; fixes are released as soon as they are ready and credited
to you unless you prefer otherwise.

In scope: anything in this repository, for example a script that leaks a secret to argv,
a log or an error message; a hook that can be bypassed; the text guard missing a common
secret shape; the voice hub serving data beyond loopback without being asked to;
`bin/skeleton init` writing outside the generated paths.

## How the kit handles secrets

- **Never committed.** Credentials live in `~/.config/agent-skeleton/` (files 0600,
  directory 0700), outside the repository. `.env` files, `skeleton.local.toml`, `local/`
  and every generated path are git-ignored. Scripts warn when a config file is readable by
  others.
- **Never on a command line.** Shell scripts pass secrets to `curl` through `curl -K -` on
  stdin; Python scripts send requests in-process. Wizards read secrets at a hidden prompt
  and store them through `envfile.py set` on stdin.
- **Never in output.** Error messages are scrubbed of tokens, webhook URLs and API keys;
  the text guard reports a pattern label, never the matched text.
- **Never sent unreviewed.** Outbound text (tickets, PR bodies, chat) passes
  `kit/bundles/core/scripts/text-guard.sh` and the `outbound-text-safety` rule: the agent
  shows you the exact text and waits for your approval.
- **Never sent by tests.** The suite runs offline with a temporary `HOME`.

## If a secret leaked

1. **Rotate it first** (revoke the token or key at its provider). Deleting a commit does
   not un-publish a secret that was pushed.
2. Then remove it from the history if needed, and report the path that leaked it as
   above, so the kit can block it next time.
