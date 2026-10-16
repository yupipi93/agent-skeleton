/* The hub tab that was already open is playing the note: this tab is not needed.
 * Browsers let a script close a tab that has a single history entry, which is what a
 * link opened from another app gets. Where that is refused the page just says so. */
'use strict';
try { window.close(); } catch { /* not closable */ }
