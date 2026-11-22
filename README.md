<p align="center"><img src="https://raw.githubusercontent.com/akilibots/.github/main/assets/akilibots-icon.svg" width="144" alt="Akilibots"></p>

# Welcome to akili-grid!

[![Python 3.15.2](https://img.shields.io/badge/Python-3.15.2-6966FF?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![dYdX Chain](https://img.shields.io/badge/dYdX_Chain-0B0B18)](https://github.com/akilibots/akili-grid)
[![Docker tests](https://github.com/akilibots/akili-grid/actions/workflows/tests.yaml/badge.svg?branch=prod)](https://github.com/akilibots/akili-grid/actions/workflows/tests.yaml)
[![Telegram](https://img.shields.io/badge/Telegram-community-6966FF?logo=telegram&logoColor=white)](https://t.me/+9F0CZj8emLc2YTY0)

> **Updated 22 November 2026:** dYdX Chain, Python 3.15.2, refreshed dependencies, durable order recovery and Docker regression tests.

Jambo! and welcome! **akili-grid** buys and sells around a bounded price grid. You choose the levels, spacing and quantities; the bot keeps the orders moving as trades fill.

The word **akili** means brain or mind in Swahili. These bots are non-opinionated: you set the strategy and stay in control. They grew out of wanting that little extra tweak that commercial bots always seemed to miss.

## Get it running

You need Git, Docker with Compose, and a funded dYdX **Chain testnet** wallet to
use the supplied example. The bot needs the wallet's mnemonic and a matching
Chain address. Old v3 API keys, STARK keys and v3 state do not work here.

1. Clone the repository and create your environment file:

```sh
git clone https://github.com/akilibots/akili-grid.git
cd akili-grid
cp .env.example .env
```

2. Edit `.env`. Set `DYDX_MNEMONIC` to your Chain wallet's mnemonic, in quotes.
   Leave the Telegram values empty if you do not want notifications.
3. Edit [`data/strategy.json`](data/strategy.json). Set `exchange.address` to that
   wallet's address, check its subaccount and review the strategy quantities and
   prices. The sample endpoints select **testnet**.

4. Build and start the bot:

```sh
docker compose up --build -d
docker compose logs -f
```

To stop it:

```sh
docker compose down
```

Stopping the process leaves its exchange orders in place. Check and cancel those
orders separately when needed. Do not run two instances from the same data folder.

## How it works

`bounds.low`, `high` and `step` define an evenly spaced grid. `start.order` selects
buy or sell, `start.size` sets the initial quantity, and `start.price = 0` uses the
current order-book midpoint. The starting price must be within the bounds.
The initial order is snapped to a grid level. Once filled, the bot maintains
`orders.below` buys and `orders.above` sells around the latest completed level,
each of `orders.size`. Multiple observed fills are processed before rebuilding.

Cancelled unfilled tracked orders are recreated with new client IDs. A terminated
partially filled order stops execution for position reconciliation. The bot does
not guess the missing quantity.

Matched profit pairs opposite fills one grid level apart and allocates actual
fees by quantity. It is not total account P&L. `stop.price` must be zero; a stop-loss
strategy is not implemented.

## Configuration notes

| Setting | What to check |
| --- | --- |
| `main.market` | The perpetual market, such as `BTC-USD` |
| `exchange.address` | The Chain address matching `DYDX_MNEMONIC` |
| `exchange.subaccount` | A cross-margin subaccount from 0 to 127, with collateral |
| `exchange.network` | `testnet` or `mainnet` |
| `exchange.indexer`, `websocket`, `node` | Endpoints for the same selected network |
| `exchange.poll_seconds` | Seconds between status checks for the strategy loops |

The node value is a TLS gRPC host and port, without `http://` or `https://`.
Review market sizes and prices before running any sample. Quantities are in the
base asset, not a dollar budget. To use mainnet, change the network and all its
endpoints together and configure the corresponding wallet and collateral.

You can supply JSON5 through the `strategy` environment variable instead of the
strategy file. Settings are tied to saved strategy state; reconcile existing
orders before changing an active strategy. Telegram notifications use
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.

## Restarting and recovery

Compose mounts `./data`, so state survives a container replacement.
`data/state.json` records progress and `data/exchange.json` records client IDs
before order submission. Keep them together and keep them out of Git.

An uncertain submission is checked using its existing client ID. The bot does not
turn a timeout into a second trade. If it cannot reconcile an order, it stops so
you can inspect the exchange and saved state. Do not delete state to bypass an
error. Partial-fill and cancellation handling is described above.

For a v3 migration, reconcile old orders and positions first, archive the old
state, then start with a fresh data folder. Use a separate data folder and
subaccount for each strategy. Never commit wallet mnemonics or `.env`.

Limit orders use Chain long-term orders with a default 24-hour expiry. Prices
follow market ticks and sizes must be exact multiples of `stepSize`. Market
orders use short-term IOC orders with a slippage bound. Profit figures, where
reported, include actual fill prices and trading fees, but exclude funding,
network transaction fees and unrealised positions.

## Test it yourself

```sh
docker build --target test -t bot-test .
docker run --rm --network none bot-test
```

The suite uses simulated exchange responses with networking disabled. It covers
order handling and recovery; SDK checks also build and sign transactions locally.
Passing tests is not a promise of live execution or profitable trading.

<details>
<summary>Running directly with Python</summary>

Use Python 3.15.2 and install the native C/C++ and Rust build tools required by
the wallet dependencies. Docker includes these prerequisites in its build stage.

```sh
python3 -m venv .venv
. .venv/bin/activate
PIP_BUILD_CONSTRAINT="$PWD/build-constraints.txt" python3 -m pip install -r requirements-dev.txt
python3 -m pip check
```

Export the values from `.env` into your shell, then run `python3 run.py`.
The direct Python entrypoint does not automatically read `.env`.
The dYdX SDK constrains some signing packages to older compatible versions;
`build-constraints.txt` supplies the build tools those packages require.

</details>

## The usual bit

This software is for educational purposes only. Do not risk money you are afraid
to lose. **USE THE SOFTWARE AT YOUR OWN RISK. THE AUTHORS AND ALL AFFILIATES ASSUME
NO RESPONSIBILITY FOR YOUR TRADING RESULTS.**

See [LICENSE](LICENSE) for the full terms.

Part of [Akilibots](https://github.com/akilibots). Come say jambo in [Telegram](https://t.me/+9F0CZj8emLc2YTY0).
