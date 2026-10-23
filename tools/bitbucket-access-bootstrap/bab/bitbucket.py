"""Bitbucket Cloud access tokens: the target, its settings page, and the create dialog.

Bitbucket has no REST endpoint that creates an access token, for any of its
three kinds, so the tool fills the same dialog a person would. Each step looks
first and acts only if needed; the token value is returned to the caller and
never printed, logged or written by this module.

Selectors follow the accessibility tree (roles and accessible names) with
fallbacks on the form inputs, because Bitbucket regenerates its CSS classes.
When a step cannot find a control it raises, and the caller writes a snapshot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import config, redact, snap, ui

KINDS = ("repository", "project", "workspace")

# Scope id (as in Bitbucket's docs and the API's x-oauth-scopes) to the section
# heading and checkbox label of the create dialog. Write implies read in the UI.
SCOPES: dict[str, tuple[str, str]] = {
    "repository": ("Repositories", "Read"),
    "repository:write": ("Repositories", "Write"),
    "repository:admin": ("Repositories", "Admin"),
    "repository:delete": ("Repositories", "Delete"),
    "pullrequest": ("Pull requests", "Read"),
    "pullrequest:write": ("Pull requests", "Write"),
    "webhook": ("Webhooks", "Read and write"),
    "pipeline": ("Pipelines", "Read"),
    "pipeline:write": ("Pipelines", "Write"),
    "pipeline:variable": ("Pipelines", "Edit variables"),
    "runner": ("Runners", "Read"),
    "runner:write": ("Runners", "Write"),
    "project": ("Projects", "Read"),
    "project:admin": ("Projects", "Admin"),
}

# Scope sets for the two tokens a CI/CD repository usually needs.
# - read: clone and pull (build triggers, read-only connections).
# - admin: a Cloud Build repository connection (repository admin, webhooks) that
#   Renovate can share. Renovate opens and updates dependency PRs, which needs
#   pullrequest:write on top of repository:write; with only pullrequest (read) it
#   fails on PR creation. Renovate's Bitbucket docs list the same pair for API
#   tokens (write:repository, write:pullrequest); the user and workspace read
#   scopes they add have no access-token equivalent and are not needed.
PRESETS: dict[str, list[str]] = {
    "read": ["repository"],
    "admin": ["repository", "repository:write", "repository:admin",
              "pullrequest", "pullrequest:write", "webhook"],
}

BOT_EMAIL = re.compile(r"[A-Za-z0-9._-]+@bots\.bitbucket\.org")
SLUG = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass
class Target:
    kind: str
    workspace: str
    repo: str | None = None
    project_key: str | None = None

    def validate(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        if not SLUG.match(self.workspace or ""):
            raise ValueError("--workspace is required (the workspace slug)")
        if self.kind == "repository" and not SLUG.match(self.repo or ""):
            raise ValueError("--repo is required for a repository token")
        if self.kind == "project" and not SLUG.match(self.project_key or ""):
            raise ValueError("--project-key is required for a project token")

    @property
    def settings_url(self) -> str:
        base = f"{config.BITBUCKET}/{self.workspace}"
        if self.kind == "repository":
            return f"{base}/{self.repo}/admin/access-tokens"
        if self.kind == "project":
            return f"{base}/workspace/projects/{self.project_key}/settings/access-tokens"
        return f"{base}/workspace/settings/access-tokens"

    @property
    def label(self) -> str:
        where = {
            "repository": f"{self.workspace}/{self.repo}",
            "project": f"{self.workspace} project {self.project_key}",
            "workspace": f"workspace {self.workspace}",
        }[self.kind]
        return f"{self.kind} access token on {where}"


@dataclass
class Spec:
    target: Target
    name: str
    scopes: list[str] = field(default_factory=list)
    expires: str | None = None  # YYYY-MM-DD; None keeps Bitbucket's default

    def validate(self) -> None:
        self.target.validate()
        if not self.name or len(self.name) > 255:
            raise ValueError("--name is required (at most 255 characters)")
        unknown = [s for s in self.scopes if s not in SCOPES]
        if unknown:
            raise ValueError(f"unknown scope(s) {unknown}; known: {', '.join(SCOPES)}")
        if not self.scopes:
            raise ValueError("--scopes needs at least one scope")
        if self.target.kind == "repository" and any(s.startswith("project") for s in self.scopes):
            raise ValueError("project scopes exist only on project and workspace tokens")
        if self.expires:
            try:
                when = date.fromisoformat(self.expires)
            except ValueError:
                raise ValueError("--expires must be YYYY-MM-DD") from None
            # Bitbucket caps access tokens at 365 days; its date picker accepts later
            # dates without complaint (2026-10-23), so the cap is checked here.
            if not date.today() < when <= date.today() + timedelta(days=365):
                raise ValueError("--expires must be after today and at most 365 days ahead")


@dataclass
class Created:
    value: str
    bot_email: str | None


def dismiss_cookie_notice(page) -> None:
    """Atlassian's cookie notice is a role=dialog too; refuse the optional cookies."""
    notice = page.get_by_role("dialog", name=re.compile("cookies", re.I))
    if ui.present(notice):
        button = notice.get_by_role("button", name=ui.ci("Only necessary"))
        if not button.count():
            button = page.get_by_role("button", name=ui.ci("Only necessary"))
        if ui.present(button):
            ui.visible(button).click()
            page.wait_for_timeout(800)


