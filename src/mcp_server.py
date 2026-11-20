"""
Concordium Agent Sentinel - Model Context Protocol (MCP) Server
Exposes standardized tools for LLM agents (Claude, Cursor, custom agents)
to query the Concordium Agent Registry, verify ZK badges, and execute x402 payments.
"""

from typing import Dict, Any, List
from .agent_card import AgentCardManager
from .x402_gateway import X402Gateway
from .eu_ai_act_logger import EUAIActAuditLogger

class ConcordiumAgentRegistryMCPServer:
    """
    Standard Model Context Protocol (MCP) tool provider for Concordium.
    """
    
    def __init__(
        self,
        card_manager: AgentCardManager,
        x402_gw: X402Gateway,
        audit_logger: EUAIActAuditLogger
    ):
        self.card_manager = card_manager
        self.x402_gw = x402_gw
        self.audit_logger = audit_logger

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Returns JSON-RPC / MCP compatible tool schema definitions.
        """
        return [
            {
                "name": "verify_concordium_badge",
                "description": "Verifies whether a target AI agent holds an authentic 'Verified by Concordium' badge backed by a ZK human proof.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_did": {
                            "type": "string",
                            "description": "Decentralized identifier of the agent (did:ccd:testnet:agent:...)"
                        }
                    },
                    "required": ["agent_did"]
                }
            },
            {
                "name": "lookup_agent_card",
                "description": "Fetches the full Concordium CIS-8004 / ERC-8004 Agent Card for a registered agent.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_did": {
                            "type": "string",
                            "description": "Decentralized identifier of the agent."
                        }
                    },
                    "required": ["agent_did"]
                }
            },
            {
                "name": "request_x402_payment_challenge",
                "description": "Generates an HTTP 402 challenge for an API or resource payable in CCD/PLT.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "resource_uri": {"type": "string"},
                        "price_ccd": {"type": "number"},
                        "recipient_address": {"type": "string"}
                    },
                    "required": ["resource_uri", "price_ccd", "recipient_address"]
                }
            },
            {
                "name": "submit_x402_payment_proof",
                "description": "Settles an open x402 challenge by presenting signed transaction proof on Concordium Testnet.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "challenge_id": {"type": "string"},
                        "payer_agent_did": {"type": "string"},
                        "client_payment_proof": {"type": "string"}
                    },
                    "required": ["challenge_id", "payer_agent_did", "client_payment_proof"]
                }
            }
        ]

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches tool calls directly and logs the interaction to the EU AI Act audit ledger.
        """
        if tool_name == "verify_concordium_badge":
            agent_did = arguments["agent_did"]
            is_valid, reason, card = self.card_manager.verify_agent_badge(agent_did)
            
            self.audit_logger.log_event(
                event_type="MCP_BADGE_VERIFICATION",
                input_payload={"agent_did": agent_did},
                decision_output={"is_valid": is_valid, "reason": reason}
            )
            return {"verified": is_valid, "status": reason, "badge": card.get("verified_by_concordium") if card else None}

        elif tool_name == "lookup_agent_card":
            agent_did = arguments["agent_did"]
            is_valid, reason, card = self.card_manager.verify_agent_badge(agent_did)
            return {"found": is_valid, "agent_card": card}

        elif tool_name == "request_x402_payment_challenge":
            challenge = self.x402_gw.create_payment_challenge(
                resource_uri=arguments["resource_uri"],
                price_ccd=arguments["price_ccd"],
                recipient_address=arguments["recipient_address"]
            )
            return challenge

        elif tool_name == "submit_x402_payment_proof":
            success, reason, receipt = self.x402_gw.settle_x402_payment(
                challenge_id=arguments["challenge_id"],
                payer_agent_did=arguments["payer_agent_did"],
                client_payment_proof=arguments["client_payment_proof"]
            )
            self.audit_logger.log_event(
                event_type="MCP_X402_SETTLEMENT",
                input_payload=arguments,
                decision_output={"success": success, "reason": reason, "receipt": receipt}
            )
            return {"success": success, "reason": reason, "receipt": receipt}

        return {"error": f"Unknown tool: {tool_name}"}
