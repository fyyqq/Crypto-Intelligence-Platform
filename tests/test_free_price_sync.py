"""Stored prices are refreshed from the exchange list, then DexScreener by contract, never from a lookalike."""

from app.services import free_price_sync as fps


def coin(cmc_id, symbol, price, cap=1000.0, contract=""):
    return {"cmc_id": cmc_id, "symbol": symbol, "price": price, "market_cap": cap, "contract": contract}


HUB = {"ETC": {"price": 8.05, "pct_24h": -1.5}, "SI": {"price": 0.0176, "pct_24h": 2.0}}


def test_exchange_price_updates_price_change_and_scales_market_cap():
    ups = fps.compute_updates([coin(1, "ETC", 8.37, cap=1200.0)], HUB, dex_fetch=lambda a: {})
    assert ups[1]["price"] == 8.05 and ups[1]["pct_24h"] == -1.5
    assert round(ups[1]["market_cap"], 2) == round(1200.0 * 8.05 / 8.37, 2)


def test_a_lookalike_ticker_far_from_the_stored_price_is_not_trusted_and_goes_to_dex():
    asked = []

    def dex(addresses):
        asked.append(addresses)
        return {"0x" + "ab" * 20: (0.00002158, 4.0)}

    c = coin(2, "SI", 0.0000244, contract="0x" + "ab" * 20)  # Sealwifhat: shares SI with Super Inu
    ups = fps.compute_updates([c], HUB, dex_fetch=dex)
    assert asked == [["0x" + "ab" * 20]]
    assert ups[2]["price"] == 0.00002158 and ups[2]["pct_24h"] == 4.0


def test_native_placeholder_contracts_and_unchanged_prices_are_skipped():
    ups = fps.compute_updates(
        [coin(3, "ETH", 5.0, contract="0x" + "e" * 40), coin(4, "ETC", 8.05)], HUB, dex_fetch=lambda a: (_ for _ in ()).throw(AssertionError("no DEX call expected")),
    )
    assert ups == {}


def test_a_failing_dex_batch_does_not_stop_the_exchange_updates():
    def boom(addresses):
        raise RuntimeError("429")

    ups = fps.compute_updates([coin(1, "ETC", 8.37), coin(9, "ZZZ", 1.0, contract="0x" + "a" * 40)], HUB, dex_fetch=boom)
    assert set(ups) == {1}


def test_dex_batch_picks_the_deepest_pool_of_the_base_token():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"pairs": [
                {"baseToken": {"address": "0xAAA" + "1" * 20}, "priceUsd": "1.0", "liquidity": {"usd": 5000}, "priceChange": {"h24": 1}},
                {"baseToken": {"address": "0xaaa" + "1" * 20}, "priceUsd": "2.0", "liquidity": {"usd": 90000}, "priceChange": {"h24": -3}},
                {"baseToken": {"address": "0xbbb" + "1" * 20}, "priceUsd": "9.0", "liquidity": {"usd": 10}, "priceChange": {}},  # too shallow
                {"baseToken": {"address": "0xccc" + "1" * 20}, "priceUsd": "3.0", "liquidity": {"usd": 5000}},
            ]}

    class Client:
        def get(self, url):
            return Resp()

    got = fps.fetch_dex_prices(["x"], client=Client())
    assert got == {"0xaaa" + "1" * 20: (2.0, -3.0), "0xccc" + "1" * 20: (3.0, None)}


def test_dex_stops_after_repeated_failures_and_the_rotating_slice_advances(monkeypatch):
    monkeypatch.setattr(fps.time, "sleep", lambda s: None)
    coins = [coin(i, f"T{i}", 1.0, contract="0x" + f"{i:040x}") for i in range(1, 200)]
    calls = []

    def boom(addresses):
        calls.append(len(addresses))
        raise RuntimeError("429")

    fps.compute_updates(coins, {}, dex_fetch=boom, top=30, rotating=60)
    assert fps.DEX_MAX_FAILURES <= len(calls) <= fps.DEX_MAX_FAILURES + fps.DEX_WORKERS  # gave up instead of hammering the API

    fps._rotation = 0
    first = [c["cmc_id"] for c in fps._dex_selection(coins, 30, 60)]
    second = [c["cmc_id"] for c in fps._dex_selection(coins, 30, 60)]
    assert first[:30] == second[:30] == list(range(1, 31))  # best-ranked always included
    assert first[30:] == list(range(31, 91)) and second[30:] == list(range(91, 151))


def test_only_evm_and_solana_addresses_are_sent():
    assert fps._is_real_contract("0x" + "a" * 40) and fps._is_real_contract("9DHe3pycTuymFk4H4bbPoAJ4hQrr2kaLDF6J6aAKpump")
    assert not fps._is_real_contract("ibc/126DA09104B71B164883842B769C0E9EC1486C0887D27A9999E395C2C8FB5682")
    assert not fps._is_real_contract("0x" + "e" * 40) and not fps._is_real_contract("") and not fps._is_real_contract("1234")
