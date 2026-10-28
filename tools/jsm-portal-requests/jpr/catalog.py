"""Walk the portals the signed-in account can see and write a catalog.

The REST walk (servicedeskapi) gives every portal, its request type groups (the
"Contact us about" categories), its request types and each type's fields with their
ids, whether they are required and their valid options. The optional UI walk opens the
same pages a person would (the portal, each category, each create form), records the
portal's display name and the labels each create form really renders, and saves an
accessibility snapshot. A label the REST fields do not explain usually means a Jira
form (ProForma) is attached, which the customer REST API cannot fill.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import config, portal

SD = "/rest/servicedeskapi/servicedesk"


def site_dir() -> Path:
    return config.CATALOG_DIR / config.site()


def catalog_path() -> Path:
    return site_dir() / "catalog.json"


def load() -> dict:
    path = catalog_path()
    if not path.is_file():
        raise SystemExit(f"jpr: no catalog yet at {path}: run `jpr crawl` first")
    return json.loads(path.read_text())


def save(data: dict) -> Path:
    config.ensure_dirs()
    out = site_dir()
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    path = catalog_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return path


def _slim_field(f: dict) -> dict:
    schema = f.get("jiraSchema") or {}
    return {
        "fieldId": f["fieldId"],
        "name": f.get("name", ""),
        "description": f.get("description", ""),
        "required": bool(f.get("required")),
        "visible": f.get("visible", True),
        "type": schema.get("type", ""),
        "items": schema.get("items", ""),
        "custom": schema.get("custom", "") or schema.get("system", ""),
        "validValues": [
            {
                "value": v.get("value"),
                "label": v.get("label"),
                **({"children": [{"value": c.get("value"), "label": c.get("label")} for c in v["children"]]}
                   if v.get("children") else {}),
            }
            for v in f.get("validValues") or []
        ],
        "defaultValues": [d.get("value") if isinstance(d, dict) else d for d in f.get("defaultValues") or []],
    }


def walk_api(session: portal.Session, only: set[str] | None = None, log=print) -> list[dict]:
    desks = session.paged(SD)
    portals = []
    for desk in desks:
        sd_id = str(desk["id"])
        if only and sd_id not in only and desk.get("projectKey") not in only:
            continue
        groups = session.paged(f"{SD}/{sd_id}/requesttypegroup")
        types = session.paged(f"{SD}/{sd_id}/requesttype")
        log(f"portal {sd_id} {desk.get('projectKey')}: {len(groups)} groups, {len(types)} request types")
        rts = []
        for rt in types:
            fields = session.get(f"{SD}/{sd_id}/requesttype/{rt['id']}/field?expand=hiddenFields")
            rts.append({
                "id": str(rt["id"]),
                "name": rt.get("name", "").strip(),
                "description": rt.get("description", ""),
                "helpText": rt.get("helpText", ""),
                "groupIds": [str(g) for g in rt.get("groupIds") or []],
                "issueTypeId": rt.get("issueTypeId"),
                "canCreateRequest": rt.get("canCreateRequest", True),
                "canRaiseOnBehalfOf": fields.get("canRaiseOnBehalfOf", False),
                "canAddRequestParticipants": fields.get("canAddRequestParticipants", False),
                "fields": [_slim_field(f) for f in fields.get("requestTypeFields", [])],
            })
        portals.append({
            "serviceDeskId": sd_id,
            "portalId": str(desk.get("portalId") or sd_id),
            "projectKey": desk.get("projectKey"),
            "projectName": desk.get("projectName"),
            "name": desk.get("projectName"),
            "groups": [{"id": str(g["id"]), "name": g.get("name", "")} for g in groups],
            "requestTypes": rts,
        })
    return portals


LABELS_JS = """
() => {
  const root = document.querySelector('main') || document.body;
  const seen = new Set(); const out = [];
  for (const el of root.querySelectorAll('label, legend')) {
    const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
    if (t && !seen.has(t)) { seen.add(t); out.push(t); }
  }
  return out;
}
"""

FORM_MARKERS = "[data-testid*=proforma], [class*=proforma], [data-testid*='forms-'], iframe[src*=proforma]"


def _norm(text: str) -> str:
    return re.sub(r"[\s*]+", " ", re.sub(r"\(optional\)|\(required\)|required", "", text, flags=re.I)).strip().lower()


def walk_ui(page, portals: list[dict], log=print) -> None:
    """Visit each portal, category and create form; annotate the catalog in place."""
    from . import snap

    base = config.base_url()
    for p in portals:
        pid = p["portalId"]
        try:
            portal.goto(page, f"{base}/servicedesk/customer/portal/{pid}")
        except portal.NotSignedIn:
            raise
        except Exception as exc:  # a portal the account cannot open
            p["ui"] = {"error": str(exc)[:200]}
            continue
        heading = page.locator("main h1, h1").first
        try:
            p["name"] = heading.inner_text(timeout=5000).strip() or p["name"]
        except Exception:
            pass
        log(f"portal {pid}: {p['name']}")
        for g in p["groups"]:
            try:
                portal.goto(page, f"{base}/servicedesk/customer/portal/{pid}/group/{g['id']}", 800)
                g["ui_url"] = page.url
            except portal.NotSignedIn:
                raise
            except Exception as exc:
                g["ui_error"] = str(exc)[:200]
        for rt in p["requestTypes"]:
            url = f"{base}/servicedesk/customer/portal/{pid}/create/{rt['id']}"
            try:
                portal.goto(page, url, 1500)
                labels = page.evaluate(LABELS_JS)
                form = page.locator(FORM_MARKERS).count() > 0
                out = snap.take(page, f"p{pid}-rt{rt['id']}", screenshot=False)
            except portal.NotSignedIn:
                raise
            except Exception as exc:
                rt["ui"] = {"error": str(exc)[:200]}
                continue
            known = {_norm(f["name"]) for f in rt["fields"]}
            extra = [lbl for lbl in labels if _norm(lbl) not in known and not any(
                _norm(lbl).startswith(k) for k in known if k)]
            rt["ui"] = {"labels": labels, "unmatched": extra, "formMarker": form, "snapshot": str(out)}
            flag = " FORM" if form else ""
            log(f"  {rt['id']:>5} {rt['name']}: {len(labels)} labels, {len(extra)} unmatched{flag}")


def crawl(page, only: set[str] | None, ui: bool, log=print) -> dict:
    session = portal.Session(page)
    me = session.myself()
    portals = walk_api(session, only, log)
    if ui:
        walk_ui(page, portals, log)
    data = {
        "site": config.site(),
        "account": {k: me.get(k) for k in ("accountId", "emailAddress", "displayName", "email", "name") if me.get(k)},
        "crawledAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ui": ui,
        "portals": portals,
    }
    if only:
        try:
            old = load()
            keep = [p for p in old.get("portals", []) if p["serviceDeskId"] not in {x["serviceDeskId"] for x in portals}]
            data["portals"] = sorted(keep + portals, key=lambda p: int(p["serviceDeskId"]))
        except SystemExit:
            pass
    save(data)
    write_markdown(data)
    return data


# ---- lookups -------------------------------------------------------------------------

def _match(items: list[dict], key: str, fields: tuple[str, ...], what: str) -> dict:
    wanted = key.strip().lower()
    for f in fields:
        exact = [i for i in items if str(i.get(f, "")).strip().lower() == wanted]
        if len(exact) == 1:
            return exact[0]
    partial = [i for i in items if any(wanted in str(i.get(f, "")).lower() for f in fields)]
    if len(partial) == 1:
        return partial[0]
    names = ", ".join(f"{i.get('id') or i.get('serviceDeskId')} {i.get('name')}" for i in (partial or items)[:15])
    raise SystemExit(f"jpr: {what} '{key}' is {'ambiguous' if partial else 'unknown'}; candidates: {names}")


def find_portal(data: dict, key: str) -> dict:
    return _match(data["portals"], key, ("serviceDeskId", "portalId", "projectKey", "name", "projectName"), "portal")


def find_type(p: dict, key: str) -> dict:
    return _match(p["requestTypes"], key, ("id", "name"), "request type")


def group_names(p: dict, rt: dict) -> list[str]:
    by_id = {g["id"]: g["name"] for g in p["groups"]}
    return [by_id.get(g, g) for g in rt["groupIds"]]


# ---- rendering -----------------------------------------------------------------------

def _cell(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).replace("|", "\\|").strip()


def field_type(f: dict) -> str:
    t = f["type"] + (f"<{f['items']}>" if f.get("items") else "")
    custom = f.get("custom", "").rsplit(":", 1)[-1]
    return f"{t} ({custom})" if custom and custom != f["fieldId"] else t


def options_text(f: dict, limit: int = 12) -> str:
    vals = f.get("validValues") or []
    shown = []
    for v in vals[:limit]:
        kids = v.get("children")
        shown.append(f"{v['label']}" + (f" > [{', '.join(c['label'] for c in kids[:6])}{'...' if len(kids) > 6 else ''}]" if kids else ""))
    more = f" (+{len(vals) - limit})" if len(vals) > limit else ""
    return "; ".join(shown) + more


def render_type(p: dict, rt: dict) -> list[str]:
    lines = [
        f"### {rt['name']} (request type {rt['id']})",
        "",
        f"Category: {', '.join(group_names(p, rt)) or '(none, hidden from the portal menu)'}. "
        f"Create page: `/servicedesk/customer/portal/{p['portalId']}/create/{rt['id']}`.",
    ]
    if rt.get("description"):
        lines += ["", _cell(rt["description"])]
    if rt.get("helpText"):
        lines += ["", f"Help text: {_cell(rt['helpText'])}"]
    lines += ["", "| Field id | Label | Req. | Type | Options |", "|---|---|---|---|---|"]
    for f in rt["fields"]:
        hidden = " (hidden)" if not f.get("visible", True) else ""
        lines.append(
            f"| `{f['fieldId']}` | {_cell(f['name'])}{hidden} | {'yes' if f['required'] else ''} | "
            f"{_cell(field_type(f))} | {_cell(options_text(f))} |"
        )
    ui = rt.get("ui") or {}
    if ui.get("unmatched") or ui.get("formMarker"):
        lines += ["", f"The create page also shows: {_cell('; '.join(ui.get('unmatched') or []))}"
                  + (" (Jira form detected)" if ui.get("formMarker") else "")]
    extras = []
    if rt.get("canAddRequestParticipants"):
        extras.append("request participants allowed")
    if rt.get("canRaiseOnBehalfOf"):
        extras.append("raise on behalf of allowed")
    if extras:
        lines += ["", f"Options: {', '.join(extras)}."]
    return lines + [""]


def render_portal(p: dict) -> str:
    lines = [
        f"# {p['name']}",
        "",
        f"Service desk {p['serviceDeskId']}, portal {p['portalId']}, project `{p['projectKey']}`.",
        "",
        "## Categories",
        "",
        "| Category | Request types |",
        "|---|---|",
    ]
    for g in p["groups"]:
        names = [f"{rt['name']} ({rt['id']})" for rt in p["requestTypes"] if g["id"] in rt["groupIds"]]
        lines.append(f"| {_cell(g['name'])} | {_cell(', '.join(names))} |")
    hidden = [f"{rt['name']} ({rt['id']})" for rt in p["requestTypes"] if not rt["groupIds"]]
    if hidden:
        lines.append(f"| (no category) | {_cell(', '.join(hidden))} |")
    lines += ["", "## Request types", ""]
    order = {g["id"]: i for i, g in enumerate(p["groups"])}
    for rt in sorted(p["requestTypes"], key=lambda r: (min([order.get(g, 999) for g in r["groupIds"]] or [999]), r["name"].lower())):
        lines += render_type(p, rt)
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(data: dict) -> Path:
    out = site_dir()
    index = [
        f"# Service desk portals on {data['site']}",
        "",
        f"Crawled {data['crawledAt']} as {data['account'].get('displayName', '?')}"
        f"{' (with UI walk)' if data.get('ui') else ''}.",
        "",
        "| Service desk | Portal | Project | Categories | Request types |",
        "|---|---|---|---|---|",
    ]
    for p in data["portals"]:
        (out / f"portal-{p['serviceDeskId']}.md").write_text(render_portal(p))
        index.append(
            f"| {p['serviceDeskId']} | [{_cell(p['name'])}](portal-{p['serviceDeskId']}.md) | `{p['projectKey']}` | "
            f"{len(p['groups'])} | {len(p['requestTypes'])} |"
        )
    path = out / "index.md"
    path.write_text("\n".join(index) + "\n")
    return path
