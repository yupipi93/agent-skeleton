/* Open in editor browser.
 *
 * A shell script cannot run an editor command, but it can open a URI:
 *   open "cursor://agent-skeleton.editor-browser-open/open?url=<encoded url>"
 * The editor routes that URI here and we show the page in its own browser:
 *   1. Cursor: workbench.action.openBrowserEditor (a browser tab, file:// included).
 *   2. VS Code: simpleBrowser.show (http/https only).
 *   3. Otherwise the system browser.
 * Installed by kit/bundles/docs/scripts/install-editor-browser.sh. */
'use strict';
const vscode = require('vscode');

async function show(url) {
  const commands = await vscode.commands.getCommands(true);
  if (commands.includes('workbench.action.openBrowserEditor')) {
    await vscode.commands.executeCommand('workbench.action.openBrowserEditor', { url });
    return;
  }
  if (/^https?:/i.test(url) && commands.includes('simpleBrowser.show')) {
    await vscode.commands.executeCommand('simpleBrowser.show', url);
    return;
  }
  await vscode.env.openExternal(vscode.Uri.parse(url, true));
}

function activate(context) {
  context.subscriptions.push(vscode.window.registerUriHandler({
    handleUri(uri) {
      if (uri.path !== '/open') return;
      const url = new URLSearchParams(uri.query).get('url');
      if (!url || !/^(https?|file):/i.test(url)) {
        vscode.window.showWarningMessage('editor-browser-open: missing or unsupported url');
        return;
      }
      show(url).catch(e => vscode.window.showErrorMessage('editor-browser-open: ' + e.message));
    },
  }));
}

function deactivate() {}

module.exports = { activate, deactivate };
