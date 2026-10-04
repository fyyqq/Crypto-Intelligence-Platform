"""Peer groups ("same use case") for the coin page's Similar Coins slider.

Each coin's business-model category (coins.business_model_category, see
coin_category_service.py) maps to ONE peer group below: SAND ("User-Generated
Metaverse Game") and MANA ("Virtual World Metaverse") both land in
"Metaverse & Virtual Worlds", so each shows the other. Similar coins are the
largest coins (by market cap) in the same group.

The groups and the rules mapping category labels onto them were written by
Claude Code (2026-10-05) after reviewing all 1,121 distinct labels of the top
1,500 coins; PEER_GROUPS is also the fixed list OpenRouter must choose from
when it (re)classifies a coin weekly. Rules are tried in order; the first
match wins, so specific groups come before broad ones.
"""

import re

_RULES: list[tuple[str, str]] = [
    # --- derivatives of other assets (only similar to each other) ---
    ("Interest-Bearing Lending Receipts", r"interest-bearing|staked aave"),
    ("Wrapped & Bridged Assets", r"^wrapped (?!bitcoin yield)|^bridged|custodial wrapped|exchange wrapped|icp native bitcoin|wrapped crypto insurance"),
    ("Liquid Staking Tokens", r"liquid staked|liquid restaked|restaked eth|staked eth|restaked sol|staked sol"),
    ("Liquid Staking & Restaking Protocols", r"liquid staking|restaking|validator club|distributed validator"),
    # --- tokenized real-world assets ---
    ("Tokenized Gold & Commodities", r"tokenized (gold|silver|uranium|emeralds)"),
    ("Tokenized Treasuries & Bonds", r"treasur|bond etf|tips bond|fixed-income|interest rate benchmark"),
    ("Tokenized Stocks & ETFs", r"tokenized .*(stock|etf|shares|pre-ipo)|tokenized stocks|stock lending|pre-market asset"),
    # --- stablecoins ---
    ("Yield-Bearing Stablecoins", r"yield-bearing|native-yield usd|staked (usd|usdt|crvusd|frax|synthetic)|bonded stablecoin|auto-yield stablecoin|yield stablecoin|stablecoin yield"),
    ("Decentralized & Synthetic Stablecoins", r"synthetic (dollar|usd)|decentralized usd|crypto-backed|overcollateralized|algorithmic stablecoin|delta-neutral|curve native|aave native|multi-backed|fractional-algorithmic|bitcoin-backed|stablecoin (protocol|credit|governance|platform)|deobank|stablecoin lending|elastic-supply"),
    ("Fiat-Backed Stablecoins", r"stablecoin$|tokenized us dollar|steem platform stablecoin"),
    # --- memes ---
    ("AI Meme Coins", r"\bai\b.*meme|meme.*\bai\b|ai-inspired|ai-generated frog"),
    ("Animal Meme Coins", r"(dog|cat|frog|wolf|hippo|animal|banana|pepe).*meme|meme.*(dog|cat|frog)|dog meme ecosystem"),
    ("Celebrity & Political Memes", r"(celebrity|political|influencer|streamer|satirical|elon).*meme"),
    ("Token & Meme Launchpads", r"launchpad|launcher|token creation|launch framework|token auction|creator token|asset-paired coin"),
    ("Meme Coins", r"meme|troll face|original meme currency"),
    ("Decentralized AI & Machine Learning", r"bittensor"),
    ("Health & Science", r"medical|health|science|longevity|research rewards"),
    ("Bitcoin Layer 2 & BTCfi", r"bitcoin (layer 2|staking|defi|restaking|lending|sidechain|smart contract|zk|omnichain|liquidity|lightning|cross-chain|asset protocol|yield)|bitcoin-(secured|powered|ethereum|merged)|brc-20|wrapped bitcoin yield|impermanent-loss-free btc|bitcoin dca"),
    ("Layer 2 Scaling", r"zk rollup layer 2|zk modular layer 2"),
    ("Prediction Markets & Betting", r"prediction|betting|casino|igaming|lottery|fortune"),
    ("DePIN & Physical Networks", r"wireless|wifi|mobile (network|carrier)|esim|iot|mapping|camera|gnss|location data|satellite|energy|vehicle|car data|mobile data|weather|depin|robotics|sharing economy|spatial|network infrastructure|vpn"),
    # --- exchanges & trading ---
    ("Exchange Tokens", r"exchange (utility|chain|layer 2|& wallet)|regulated exchange|exchange-backed|instant exchange|bankrupt exchange|multi-asset trading platform"),
    ("Perpetuals & Derivatives", r"perpetual|options|leverage|derivatives|gas futures"),
    ("Trading Bots & Analytics", r"trading (bot|terminal|platform|wallet|strategies|agent)|telegram trading|social trading|automated trading|analytics|intelligence platform|dex analytics|crypto research"),
    ("DEX & Liquidity", r"\bdex\b|\bamm\b|market maker|trading infrastructure|swap|liquidity|order book|rfq"),
    ("Lending & Borrowing", r"lending|borrowing|loans|credit (marketplace|allocator|network|history)|money market"),
    ("Yield & Asset Management", r"yield|vault|asset management|fund management|index fund|risk tranche|investment dao|fund platform"),
    # --- Bitcoin ecosystem ---
    ("Bitcoin Layer 2 & BTCfi", r"bitcoin (layer 2|staking|defi|restaking|lending|sidechain|smart contract|zk|omnichain|liquidity|lightning|liquid|cross-chain|asset protocol|yield)|bitcoin-(secured|powered|ethereum|merged)|brc-20|runes|wrapped bitcoin yield|impermanent-loss-free btc|bitcoin dca"),
    # --- AI ---
    ("AI Agents", r"ai agent|autonomous ai|multi-agent|agent (network|payments)|ai (crypto copilot|personal finance|defi)|sharded chain for ai"),
    ("Decentralized AI & Machine Learning", r"machine learning|\bml\b|ai (inference|model|training|compute|output|oracle|data|governance)|bittensor|\bagi\b|federated ai|useful-work ai|ai-powered layer 1|verifiable ai|human-verified ai|ai-enhanced data|ai web-data|ai robotics|ai infrastructure|uncensored ai"),
    ("AI Applications", r"\bai\b|ai-"),
    # --- infrastructure ---
    ("Decentralized GPU & Compute", r"gpu|compute|cloud computing|serverless|rendering|edge compute|video transcoding|hosting network|computing (network|marketplace|layer)|computation"),
    ("Decentralized Storage & Data", r"storage|file sharing|database|data (lake|indexing|network|availability|warehouse|layer|exchange|marketplace)|permanent data|rpc network|programmable data|knowledge graph|data storage"),
    ("Oracles", r"oracle|randomness"),
    ("DePIN & Physical Networks", r"wireless|wifi|mobile (network|carrier)|esim|iot|mapping|camera|gnss|location data|satellite|energy|vehicle|car data|weather|depin|robotics|sharing economy|spatial|network infrastructure|vpn"),
    ("Zero-Knowledge Infrastructure", r"\bzk\b|zero-knowledge|prover|coprocessor|proof verification"),
    ("Privacy", r"privacy|private|shielded|mixer|mimblewimble|zcash|mixnet|confidential|encrypted|fhe|threshold cryptography|mpc"),
    # --- consumer ---
    ("Metaverse & Virtual Worlds", r"metaverse|virtual world|virtual property|earth-mapped|land platform"),
    ("Fan & Sports Tokens", r"fan token|sports|fan platform|formula 1|esports fan"),
    ("Move & Watch-to-Earn Apps", r"to-earn (fitness|reward|social|camera)|move-to-earn|walk-to-earn|watch-to-earn"),
    ("Web3 Gaming", r"game|gaming|play-to-earn|tap-to-earn|rpg|shooter|chess|esports|loot|axie|maplestory|battler|guild"),
    ("NFTs & Collectibles", r"nft|collectible|digital art|art ownership|trading card"),
    ("Prediction Markets & Betting", r"prediction|betting|casino|igaming|lottery|fortune"),
    ("Social & Creator Economy", r"social|creator|blogging|content|messaging|group chat|music|film|streaming|quests|marketing|ad network|ad rewards|creative economy|anime|k-pop|idol|entertainment|education|knowledge q&a|encyclopedia|talent|freelance"),
    ("Wallets & Crypto Apps", r"wallet|account abstraction|smart account|neobank|super app|wealth app|financial services|asset services|community app"),
    ("Identity & Reputation", r"identity|personhood|reputation|attestation|credential|domain name|name service|notarization"),
    ("Cross-Chain Interoperability", r"cross-chain|bridge|omnichain|interchain|interoperab|chain abstraction|intent|messaging protocol"),
    ("Tokenized Real-World Assets", r"rwa|real estate|tokeniz|trade finance|invoice|agriculture|carbon|luxury|securities"),
    ("Payments", r"payment|remittance|cash|settlement|card|invoicing|payroll|commerce|shopping|travel|mileage|loyalty|rewards|voucher|gateway|crypto-fiat"),
    ("Layer 2 Scaling", r"layer 2|rollup|\bl2\b|layer 3|superchain|scaling|sequencer|evm extension|svm extension|evm on solana|evm chain on near"),
    ("Security & Developer Infrastructure", r"security|threat|bug bounty|cybersecurity|node infrastructure|keeper|automation|code collaboration|blockchain data|indexing|web3 operating system|arbitration|insurance"),
    ("Health & Science", r"medical|health|science|longevity|research rewards"),
    ("Enterprise Blockchains", r"enterprise|supply chain|logistics|trade|institutional|regulated|compliant|sharia|middle east"),
    ("Governance & DAOs", r"dao|governance"),
    ("Proof-of-Work Currencies", r"proof-of-work|digital cash|electronic cash|bitcoin fork|store of value|payment currency|asic-resistant|currency|big-block"),
    ("Gas & Ecosystem Tokens", r"gas (token|fees)|utility token|ecosystem (token|platform)|deflationary|defi protocol token|defi utility"),
    ("Smart Contract Platforms (Layer 1)", r"layer 1|smart contract|blockchain|platform|chain|network|parachain|hashgraph|ledger|dag"),
]

