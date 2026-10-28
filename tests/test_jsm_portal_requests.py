"""tools/jsm-portal-requests without a browser: field lookup, value conversion, plans."""
from __future__ import annotations

import subprocess
import sys
import unittest

from tests.helpers import ROOT

TOOL = ROOT / "tools" / "jsm-portal-requests"
JPR = TOOL / "bin" / "jpr"

PORTAL = {"serviceDeskId": "1", "portalId": "1", "projectKey": "IT", "name": "IT Support",
          "groups": [{"id": "32", "name": "Accounts"}]}
GROUP_TYPE = {
    "id": "363", "name": "Group creation", "groupIds": ["32"], "canCreateRequest": True,
    "canAddRequestParticipants": True, "canRaiseOnBehalfOf": False,
    "fields": [
        {"fieldId": "customfield_1", "name": "Is this an external or an internal group?", "required": True,
         "visible": True, "type": "option", "items": "", "custom": "select",
         "validValues": [{"value": "12218", "label": "Internal"}, {"value": "12219", "label": "External"}]},
        {"fieldId": "customfield_2", "name": "Group Name", "required": True, "visible": True,
         "type": "string", "items": "", "custom": "textfield", "validValues": []},
        {"fieldId": "summary", "name": "Summary", "required": True, "visible": True,
         "type": "string", "items": "", "custom": "summary", "validValues": []},
        {"fieldId": "customfield_3", "name": "Country", "required": False, "visible": True,
         "type": "option-with-child", "items": "", "custom": "cascadingselect",
         "validValues": [{"value": "1", "label": "Spain", "children": [{"value": "11", "label": "Madrid"}]}]},
        {"fieldId": "customfield_4", "name": "Tools", "required": False, "visible": True,
         "type": "array", "items": "option", "custom": "multiselect",
         "validValues": [{"value": "7", "label": "Drive"}, {"value": "8", "label": "Jira"}]},
    ],
}


def _import():
    sys.path.insert(0, str(TOOL))
    import jpr.catalog as catalog  # noqa: E402
    import jpr.request as request  # noqa: E402
    return catalog, request


class FieldTest(unittest.TestCase):
    def test_lookup_by_id_label_and_part(self) -> None:
        _, req = _import()
        self.assertEqual(req.find_field(GROUP_TYPE, "customfield_2")["name"], "Group Name")
        self.assertEqual(req.find_field(GROUP_TYPE, "group name")["fieldId"], "customfield_2")
        self.assertEqual(req.find_field(GROUP_TYPE, "external")["fieldId"], "customfield_1")
        with self.assertRaises(SystemExit):
            req.find_field(GROUP_TYPE, "nothing like it")

    def test_conversions(self) -> None:
        _, req = _import()
        f = {x["fieldId"]: x for x in GROUP_TYPE["fields"]}
        self.assertEqual(req.convert(f["customfield_1"], "external")[0], {"id": "12219"})
        self.assertEqual(req.convert(f["customfield_1"], "12218")[0], {"id": "12218"})
        self.assertEqual(req.convert(f["customfield_3"], "Spain > Madrid")[0],
                         {"id": "1", "child": {"id": "11"}})
        self.assertEqual(req.convert(f["customfield_4"], "Drive; jira")[0], [{"id": "7"}, {"id": "8"}])
        self.assertEqual(req.convert(f["customfield_2"], 'json:"raw"')[0], "raw")
        with self.assertRaises(SystemExit):
            req.convert(f["customfield_1"], "Maybe")


class PlanTest(unittest.TestCase):
    def test_complete_plan_payload(self) -> None:
        _, req = _import()
        plan = req.build(PORTAL, GROUP_TYPE, [("external", "External"), ("Group Name", "team.users"),
                                              ("summary", "Access group")], [])
        self.assertEqual(plan.problems, [])
        self.assertEqual(plan.payload(), {
            "serviceDeskId": "1", "requestTypeId": "363",
            "requestFieldValues": {"customfield_1": {"id": "12219"}, "customfield_2": "team.users",
                                   "summary": "Access group"},
        })
        self.assertIn("Access group", plan.texts())

    def test_missing_required_and_forms_are_problems(self) -> None:
        _, req = _import()
        plan = req.build(PORTAL, GROUP_TYPE, [("Group Name", "x")], [], on_behalf="abc")
        text = " ".join(plan.problems)
        self.assertIn("Summary", text)
        self.assertIn("on behalf", text)
        form_type = dict(GROUP_TYPE, ui={"formMarker": True})
        self.assertTrue(any("Jira form" in p for p in req.build(PORTAL, form_type, [], []).problems))

    def test_markdown_lists_categories_and_fields(self) -> None:
        catalog, _ = _import()
        page = catalog.render_portal(dict(PORTAL, requestTypes=[GROUP_TYPE]))
        self.assertIn("| Accounts | Group creation (363) |", page)
        self.assertIn("`customfield_1`", page)
        self.assertIn("Internal; External", page)


class CliTest(unittest.TestCase):
    def test_help_runs_without_a_browser(self) -> None:
        out = subprocess.run([str(JPR), "--help"], capture_output=True, text=True, check=True).stdout
        self.assertIn("request", out)
        self.assertIn("crawl", out)


if __name__ == "__main__":
    unittest.main()
