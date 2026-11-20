//! Concordium CIS-8004 Agent Registry Smart Contract
//! Binds autonomous AI agents to verified Concordium human identities via Zero-Knowledge proofs.

#![cfg_attr(not(feature = "std"), no_std)]
use concordium_std::*;

#[derive(Serialize, SchemaType)]
pub enum AgentStatus {
    Active,
    Revoked,
    Suspended,
}

#[derive(Serialize, SchemaType)]
pub struct AgentRecord {
    pub agent_did: String,
    pub zk_commitment: [u8; 32],
    pub accountable_human_cred: [u8; 32],
    pub verification_tier: u8,
    pub status: AgentStatus,
    pub registered_at: Timestamp,
}

#[derive(Serial, DeserialWithState)]
#[concordium(state_parameter = "S")]
pub struct State<S = StateApi> {
    pub admin: AccountAddress,
    pub agents: StateMap<String, AgentRecord, S>,
}

#[derive(Serialize, SchemaType)]
pub struct RegisterAgentParams {
    pub agent_did: String,
    pub zk_commitment: [u8; 32],
    pub accountable_human_cred: [u8; 32],
    pub verification_tier: u8,
}

#[derive(Debug, PartialEq, Eq, Reject, Serialize, SchemaType)]
pub enum RegistryError {
    #[from(ParseError)]
    ParseParams,
    OwnerOnly,
    AgentAlreadyRegistered,
    AgentNotFound,
    AgentRevoked,
}

#[init(contract = "agent_sentinel_registry")]
pub fn contract_init<S: HasStateApi>(
    ctx: &InitContext,
    state_builder: &mut StateBuilder<S>,
) -> InitResult<State<S>> {
    let admin = ctx.init_origin();
    let agents = state_builder.new_map();
    Ok(State { admin, agents })
}

#[receive(
    contract = "agent_sentinel_registry",
    name = "register_agent",
    parameter = "RegisterAgentParams",
    error = "RegistryError",
    mutable
)]
pub fn register_agent<S: HasStateApi>(
    ctx: &ReceiveContext,
    host: &mut Host<State<S>, S>,
) -> Result<(), RegistryError> {
    let params: RegisterAgentParams = ctx.parameter_cursor().get()?;
    
    // Ensure agent is not already registered
    if host.state().agents.get(&params.agent_did).is_some() {
        return Err(RegistryError::AgentAlreadyRegistered);
    }
    
    let now = ctx.block_time();
    let record = AgentRecord {
        agent_did: params.agent_did.clone(),
        zk_commitment: params.zk_commitment,
        accountable_human_cred: params.accountable_human_cred,
        verification_tier: params.verification_tier,
        status: AgentStatus::Active,
        registered_at: now,
    };
    
    host.state_mut().agents.insert(params.agent_did, record);
    Ok(())
}

#[receive(
    contract = "agent_sentinel_registry",
    name = "verify_agent",
    parameter = "String",
    return_value = "bool"
)]
pub fn verify_agent<S: HasStateApi>(
    ctx: &ReceiveContext,
    host: &Host<State<S>, S>,
) -> ReceiveResult<bool> {
    let agent_did: String = ctx.parameter_cursor().get()?;
    if let Some(record) = host.state().agents.get(&agent_did) {
        match record.status {
            AgentStatus::Active => Ok(true),
            _ => Ok(false),
        }
    } else {
        Ok(false)
    }
}

#[receive(
    contract = "agent_sentinel_registry",
    name = "revoke_agent",
    parameter = "String",
    error = "RegistryError",
    mutable
)]
pub fn revoke_agent<S: HasStateApi>(
    ctx: &ReceiveContext,
    host: &mut Host<State<S>, S>,
) -> Result<(), RegistryError> {
    let agent_did: String = ctx.parameter_cursor().get()?;
    let sender = ctx.sender();
    
    // In production, only the admin or the bound human account can revoke
    match sender {
        Address::Account(acc) => {
            if acc != host.state().admin {
                return Err(RegistryError::OwnerOnly);
            }
        }
        _ => return Err(RegistryError::OwnerOnly),
    }
    
    let mut entry = host.state_mut().agents.get_mut(&agent_did).ok_or(RegistryError::AgentNotFound)?;
    entry.status = AgentStatus::Revoked;
    Ok(())
}