# Labels the rules above would file under a less useful group (e.g. NEAR's
# "Sharded Chain for AI Agents" should sit with other Layer 1s, XLM with XRP).
_OVERRIDES: dict[str, str] = {
    "Sharded Chain for AI Agents": "Smart Contract Platforms (Layer 1)",
    "Research-Driven Smart Contract Platform": "Smart Contract Platforms (Layer 1)",
    "Trading-Optimized Parallel EVM": "Smart Contract Platforms (Layer 1)",
    "Proof-of-Liquidity Layer 1": "Smart Contract Platforms (Layer 1)",
    "Native-Yield Layer 2": "Layer 2 Scaling",
    "Hybrid Compute Layer 2": "Layer 2 Scaling",
    "Universal ZK Compute Protocol": "Zero-Knowledge Infrastructure",
    "Verifiable Data Infrastructure": "Zero-Knowledge Infrastructure",
    "Fixed-Rate Lending & Stablecoin": "Lending & Borrowing",
    "Institutional Lending Yield Vault": "Yield-Bearing Stablecoins",
    "Decentralized Cloud Infrastructure": "Decentralized GPU & Compute",
    "Payments & Asset Tokenization Network": "Payments",
    "TRON DeFi & Meme Platform": "DEX & Liquidity",
    "AI Agent Launchpad": "AI Agents",
    "Mobile Esports Gaming": "Web3 Gaming",
    "K-Pop Fan Platform": "Social & Creator Economy",
    "Bitcoin-Themed BNB Token": "Meme Coins",
    "Korean Heritage Token": "Gas & Ecosystem Tokens",
    "TRON DeFi Token": "Gas & Ecosystem Tokens",
}

_COMPILED = [(group, re.compile(rx, re.I)) for group, rx in _RULES]

PEER_GROUPS: list[str] = list(dict.fromkeys(group for group, _ in _RULES))


def peer_group(category: str | None) -> str | None:
    """The peer group for a business-model category label, or None."""
    if not category:
        return None
    if category in _OVERRIDES:
        return _OVERRIDES[category]
    for group, rx in _COMPILED:
        if rx.search(category):
            return group
    return None
