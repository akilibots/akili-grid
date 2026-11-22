# akili-grid

A bounded moving grid for dYdX Chain. This implementation replaces the retired
dYdX v3 integration.

`bounds.low`, `high` and `step` define an evenly spaced grid. `start.order` selects
buy or sell, `start.size` sets the initial quantity, and `start.price = 0` uses the
current order-book midpoint. The starting price must be within the bounds.
The initial order is snapped to a grid level. Once filled, the bot maintains
`orders.below` buys and `orders.above` sells around the latest completed level,
each of `orders.size`. Multiple observed fills are processed before rebuilding.

Cancelled unfilled tracked orders are recreated with new client IDs. A terminated
partially filled order stops execution for position reconciliation. The bot does
not guess the missing quantity. Grid state uses integer level indices so JSON
serialization cannot turn arithmetic price keys into strings.

Matched profit pairs opposite fills one grid level apart and allocates actual
fees by quantity. It is not total account P&L. `stop.price` must be zero; a stop-loss
strategy is not implemented.

## Requirements and configuration

Docker builds use Python 3.15.2. Copy `.env.example` to `.env`, set
`DYDX_MNEMONIC` to the mnemonic of a dYdX Chain wallet, then edit
`data/strategy.json`. The wallet must match `exchange.address` and have collateral
in the configured cross-margin subaccount. A v3 API key or STARK key cannot be used.
Never commit `.env`, a wallet mnemonic, or runtime state.

The example selects **testnet**. Set `exchange.network`, `indexer`, `websocket`
and `node` together when changing networks. `node` is a TLS gRPC host and port,
without an HTTP prefix. Subaccounts 0 through 127 are supported. `poll_seconds`
controls indexer polling. These bots do not use a v3 account WebSocket.
Configuration can instead be supplied as JSON5 in the `strategy` environment
variable. Strategy settings are bound to saved state; changing an active strategy
requires reconciling its existing orders first.

Optional notifications use `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
Telegram failures are logged without changing order execution.

## Run

```sh
cp .env.example .env
# Edit .env and data/strategy.json before starting.
docker compose build
docker compose up -d
docker compose logs -f
```

Compose mounts `./data` so state survives container replacement. Stop the process
before changing state. Stopping a bot leaves exchange orders in place; inspect and
cancel them through the exchange if needed. Only one process may use a data directory.
Use a separate directory and subaccount for each strategy.

For a local Python installation, install the native build tools required by
`coincurve` and the wallet dependencies, then use:

```sh
python3 -m venv .venv
. .venv/bin/activate
PIP_BUILD_CONSTRAINT="$PWD/build-constraints.txt" python3 -m pip install -r requirements-dev.txt
```

The dYdX SDK currently constrains some signing dependencies to older compatible
versions. `build-constraints.txt` supplies the build tools expected by coincurve 20;
Docker installs the native build prerequisites. Runtime dependency versions must
continue to satisfy `python3 -m pip check`.

## Recovery and order handling

`data/state.json` records strategy progress. `data/exchange.json` journals client
IDs **before** order submission. Keep both files together. An ambiguous timeout
is reconciled against its existing client ID; it never automatically becomes a
new trade. If an order remains unknown, execution stops for reconciliation.
Do not delete the journal to bypass an error.

Legacy v3 state is incompatible. Reconcile any previous orders and positions,
archive the old state, and start the Chain bot with a fresh data directory.
The exchange journal is bound to its wallet, network and subaccount.

Limit orders use Chain long-term orders with a default 24-hour expiry. Prices
are aligned to market ticks, and sizes must be exact multiples of `stepSize`.
Market orders use short-term IOC orders with a side-aware slippage bound.
A cancellation must be confirmed before a replacement is submitted.
Profit figures use actual fill prices and trading fees. They exclude funding,
network transaction fees and unrealised position value.

## Tests

```sh
docker build --target test -t bot-test .
docker run --rm --network none bot-test
```

The regression suite runs without exchange access or credentials. It exercises
strategy transitions, restart recovery, order identities, fills and cancellations.
SDK tests build real order protobuf messages and derive a public test wallet
locally. Passing these tests does not establish live execution or profitability.

Software is supplied as is under the repository licence.
