---
description: Headless Chrome never outlives the script that started it - use chrome.sh, or a CDP script that cleans up on every exit path.
apply: always
---

# Headless Chrome cleanup

A headless Chrome whose caller dies (a shell timeout, Ctrl-C, an exception) is not a child
of anything any more: it keeps rendering, sometimes for days, at full CPU.

1. **Screenshots and PDFs**: `kit/bundles/docs/scripts/chrome.sh pdf|screenshot`. It takes
   files or URLs, extra flags in `CHROME_EXTRA_FLAGS`, a hard limit in `CHROME_TIMEOUT`,
   and cleans up on every exit path. Never run the Chrome binary by hand.
2. **A script that drives Chrome over the DevTools protocol (CDP)** must:
   - spawn Chrome detached (its own process group) and kill the group in a `finally`;
   - handle SIGINT, SIGTERM and SIGHUP with the same cleanup;
   - time out every CDP call and the whole script (an unref'd timer);
   - delete its temporary profile directory.
3. Never leave a script that only cleans up on success. Test the failure paths: SIGTERM
   the script by the PID you started and check that no Chrome and no profile is left.
