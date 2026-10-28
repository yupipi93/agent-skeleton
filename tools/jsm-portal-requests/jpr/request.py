"""Turn `name=value` pairs into a customer request payload, check it, send it.

Values are given by field id or by the label the portal shows; options by their label
or id. The payload is the one `POST /rest/servicedeskapi/request` takes, so the request
is created exactly as if the signed-in person had filled the portal form.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import config

UNSUPPORTED = ("attachment",)


@dataclass
class Plan:
    portal: dict
    rtype: dict
    values: dict = field(default_factory=dict)       # fieldId -> API value
    shown: list = field(default_factory=list)        # (label, fieldId, human value)
    participants: list = field(default_factory=list)
    on_behalf: str = ""
    problems: list = field(default_factory=list)

    def payload(self) -> dict:
        body = {
            "serviceDeskId": self.portal["serviceDeskId"],
            "requestTypeId": self.rtype["id"],
            "requestFieldValues": self.values,
        }
        if self.participants:
            body["requestParticipants"] = self.participants
        if self.on_behalf:
            body["raiseOnBehalfOf"] = self.on_behalf
        return body

    def texts(self) -> str:
        out = []
        for _, fid, human in self.shown:
            f = next((x for x in self.rtype["fields"] if x["fieldId"] == fid), None)
            if fid in ("summary", "description") or (f and f["type"] in ("string", "any")):
                out.append(str(human))
        return "\n\n".join(out)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def find_field(rtype: dict, key: str) -> dict:
    fields = rtype["fields"]
    k = _norm(key)
    for f in fields:
        if f["fieldId"].lower() == k:
            return f
    exact = [f for f in fields if _norm(f["name"]) == k]
    if len(exact) == 1:
        return exact[0]
    partial = [f for f in fields if k in _norm(f["name"])]
    if len(partial) == 1:
        return partial[0]
    names = "; ".join(f"{f['fieldId']} = {f['name']}" for f in (partial or fields))
    raise SystemExit(f"jpr: field '{key}' is {'ambiguous' if partial else 'unknown'} in "
                     f"'{rtype['name']}'. Fields: {names}")


def _option(f: dict, raw: str, options: list | None = None) -> dict:
    options = f.get("validValues") if options is None else options
    want = _norm(raw)
    for v in options:
        if _norm(v["label"]) == want or str(v["value"]) == raw.strip():
            return v
    partial = [v for v in options if want in _norm(v["label"])]
    if len(partial) == 1:
        return partial[0]
    labels = ", ".join(v["label"] for v in options)
    raise SystemExit(f"jpr: '{raw}' is not an option of '{f['name']}'. Options: {labels}")


def _split_list(raw: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;\n]", raw) if x.strip()]


def convert(f: dict, raw: str):
    """API value and a human rendering for one field."""
    t, items, custom = f["type"], f.get("items", ""), f.get("custom", "")
    if t in UNSUPPORTED or items in UNSUPPORTED:
        raise SystemExit(f"jpr: '{f['name']}' is an attachment field; attach files in the portal after creation")
    if raw.startswith("json:"):
        value = json.loads(raw[5:])
        return value, json.dumps(value, ensure_ascii=False)
    if t == "option-with-child":
        parent_raw, _, child_raw = raw.partition(">")
        parent = _option(f, parent_raw)
        value = {"id": str(parent["value"])}
        human = parent["label"]
        if child_raw.strip():
            child = _option(f, child_raw, parent.get("children") or [])
            value["child"] = {"id": str(child["value"])}
            human += f" > {child['label']}"
        return value, human
    if t in ("option", "priority") or (f.get("validValues") and t not in ("array",)):
        v = _option(f, raw)
        return {"id": str(v["value"])}, v["label"]
    if t == "array" and items in ("option", "component", "version") or (t == "array" and f.get("validValues")):
        picked = [_option(f, x) for x in _split_list(raw)]
        return [{"id": str(v["value"])} for v in picked], "; ".join(v["label"] for v in picked)
    if t == "array" and items == "user":
        ids = _split_list(raw)
        return [{"accountId": i} for i in ids], "; ".join(ids)
    if t == "user":
        return {"accountId": raw.strip()}, raw.strip()
    if t == "array" and items == "string":
        vals = _split_list(raw)
        return vals, "; ".join(vals)
    if t == "number":
        return float(raw), raw
    if t in ("date", "datetime") or "datepicker" in custom:
        return raw.strip(), raw.strip()
    return raw, raw


def build(portal: dict, rtype: dict, pairs: list[tuple[str, str]], participants: list[str],
          on_behalf: str = "") -> Plan:
    plan = Plan(portal, rtype, participants=participants, on_behalf=on_behalf)
    for key, raw in pairs:
        f = find_field(rtype, key)
        value, human = convert(f, raw)
        plan.values[f["fieldId"]] = value
        plan.shown.append((f["name"], f["fieldId"], human))
    for f in rtype["fields"]:
        if f["required"] and f.get("visible", True) and f["fieldId"] not in plan.values:
            plan.problems.append(f"missing required field '{f['name']}' ({f['fieldId']})")
    if participants and not rtype.get("canAddRequestParticipants"):
        plan.problems.append("this request type does not take request participants")
    if on_behalf and not rtype.get("canRaiseOnBehalfOf"):
        plan.problems.append("this account cannot raise this request type on behalf of someone else")
    ui = rtype.get("ui") or {}
    if ui.get("formMarker"):
        plan.problems.append("the create page renders a Jira form, which this API path cannot fill; "
                             "raise it in the portal by hand")
    if not rtype.get("canCreateRequest", True):
        plan.problems.append("the signed-in account cannot create this request type")
    return plan


def guard(text: str) -> tuple[bool, str]:
    """Run the kit text guard (secrets and em dash) over the outgoing text."""
    if not text.strip() or not config.TEXT_GUARD.is_file():
        return True, ""
    config.ensure_dirs()
    with tempfile.NamedTemporaryFile("w", suffix=".md", dir=config.RUNS_DIR, delete=False) as fh:
        fh.write(text)
        tmp = Path(fh.name)
    try:
        proc = subprocess.run(["/bin/bash", str(config.TEXT_GUARD), "--em-dash", "--file", str(tmp)],
                              capture_output=True, text=True)
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()
    finally:
        tmp.unlink(missing_ok=True)


def render(plan: Plan) -> str:
    p, rt = plan.portal, plan.rtype
    lines = [
        f"site      {config.site()}",
        f"portal    {p['name']} (service desk {p['serviceDeskId']}, {p['projectKey']})",
        f"type      {rt['name']} ({rt['id']})",
    ]
    for label, fid, human in plan.shown:
        text = str(human)
        if "\n" in text:
            text = "\n            " + "\n            ".join(text.splitlines())
        lines.append(f"field     {label} [{fid}]: {text}")
    if plan.participants:
        lines.append(f"cc        {', '.join(plan.participants)}")
    if plan.on_behalf:
        lines.append(f"for       {plan.on_behalf}")
    for problem in plan.problems:
        lines.append(f"PROBLEM   {problem}")
    return "\n".join(lines)


def portal_link(portal_id: str, key: str) -> str:
    return f"{config.base_url()}/servicedesk/customer/portal/{portal_id}/{key}"
