from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from execution.models import ExecutionAccount, HarnessSignal
from execution.services.ingest import ingest_signal
from execution.services.mcp_auth import generate_pat
from trading.constants import BROKER_ALPACA
from trading.models import BrokerConnection


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", email="a@example.com", password="x")
        self.bob = User.objects.create_user(username="bob", email="b@example.com", password="x")
        self.conn_a = BrokerConnection.objects.create(
            user=self.alice, broker=BROKER_ALPACA, is_paper=True, last_equity=Decimal("10000")
        )
        self.conn_b = BrokerConnection.objects.create(
            user=self.bob, broker=BROKER_ALPACA, is_paper=True, last_equity=Decimal("10000")
        )
        self.acct_a = ExecutionAccount.objects.create(
            user=self.alice, slug="main", label="Alice", broker_connection=self.conn_a
        )
        ExecutionAccount.objects.create(
            user=self.bob, slug="main", label="Bob", broker_connection=self.conn_b
        )

    def test_ref_id_scoped_per_user(self):
        ingest_signal(
            self.alice,
            {
                "ref_id": "shared-ref",
                "account_slug": "main",
                "symbol": "SPY",
                "entry_rule": {"price": "1"},
                "size": 1,
            },
        )
        ingest_signal(
            self.bob,
            {
                "ref_id": "shared-ref",
                "account_slug": "main",
                "symbol": "QQQ",
                "entry_rule": {"price": "1"},
                "size": 1,
            },
        )
        self.assertEqual(HarnessSignal.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(HarnessSignal.objects.filter(user=self.bob).count(), 1)

    def test_cannot_ingest_other_users_account(self):
        ExecutionAccount.objects.filter(user=self.alice, slug="main").update(slug="alice-main")
        with self.assertRaises(Exception):
            ingest_signal(
                self.bob,
                {
                    "ref_id": "x-2",
                    "account_slug": "alice-main",
                    "symbol": "SPY",
                    "entry_rule": {"price": "1"},
                    "size": 1,
                },
            )

    @override_settings(EXECUTION_MCP_ADMIN_BEARER="")
    def test_mcp_pat_scoped(self):
        raw_a, _ = generate_pat(self.alice, "agent", scopes=["execution:read", "execution:trade"])
        raw_b, _ = generate_pat(self.bob, "agent", scopes=["execution:read", "execution:trade"])
        client = APIClient()
        self.acct_a.slug = "alice-main"
        self.acct_a.save()
        ingest_signal(
            self.alice,
            {"ref_id": "vis-1", "account_slug": "alice-main", "symbol": "AAPL", "entry_rule": {"price": "1"}, "size": 1},
        )

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "status", "arguments": {}},
        }
        resp_b = client.post(
            "/api/mcp/execution/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {raw_b}",
        )
        self.assertEqual(resp_b.status_code, 200)
        body_b = resp_b.json()["result"]["structuredContent"]
        self.assertEqual(len(body_b["open_signals"]), 0)

        resp_a = client.post(
            "/api/mcp/execution/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {raw_a}",
        )
        body_a = resp_a.json()["result"]["structuredContent"]
        self.assertEqual(len(body_a["open_signals"]), 1)