def open_settings(page, target: Target) -> None:
    ui.goto(page, target.settings_url)
    dismiss_cookie_notice(page)
    body = page.locator("body").inner_text()
    if re.search(r"(don.t|do not) have (permission|access)|page (was not|wasn.t) found|404", body, re.I):
        raise PermissionError(
            f"{target.settings_url} is not available to this account: it needs admin on the "
            f"{target.kind}, and workspace tokens need a Premium plan"
        )


def existing_names(page, target: Target) -> list[str]:
    """Token names listed on the settings page: the link in each body row.

    The table exposes rows (header row first) but no cell roles; each token row
    holds a link with the token name and an "Actions" button (2026-10-23).
    """
    open_settings(page, target)
    names = []
    rows = page.get_by_role("rowgroup").get_by_role("row")
    for i in range(rows.count()):
        link = rows.nth(i).get_by_role("link")
        if link.count():
            text = link.first.inner_text().strip()
            if text:
                names.append(text)
    return names


def _dialog(page):
    """The create dialog: the visible dialog that has a Name field (not the cookie notice)."""
    dialogs = page.get_by_role("dialog").filter(
        has=page.get_by_role("textbox", name=re.compile(r"^\s*name", re.I))
    )
    return ui.visible(dialogs, 20000)


def _open_create_dialog(page) -> object:
    pattern = re.compile(r"^\s*create (repository |project |workspace )?access token\s*$", re.I)
    for role in ("button", "link"):
        candidate = page.get_by_role(role, name=pattern)
        if ui.present(candidate):
            ui.visible(candidate).click()
            break
    else:
        raise LookupError("no 'Create access token' button on the settings page")
    page.wait_for_timeout(1200)
    return _dialog(page)


def _scope_checkbox(dialog, scope: str):
    section, label = SCOPES[scope]
    # 1. The input carries the scope id (value, name or id) in most Bitbucket releases.
    for css in (f'input[type=checkbox][value="{scope}"]', f'input[type=checkbox][name="{scope}"]'):
        loc = dialog.locator(css)
        if loc.count():
            return loc.first
    # 2. A group or fieldset named after the section.
    group = dialog.get_by_role("group", name=re.compile(re.escape(section), re.I))
    if ui.present(group):
        box = group.get_by_role("checkbox", name=ui.ci(label))
        if box.count():
            return box.first
    # 3. The nearest ancestor of the section heading that holds checkboxes.
    xpath = (
        f"xpath=//*[normalize-space(text())='{section}']"
        f"/ancestor::*[.//input[@type='checkbox']][1]"
    )
    box = dialog.locator(xpath).first.get_by_role("checkbox", name=ui.ci(label))
    if box.count():
        return box.first
    raise LookupError(f"no checkbox for scope {scope!r} ({section} / {label})")


