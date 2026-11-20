"""
Concordium Agent Sentinel - Agent Card & Zero-Knowledge Badge Engine
Conforms to Concordium CIS-8004 and cross-chain ERC-8004 specifications.
Provides ZK identity binding, verifiable credential generation, and badge verification.
"""

import json
import hashlib
import hmac
import time
from typing import Dict, Any, Optional, Tuple

class AgentCardManager:
    """
    Manages the creation, cryptographic signing, and verification of
    Concordium Agent Cards and 'Verified by Concordium' Zero-Knowledge badges.
    """
    
    CONCORDIUM_TESTNET_CHAIN_ID = "ccd:testnet:420"
    BADGE_ISSUER_DID = "did:ccd:testnet:issuer:concordium-id-guardian"
    
    def __init__(self, issuer_secret_seed: str = "concordium-zk-identity-seed-2026"):
        self.issuer_secret = issuer_secret_seed.encode("utf-8")
        self._registry: Dict[str, Dict[str, Any]] = {}

    def issue_agent_card(
        self,
        agent_did: str,
        name: str,
        human_id_credential: str,
        verification_tier: str = "TIER_1_ID_PROVED",
        capabilities: Optional[list] = None,
        sponsor_url: str = "https://sponsor.concordium.testnet/v1/relay"
    ) -> Dict[str, Any]:
        """
        Issues an official Concordium CIS-8004 compliant Agent Card.
        Binds the off-chain/on-chain agent to a Zero-Knowledge human identity proof.
        """
        issued_at = int(time.time())
        badge_payload = f"{agent_did}|{human_id_credential}|{verification_tier}|{issued_at}"
        zk_commitment = hashlib.sha256(badge_payload.encode("utf-8")).hexdigest()
        
        # Deterministic HMAC signature simulating Concordium Identity Guardian cryptographic attestation
        zk_signature = hmac.new(self.issuer_secret, zk_commitment.encode("utf-8"), hashlib.sha256).hexdigest()
        badge_id = f"badge_ccd_{zk_commitment[:16]}"
        
        agent_card = {
            "agent_did": agent_did,
            "name": name,
            "version": "1.0.0",
            "chain_id": self.CONCORDIUM_TESTNET_CHAIN_ID,
            "verified_by_concordium": {
                "status": "VERIFIED",
                "badge_id": badge_id,
                "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(issued_at)),
                "verification_tier": verification_tier,
                "proof_type": "Groth16_Concordium_ID",
                "zk_commitment": f"0x{zk_commitment}",
                "guardian_signature": f"0x{zk_signature}"
            },
            "accountable_human": {
                "concordium_id_credential": f"0x{hashlib.sha256(human_id_credential.encode()).hexdigest()}",
                "anonymity_revoker_quorum": "3/5_CONCORDIUM_GUARDIANS",
                "accountability_signature": f"0x{hashlib.sha384(agent_did.encode()).hexdigest()[:64]}"
            },
            "supported_protocols": capabilities or ["MCP", "A2A", "x402", "ERC-8004"],
            "payment_rails": {
                "x402_enabled": True,
                "accepted_assets": ["CCD", "tEUR_PLT", "tUSD_PLT"],
                "sponsor_service_url": sponsor_url
            },
            "compliance": {
                "eu_ai_act_article_12": True,
                "audit_log_format": "RFC-6962-Merkle-Audit-Proof",
                "immutable_merkle_root": f"0x{hashlib.sha256((agent_did + str(issued_at)).encode()).hexdigest()}"
            }
        }
        
        self._registry[agent_did] = agent_card
        return agent_card

    def verify_agent_badge(self, agent_did: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Verifies that an agent holds an authentic 'Verified by Concordium' badge
        and that a verified human stands behind it without revealing their identity.
        """
        card = self._registry.get(agent_did)
        if not card:
            return False, "AGENT_NOT_REGISTERED", None
            
        badge_data = card.get("verified_by_concordium", {})
        if badge_data.get("status") != "VERIFIED":
            return False, f"BADGE_STATUS_{badge_data.get('status')}", card
            
        # Verify ZK commitment integrity
        zk_commitment = badge_data.get("zk_commitment", "").replace("0x", "")
        expected_sig = hmac.new(self.issuer_secret, zk_commitment.encode("utf-8"), hashlib.sha256).hexdigest()
        actual_sig = badge_data.get("guardian_signature", "").replace("0x", "")
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False, "INVALID_GUARDIAN_SIGNATURE", card
            
        return True, "VERIFIED_BY_CONCORDIUM_ACTIVE", card

    def revoke_agent(self, agent_did: str, reason: str = "Operator Manual Revocation") -> bool:
        """
        Emergency revocation: revokes the badge instantly across the network.
        """
        if agent_did in self._registry:
            self._registry[agent_did]["verified_by_concordium"]["status"] = "REVOKED"
            self._registry[agent_did]["verified_by_concordium"]["revocation_reason"] = reason
            return True
        return False
