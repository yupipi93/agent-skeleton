#!/usr/bin/env python3
"""Summarize a Terraform plan for review, destroys and replaces first.

Reads the JSON form of a saved plan (`terraform show -json PLANFILE`) from a file
or stdin and prints what a reviewer needs before an apply is proposed:

  terraform plan -out=dev.tfplan
  terraform show -json dev.tfplan | kit/bundles/terraform/scripts/plan-summary.py
  kit/bundles/terraform/scripts/plan-summary.py dev.json --targets --match 'cloud_run'

Options:
  --targets          print a copy-paste `-target=` line per changed resource
  --match REGEX      only consider resource addresses matching REGEX
  --fail-on-destroy  exit 3 when the plan destroys or replaces anything

Exit codes: 0 ok, 2 bad input, 3 destroy or replace present (with --fail-on-destroy).
Read-only: it never runs terraform and never touches state. Python 3.8+, stdlib only.
"""
import argparse
import json
import re
import sys

SYMBOL = {
    "create": "+",
    "update": "~",
    "delete": "-",
    "replace": "-/+",
    "replace-cbd": "+/-",
    "read": "<=",
}
ORDER = ("delete", "replace", "replace-cbd", "update", "create", "read")
TITLE = {
    "delete": "DESTROY (read these first)",
    "replace": "REPLACE, destroy then create (read these first)",
    "replace-cbd": "REPLACE, create then destroy (read these first)",
    "update": "UPDATE IN PLACE",
    "create": "CREATE",
    "read": "DATA SOURCES READ DURING APPLY",
}


def classify(actions):
    a = list(actions or [])
    if a == ["delete", "create"]:
        return "replace"
    if a == ["create", "delete"]:
        return "replace-cbd"
    if len(a) == 1 and a[0] in ("create", "update", "delete", "read"):
        return a[0]
    return None  # no-op or unknown


def replace_reason(rc):
    paths = rc.get("change", {}).get("replace_paths") or []
    out = []
    for p in paths:
        if isinstance(p, list):
            out.append(".".join(str(x) for x in p))
    reason = rc.get("action_reason")
    if reason and reason not in ("replace_because_cannot_update",):
        out.append(reason)
    return ", ".join(out)


def load(path):
    try:
        if path in (None, "-"):
            return json.load(sys.stdin)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write("error: cannot read plan JSON: %s\n" % e)
        sys.stderr.write("hint: terraform show -json PLANFILE | %s\n" % sys.argv[0])
        sys.exit(2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Summarize a terraform plan (JSON) for review.")
    ap.add_argument("plan_json", nargs="?", help="file from `terraform show -json` (default stdin)")
    ap.add_argument("--targets", action="store_true", help="print -target= lines for changed resources")
    ap.add_argument("--match", help="only addresses matching this regular expression")
    ap.add_argument("--fail-on-destroy", action="store_true", help="exit 3 on destroy or replace")
    args = ap.parse_args(argv)

    plan = load(args.plan_json)
    if not isinstance(plan, dict) or "format_version" not in plan:
        sys.stderr.write("error: input is not `terraform show -json` output\n")
        return 2
    pattern = re.compile(args.match) if args.match else None

    groups = {k: [] for k in ORDER}
    imports, moves = [], []
    for rc in plan.get("resource_changes", []) or []:
        addr = rc.get("address", "?")
        if pattern and not pattern.search(addr):
            continue
        change = rc.get("change", {}) or {}
        if change.get("importing"):
            imports.append(addr)
        if rc.get("previous_address") and rc["previous_address"] != addr:
            moves.append((rc["previous_address"], addr))
        kind = classify(change.get("actions"))
        if kind:
            groups[kind].append(rc)

    drift = []
    for rc in plan.get("resource_drift", []) or []:
        addr = rc.get("address", "?")
        if pattern and not pattern.search(addr):
            continue
        if classify(rc.get("change", {}).get("actions")):
            drift.append(rc)

    n = {k: len(v) for k, v in groups.items()}
    destructive = n["delete"] + n["replace"] + n["replace-cbd"]
    print("Plan: %d to add, %d to change, %d to replace, %d to destroy, %d to import, %d moved"
          % (n["create"], n["update"], n["replace"] + n["replace-cbd"], n["delete"],
             len(imports), len(moves)))
    if pattern:
        print("(filtered to addresses matching %r)" % args.match)
    if destructive:
        print("WARNING: %d resource(s) will be destroyed or replaced." % destructive)

    for kind in ORDER:
        if not groups[kind]:
            continue
        print("\n" + TITLE[kind])
        for rc in groups[kind]:
            line = "  %-4s %s" % (SYMBOL[kind], rc["address"])
            if kind.startswith("replace"):
                why = replace_reason(rc)
                if why:
                    line += "   (forced by: %s)" % why
            print(line)
    if imports:
        print("\nIMPORT")
        for a in imports:
            print("  <-   %s" % a)
    if moves:
        print("\nMOVED (no infrastructure change by itself)")
        for old, new in moves:
            print("  %s -> %s" % (old, new))
    if drift:
        print("\nDRIFT: changed outside Terraform since the last apply")
        for rc in drift:
            kind = classify(rc.get("change", {}).get("actions"))
            print("  %-4s %s" % (SYMBOL.get(kind, "?"), rc["address"]))
        print("  An apply of this workspace would revert the drift above. If it is not part")
        print("  of the task, target only your own resources and report the drift.")

    if args.targets:
        managed = [rc["address"] for k in ORDER if k != "read" for rc in groups[k]
                   if rc.get("mode", "managed") == "managed"]
        if managed:
            print("\nTARGETS (review before use; -target is for scoped changes only)")
            for i, a in enumerate(managed):
                end = " \\" if i < len(managed) - 1 else ""
                print("  -target='%s'%s" % (a.replace("'", "'\\''"), end))

    if not any(n.values()) and not imports and not moves:
        print("\nNo changes.")
    if args.fail_on_destroy and destructive:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
