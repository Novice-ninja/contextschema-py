import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_example(name: str):
    path = ROOT / "examples" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestExamples(unittest.TestCase):
    def test_customer_service_refund_example(self) -> None:
        module = load_example("customer_service_refund")
        result = module.run()

        self.assertEqual(result.action, "hard_gate")
        self.assertEqual(result.field("order_status").status, "event_invalidated")
        self.assertEqual(result.to_policy_input()["schema"]["name"], "RefundDecision")

    def test_coding_agent_change_example(self) -> None:
        module = load_example("coding_agent_change")
        result = module.run()

        self.assertEqual(result.action, "hard_gate")
        self.assertEqual(result.field("failing_tests").status, "event_invalidated")
        self.assertTrue(result.weak_fields())

    def test_sales_opportunity_next_step_example(self) -> None:
        module = load_example("sales_opportunity_next_step")
        result = module.run()

        self.assertEqual(result.action, "hard_gate")
        self.assertEqual(result.field("pricing_guidance").status, "event_invalidated")

    def test_procurement_vendor_onboarding_example(self) -> None:
        module = load_example("procurement_vendor_onboarding")
        result = module.run()

        self.assertEqual(result.action, "hard_gate")
        self.assertEqual(result.field("sanctions_screening").status, "event_invalidated")

    def test_finance_invoice_approval_example(self) -> None:
        module = load_example("finance_invoice_approval")
        result = module.run()

        self.assertEqual(result.action, "hard_gate")
        self.assertEqual(result.field("po_match").status, "event_invalidated")

    def test_hr_employee_policy_example(self) -> None:
        module = load_example("hr_employee_policy")
        result = module.run()

        self.assertEqual(result.action, "soft_flag")
        self.assertEqual(result.field("manager_approval").status, "missing_optional")

    def test_security_access_review_example(self) -> None:
        module = load_example("security_access_review")
        result = module.run()

        self.assertEqual(result.action, "hard_gate")
        self.assertEqual(result.field("manager_approval").status, "event_invalidated")

    def test_merchandising_super_agent_router_example(self) -> None:
        module = load_example("merchandising_super_agent_router")
        results = module.run()

        self.assertEqual(results["markdown"].action, "hard_gate")
        self.assertEqual(results["markdown"].schema_confidence.required_missing, ["margin_guardrail"])
        self.assertEqual(results["store_transfer"].action, "proceed")
        self.assertIn("markdown", results["schema_definitions"])


if __name__ == "__main__":
    unittest.main()