def _check(page, box) -> None:
    if box.is_checked():
        return
    try:
        box.check()
    except Exception:
        # Atlaskit hides the real input under a styled span; clicking the label works.
        box.click(force=True)
    page.wait_for_timeout(250)
    if not box.is_checked():
        raise RuntimeError("a scope checkbox did not stay checked")


def _set_expiry(page, dialog, date: str) -> None:
    """Type the date into the Atlaskit date picker, then check what it shows.

    The picker is a combobox named "Expiry" that displays and accepts M/D/YYYY
    (en-US) and is pre-filled with the workspace default, 7 days ahead on some
    workspaces (2026-10-23). A date past the workspace's maximum is refused there.
    """
    year, month, day = date.split("-")
    shown = f"{int(month):02d}/{int(day):02d}/{year}"
    field = dialog.get_by_role("combobox", name=re.compile("expir", re.I))
    if not ui.present(field):
        field = dialog.get_by_role("textbox", name=re.compile("expir", re.I))
    if not ui.present(field):
        raise LookupError("the dialog has no expiry field; drop --expires or update the tool")
    box = ui.visible(field)
    box.click()
    box.press("ControlOrMeta+a")
    box.press_sequentially(shown, delay=40)
    box.press("Enter")
    page.wait_for_timeout(600)
    text = dialog.inner_text()
    if shown not in text and f"{int(month)}/{int(day)}/{year}" not in text:
        raise RuntimeError(f"the expiry field did not take {shown}; it may exceed the workspace maximum")


def fill_form(page, spec: Spec):
    """Open the dialog and fill name, scopes and expiry. Returns the dialog."""
    dialog = _open_create_dialog(page)
    name = dialog.get_by_role("textbox", name=re.compile(r"^\s*name", re.I))
    ui.visible(name).fill(spec.name)
    page.wait_for_timeout(300)
    for scope in spec.scopes:
        _check(page, _scope_checkbox(dialog, scope))
    if spec.expires:
        _set_expiry(page, dialog, spec.expires)
    return dialog


def cancel(page, dialog) -> None:
    for name in ("Cancel", "Close"):
        button = dialog.get_by_role("button", name=ui.ci(name))
        if ui.present(button):
            ui.visible(button).click()
            page.wait_for_timeout(600)
            return
    page.keyboard.press("Escape")


def submit(page, dialog) -> Created:
    """Click Create and read the token from the result. Shown once, only here."""
    create = ui.visible(dialog.get_by_role("button", name=ui.ci("Create")))
    if not create.is_enabled():
        raise RuntimeError("Create is disabled: a required field (name, scope, expiry) is missing")
    create.click()

    value = None
    for _ in range(40):
        page.wait_for_timeout(500)
        texts = [page.locator("body").inner_text(), *snap.input_values(page)]
        value = next((redact.find(t) for t in texts if redact.contains(t)), None)
        if value:
            break
    if not value:
        raise RuntimeError("clicked Create but no token appeared on the page")
    bot = BOT_EMAIL.search(page.locator("body").inner_text())
    return Created(value=value, bot_email=bot.group(0) if bot else None)


def close_result(page) -> None:
    """Dismiss the one-time token dialog so the value leaves the screen."""
    for name in ("Done", "Close", "OK", "I have copied the token"):
        button = page.get_by_role("button", name=ui.ci(name))
        if ui.present(button):
            ui.visible(button).click()
            page.wait_for_timeout(800)
            return
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)
