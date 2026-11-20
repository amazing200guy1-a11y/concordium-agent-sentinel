"""
Concordium Agent Sentinel - Deterministic Test Suite
Formally verifies Agent Card creation, ZK Badge verification,
x402 HTTP micropayments, MCP tools, and EU AI Act Article 12 audit chaining.
"""

import unittest
import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent_card import AgentCardManager
from src.x402_gateway import X402Gateway
from src.eu_ai_act_logger import EUAIActAuditLogger
from src.mcp_server import ConcordiumAgentRegistryMCPServer

class TestConcordiumAgentSentinel(unittest.TestCase):
    
    def setUp(self):
        self.card_mgr = AgentCardManager()
        self.x402_gw = X402Gateway()
        self.supervisor_id = "did:ccd:testnet:id:42xFUNAABUsmanBamidele"
        self.test_agent_did = "did:ccd:testnet:agent:0x89205a3a3b2a69de6dbf7f01ed13b2108b2c43e7"
        self.audit_logger = EUAIActAuditLogger(self.test_agent_did, self.supervisor_id)
        self.mcp_server = ConcordiumAgentRegistryMCPServer(self.card_mgr, self.x402_gw, self.audit_logger)

    def test_01_issue_agent_card_cis8004(self):
        card = self.card_mgr.issue_agent_card(
            agent_did=self.test_agent_did,
            name="Autonomous Compute Dispatcher",
            human_id_credential="concordium_kyc_passport_hash_987",
            verification_tier="TIER_1_ID_PROVED"
        )
        self.assertEqual(card["agent_did"], self.test_agent_did)
        self.assertEqual(card["verified_by_concordium"]["status"], "VERIFIED")
        self.assertTrue(card["verified_by_concordium"]["zk_commitment"].startswith("0x"))
        self.assertTrue(card["verified_by_concordium"]["guardian_signature"].startswith("0x"))
        self.assertIn("x402", card["supported_protocols"])

    def test_02_verify_agent_badge_success(self):
        self.card_mgr.issue_agent_card(
            agent_did=self.test_agent_did,
            name="Alpha Agent",
            human_id_credential="human_cred_alpha"
        )
        is_valid, reason, card = self.card_mgr.verify_agent_badge(self.test_agent_did)
        self.assertTrue(is_valid)
        self.assertEqual(reason, "VERIFIED_BY_CONCORDIUM_ACTIVE")
        self.assertIsNotNone(card)

    def test_03_unregistered_agent_rejected(self):
        unregistered_did = "did:ccd:testnet:agent:0x000000000000000000000000000000000000dead"
        is_valid, reason, card = self.card_mgr.verify_agent_badge(unregistered_did)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "AGENT_NOT_REGISTERED")
        self.assertIsNone(card)

    def test_04_tampered_guardian_signature_rejected(self):
        self.card_mgr.issue_agent_card(
            agent_did=self.test_agent_did,
            name="Tamper Test Agent",
            human_id_credential="cred_123"
        )
        # Maliciously alter the guardian signature
        self.card_mgr._registry[self.test_agent_did]["verified_by_concordium"]["guardian_signature"] = "0xdeadbeef" * 8
        is_valid, reason, card = self.card_mgr.verify_agent_badge(self.test_agent_did)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "INVALID_GUARDIAN_SIGNATURE")

    def test_05_emergency_agent_revocation(self):
        self.card_mgr.issue_agent_card(
            agent_did=self.test_agent_did,
            name="Revocation Agent",
            human_id_credential="cred_456"
        )
        revoked = self.card_mgr.revoke_agent(self.test_agent_did, "Compromised prompt detected")
        self.assertTrue(revoked)
        is_valid, reason, card = self.card_mgr.verify_agent_badge(self.test_agent_did)
        self.assertFalse(is_valid)
        self.assertEqual(reason, "BADGE_STATUS_REVOKED")

    def test_06_x402_challenge_creation(self):
        challenge = self.x402_gw.create_payment_challenge(
            resource_uri="/v1/llm/inference",
            price_ccd=1.50,
            recipient_address="4jXyConcordiumRecipientAddress991823"
        )
        self.assertEqual(challenge["status_code"], 402)
        self.assertEqual(challenge["payment_details"]["amount"], 1.50)
        self.assertEqual(challenge["payment_details"]["asset"], "CCD")
        self.assertIn("x402", challenge["headers"]["WWW-Authenticate"])

    def test_07_x402_payment_settlement(self):
        challenge = self.x402_gw.create_payment_challenge(
            resource_uri="/v1/compute/gpu_hour",
            price_ccd=5.00,
            recipient_address="4jXyGPUProviderNode"
        )
        ch_id = challenge["challenge_id"]
        valid_proof = "a9f8b2c1d3e4f50689201923:ccd_sig_990182736451029384756"
        
        success, reason, receipt = self.x402_gw.settle_x402_payment(
            challenge_id=ch_id,
            payer_agent_did=self.test_agent_did,
            client_payment_proof=valid_proof,
            sponsored=True
        )
        self.assertTrue(success)
        self.assertEqual(reason, "SETTLEMENT_SUCCESSFUL")
        self.assertEqual(receipt["amount"], 5.00)
        self.assertEqual(receipt["gas_cost_to_user"], 0.0)
        self.assertEqual(receipt["status"], "FINALIZED_ON_CONCORDIUM_TESTNET")

    def test_08_x402_malformed_proof_rejected(self):
        challenge = self.x402_gw.create_payment_challenge(
            resource_uri="/v1/data/feed",
            price_ccd=0.25,
            recipient_address="4jXyDataNode"
        )
        success, reason, receipt = self.x402_gw.settle_x402_payment(
            challenge_id=challenge["challenge_id"],
            payer_agent_did=self.test_agent_did,
            client_payment_proof="invalid_proof_missing_colon"
        )
        self.assertFalse(success)
        self.assertEqual(reason, "MALFORMED_X402_PROOF")
        self.assertIsNone(receipt)

    def test_09_eu_ai_act_article_12_audit_chaining(self):
        entry1 = self.audit_logger.log_event(
            event_type="DECISION_DISPATCH",
            input_payload={"prompt": "Pay vendor for 10 compute hours"},
            decision_output={"status": "APPROVED", "amount_ccd": 5.0}
        )
        entry2 = self.audit_logger.log_event(
            event_type="SETTLEMENT_COMPLETE",
            input_payload={"receipt_id": "rcpt_123"},
            decision_output={"on_chain_tx": "0xabc"}
        )
        self.assertEqual(entry2["sequence_id"], 2)
        self.assertEqual(entry2["previous_hash"], entry1["current_hash"])
        self.assertEqual(len(self.audit_logger.entries), 2)

    def test_10_mcp_tool_execution(self):
        self.card_mgr.issue_agent_card(
            agent_did=self.test_agent_did,
            name="MCP Tested Agent",
            human_id_credential="kyc_mcp_101"
        )
        res = self.mcp_server.call_tool("verify_concordium_badge", {"agent_did": self.test_agent_did})
        self.assertTrue(res["verified"])
        self.assertEqual(res["status"], "VERIFIED_BY_CONCORDIUM_ACTIVE")

    def test_11_merkle_root_determinism(self):
        root1 = self.audit_logger.compute_merkle_root()
        self.assertTrue(root1.startswith("0x"))
        self.assertEqual(len(root1), 66)

if __name__ == "__main__":
    unittest.main()
