"""kit/bundles/terraform/scripts/plan-summary.py on a synthetic `terraform show -json` plan."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from tests.helpers import ROOT

SCRIPT = ROOT / "kit" / "bundles" / "terraform" / "scripts" / "plan-summary.py"


def rc(address, actions, **extra):
    item = {"address": address, "mode": "managed", "type": address.split(".")[0],
            "change": {"actions": actions}}
    item["change"].update(extra.pop("change", {}))
    item.update(extra)
    return item


PLAN = {
    "format_version": "1.2",
    "resource_changes": [
        rc("google_cloud_run_v2_service.api", ["update"]),
        rc('google_secret_manager_secret.app["api-key"]', ["create"]),
        rc("google_sql_database_instance.main", ["delete", "create"],
           change={"replace_paths": [["region"]]}),
        rc("google_storage_bucket.legacy", ["delete"]),
        rc("google_storage_bucket.assets", ["no-op"], change={"importing": {"id": "my-project-id-assets"}}),
        rc("module.api.google_service_account.this", ["no-op"],
           previous_address="google_service_account.api"),
        {"address": "data.google_project.this", "mode": "data", "change": {"actions": ["read"]}},
    ],
    "resource_drift": [rc("google_storage_bucket.logs", ["update"])],
}


class PlanSummaryTest(unittest.TestCase):
    def run_script(self, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin if stdin is not None else json.dumps(PLAN),
                              capture_output=True, text=True)

    def test_counts_and_destroys_first(self) -> None:
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout
        self.assertIn("Plan: 1 to add, 1 to change, 1 to replace, 1 to destroy, 1 to import, 1 moved", out)
        self.assertIn("WARNING: 2 resource(s) will be destroyed or replaced.", out)
        self.assertLess(out.index("DESTROY"), out.index("UPDATE IN PLACE"))
        self.assertLess(out.index("REPLACE"), out.index("CREATE"))
        self.assertIn("(forced by: region)", out)
        self.assertIn("google_service_account.api -> module.api.google_service_account.this", out)
        self.assertIn("DRIFT", out)
        self.assertIn("google_storage_bucket.logs", out)

    def test_targets_are_quoted_and_skip_data_sources(self) -> None:
        out = self.run_script("--targets").stdout
        self.assertIn("-target='google_secret_manager_secret.app[\"api-key\"]'", out)
        self.assertNotIn("-target='data.", out)

    def test_match_filters_addresses(self) -> None:
        out = self.run_script("--match", "cloud_run", "--targets").stdout
        self.assertIn("Plan: 0 to add, 1 to change, 0 to replace, 0 to destroy", out)
        self.assertIn("-target='google_cloud_run_v2_service.api'", out)
        self.assertNotIn("sql_database_instance", out)

    def test_fail_on_destroy(self) -> None:
        self.assertEqual(self.run_script("--fail-on-destroy").returncode, 3)
        self.assertEqual(self.run_script("--fail-on-destroy", "--match", "cloud_run").returncode, 0)

    def test_empty_plan(self) -> None:
        p = self.run_script(stdin=json.dumps({"format_version": "1.2", "resource_changes": []}))
        self.assertEqual(p.returncode, 0)
        self.assertIn("No changes.", p.stdout)

    def test_bad_input(self) -> None:
        self.assertEqual(self.run_script(stdin="not json").returncode, 2)
        self.assertEqual(self.run_script(stdin="{}").returncode, 2)


if __name__ == "__main__":
    unittest.main()
