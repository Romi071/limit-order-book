# Algorithmic Limit Order Book (LOB) Matching Engine

An algorithmic Limit Order Book (LOB) matching engine and asynchronous exchange server built entirely in Python. Designed as a proof-of-concept mimicking institutional architecture, this engine focuses on computational efficiency, non-blocking network I/O, and a strictly bounded active memory footprint. It handles price-time priority matching, advanced execution types (IOC, FOK), partial fills, token-authenticated `O(1)` order cancellations and amendments, amortized `O(N)` heap garbage collection, real-time WebSocket depth broadcasting, and a batched asynchronous SQLite WAL ledger.

## Key Features

*   **Atomic Advanced Order Types:** Native support for GTC (Good-'Til-Cancelled), IOC (Immediate-Or-Cancel), and FOK (Fill-Or-Kill). FOK orders guarantee strict all-or-nothing execution via a surgical state-rollback mechanism verified against `min_lot_size` (`1e-8`) precision boundaries to prevent partial fills or false float-dust rejections.
*   **Maker/Taker ID Handshake & Collision-Safe Token Security:** Flattens matching execution into a continuous `O(K)` loop to seamlessly capture both the public `takerId` and `makerId` for every match, generating a traceable trade tape. Every order is issued a server-generated 16-character cryptographic hex `id` and `secret_token` (`uuid.uuid4().hex[:16]`) required for `O(1)` cancellations and amendments, alongside an optional `client_tag` for strategy metadata.
*   **Hybrid RAM/Disk Ledger Pattern:** The core matching engine operates 100% synchronously in RAM to maintain microsecond execution speeds. Network I/O and disk persistence are strictly decoupled into the asynchronous routing layer—streaming live L2 market depth over WebSockets and batch-committing executed trade receipts via a Producer-Consumer buffer into an ACID-compliant SQLite (WAL) database without blocking the matching loop.
*   **`O(1)` Order Cancellations & Active-Only Tracker Lifecycle:** Instead of physically scanning and removing orders from queues (`O(N)` bottleneck), the engine uses a hash map (`order_tracker`) exclusively indexing live, resting GTC orders to locate targets instantly and logically neutralize them in-place. Transient IOC/FOK orders and immediately filled GTC taker orders bypass tracker registration completely, and filled or cancelled resting orders are immediately purged (`del`) from `order_tracker` to guarantee zero memory leaks. Cancellations return the exact `cancelled_amount` to allow downstream market-making bots to deterministically compute fill deltas.
*   **Amortized `O(N)` Heap Garbage Collector & Object Pooling:** While lazy deletion keeps individual cancellations `O(1)`, heavy quoting cycles can leave dead price levels lingering inside the heaps. The engine increments a `cancel_count` whenever a cancellation depletes a price level below `min_lot_size` and triggers `run_garbage_collector()` at `gc_threshold` (1,000 depleted levels). Using `LOAD_FAST` local pointer caching, the GC strips dead prices, synchronizes `heapq_exists` flags, and restores the heap invariant via `heapq.heapify()` in amortized `O(1)` time. Empty `OrderQueue` shells remain cached in `bids` and `asks` as an in-memory object pool to eliminate CPython `malloc` overhead when prices revisit prior ticks.
*   **Dynamic Order Amendment (DRY):** Supports `O(1)` volume modification. Decreasing volume retains queue priority in-place, while increasing volume dynamically triggers a `cancel-and-replace` operation to the back of the queue while preserving the order's `id` and `secret_token` to maintain strict price-time fairness.
*   **Price-Time Priority (FIFO):** Utilizes Python's `collections.deque` to maintain strict First-In-First-Out execution for orders sitting at the same price level, ensuring absolute fairness in the queue.
*   **Logarithmic Price Discovery & Deduplication:** Implements Min-Heaps and Max-Heaps (`heapq`) to track the best bid and ask prices dynamically in `O(log N)` time. Each `OrderQueue` maintains an `O(1)` `heapq_exists` boolean state guard to prevent duplicate price pushes when new liquidity arrives at a previously cancelled price level still awaiting garbage collection.
*   **IEEE 754 Floating-Point Drift Armor:** Order exhaustion and price-level depletion are governed by strict `min_lot_size` (`1e-8`) tolerance boundaries rather than raw float equality. When a price level's volume drops below `1e-8` during matching, the price is popped from the heap (`heapq_exists = False`) and `empty_queue()` zeroes out residual float dust while evicting any trailing lazy-deleted ghost orders. Combined with a "Heal-on-Read" dust sweeper in `export_market`, the engine is immune to IEEE 754 residual float drift.
*   **Object Memory Optimization:** Employs Python's `__slots__` directive on all `Order` and `OrderQueue` objects. This disables dynamic `__dict__` allocation per object, drastically reducing RAM usage and speeding up attribute access for high-frequency object creation.
*   **Strict Boundary Safeguards:** Built-in validation intercepts invalid data (e.g., negative prices, sub-minimum lot volumes, invalid order types) at both the network gateway (via Pydantic) and object instantiation, throwing a `ValueError` or `TypeError` before bad data can taint the matching engine's state.

---

## Time Complexity Benchmarks

| Operation | Time Complexity | Implementation Mechanism |
| :--- | :--- | :--- |
| **Look up Best Bid/Ask** | `O(1)` | Reading the 0-index of the `heapq` arrays. |
| **Add New Price Level** | `O(log N)` | Pushing a new price float/int to the min/max heap (guarded by `heapq_exists`). |
| **Add Order to Queue** | `O(1)` | `deque.append()` at the specified price level. |
| **Execute Trade (Match)** | `O(K)` | Single `while` loop over `K` resting orders to capture Taker/Maker IDs and evict inactive ghosts. |
| **FOK Liquidity Dry-Run** | `O(K log N)` | Peek-and-Restore state rollback (popping/restoring `K` eligible price levels). |
| **Cancel / Amend Order** | `O(1)` | Hash map lookup + `secret_token` verification + logical state modification + tracker eviction. |
| **Heap Garbage Collection** | `O(N)` *(Amortized)* | Triggered every 1,000 depleted price levels via `LOAD_FAST` pointer filtering and `heapq.heapify()`. |

---

## Architecture & Logic Flow

1. **The Bouncer (`Order` Object):** Every incoming request is strictly filtered against minimum lot size (`1e-8`) and type constraints. The server generates two distinct 16-character UUID hex strings (`uuid.uuid4().hex[:16]`): a public `id` (exposed on the trade tape) and a private `secret_token` (returned only to the order creator as an authentication PIN for lifecycle modifications), alongside an optional user-defined `client_tag`.
2. **The Tracker (`order_tracker`):** Only `GTC` orders that survive immediate matching and rest in the book are logged into the global dictionary mapped as `{order_id: Order_Object}`. This grants instant `O(1)` lookup and authentication over active liquidity while immediately purging (`del`) filled or cancelled orders so dead IDs never accumulate in RAM.
3. **The Matching Loop (`add_order`):** 
    *   **FOK Dry-Run:** If an order is Fill-Or-Kill, the engine temporarily lifts price levels off the heap to verify sufficient liquidity (`order.amount - total_valid_liquidity >= self.min_lot_size`) before mutating any state. If liquidity is insufficient, the heap is restored and the order is killed instantly.
    *   **Taker Orders:** If a buy order crosses the best available ask (or vice versa), the engine aggressively sweeps the liquidity. It immediately evicts any leading lazy-deleted ghost orders (`maker_order.active == False`), handles partial or full fills, deletes exhausted maker orders from `order_tracker`, and records the Taker/Maker ID handshake. IOC orders that fail to fully fill evaporate here.
    *   **Maker Orders:** If a GTC order remains active after matching, it is registered in `order_tracker`, routed to its respective `OrderQueue` (reusing the pooled queue if the price was previously visited), and pushed to the heap if `heapq_exists` is `False`.
4. **Volume Mathematics, Dust Sweeping & Heap GC:** Price levels dynamically track aggregate volume. When a queue's volume drops below `min_lot_size` (`1e-8`) during matching, the price is popped from the heap (`heapq_exists = False`) and `empty_queue()` clears residual float dust and trailing ghost orders. When a cancellation depletes a price level below `1e-8`, `empty_queue()` is called and `cancel_count` increments—triggering `run_garbage_collector()` every 1,000 depleted levels to prune dead floats from the heaps in-place.

---

## Engineering Trade-offs

### 1. FOK Atomicity vs. Data Structures
Guaranteeing atomicity for Fill-Or-Kill (FOK) orders presents a unique systems design challenge. The engine must mathematically prove that sufficient volume exists at valid prices *before* mutating a single variable. 

In hardware-accelerated environments, professional exchanges often utilize contiguous memory arrays or Red-Black Trees (e.g., C++ `std::map`) to sequentially walk down the price levels in purely `O(K)` time without altering the data structure.

Because this engine relies on Python's `heapq` for ultra-fast `O(1)` best-price lookups and `O(log N)` insertions, looking at the *second* or *third* best price requires physically popping the best price off the heap. To solve this without triggering a catastrophic `O(N)` deep copy of the entire market depth, this engine utilizes a **Peek-and-Restore (State Rollback)** pattern. 

For FOK orders, the engine pops `K` eligible price levels, tallies the valid liquidity against `min_lot_size`, and immediately pushes the prices back onto the heap in `O(K log N)`. While this introduces a small multiplier constant to the time complexity, `K` remains exceptionally small in live markets, making it a highly efficient, memory-cheap compromise for a locally run Python matching engine.

### 2. Unified "Not Found / Already Filled" Lifecycle Responses & Object Pooling
In high-frequency trading architecture, matching engine RAM is reserved strictly for active liquidity. Retaining a historical index of every filled or cancelled `orderId` in `order_tracker` solely to differentiate between "Order Already Filled" and "Order Never Existed" introduces an unbounded memory leak over long sessions.

Following production exchange conventions (e.g., Binance/Bybit REST semantics), this engine deletes order IDs from `order_tracker` the exact microsecond they are filled or cancelled. Consequently, `/cancel` and `/amend` return a unified `HTTP 404 Not Found` (`success: False`, `cancelled_amount: 0`) whenever an ID is absent from the active tracker. Downstream algorithmic bots (which generate and track their own active orders locally) can deterministically infer that an absent ID with `cancelled_amount: 0` was 100% filled by a taker. Meanwhile, empty `OrderQueue` shells at depleted price ticks are intentionally retained in `bids` and `asks` as a lightweight (~768 bytes/level) **Object Pool**, trading a negligible, bounded RAM footprint on discrete tick grids for zero-allocation speed during repetitive market-maker re-quoting.

---

## Network Infrastructure & Persistence (`server.py`)

The core algorithmic matching logic is wrapped inside an asynchronous, non-blocking microservice architecture designed to handle concurrent order flow without race conditions or I/O bottlenecks:

*   **ASGI Server & Concurrency Control:** Powered by **FastAPI** and Uvicorn. To protect the in-memory `heapq` and `deque` structures from asynchronous race conditions during high-frequency state mutations, order ingestion, cancellation, and amendment are guarded by a strict `asyncio.Lock()` mutex that releases immediately after RAM execution.
*   **Strict Gateway Validation & Semantic HTTP Responses:** Utilizes **Pydantic** `BaseModel` schemas (`IncomingOrder`, `CancelOrder`, `AmendOrder`) backed by a Rust core to validate and type-check incoming JSON payloads at the network boundary. Lifecycle endpoints (`/cancel`, `/amend`) map the engine's structured dictionary responses directly to HTTP status codes: `200 OK` on successful state mutation (returning `cancelled_amount` or `old_amount`/`new_amount`/`priority_lost`), `401 Unauthorized` on a `PermissionError` (invalid `secret_token`), and a unified `404 Not Found` when targeting an order that was already filled, previously cancelled, or never existed.
*   **Concurrent WebSocket Broadcasting (`ConnectionManager`):** Encapsulates active client connections into a dedicated OOP manager. Whenever an order addition, successful cancellation, or successful amendment mutates the book, the L2 market snapshot is computed and broadcasted concurrently to all connected listeners via `asyncio.gather`, preventing slow clients from lagging the main event loop.
*   **Batched ACID SQLite WAL Ledger (`aiosqlite`):** Implements a non-blocking **Producer-Consumer** persistence architecture (`ledger.db`). Rather than bottlenecking the HTTP loop with single-fire disk commits, executed trades are appended in nanoseconds to an in-memory `logs_buffer`. An asynchronous background daemon (`sql_flusher`) wakes up every 100ms, atomically drains the buffer, and executes C-level batched `executemany` inserts with **Write-Ahead Logging (`PRAGMA journal_mode=WAL`)** enabled. Managed via FastAPI's `@asynccontextmanager` `lifespan` protocol, the teardown sequence enforces a final buffer drain upon shutdown to guarantee zero data loss.

---

## Usage & Asynchronous Stress Testing

### 1. Booting the Exchange Server
Initialize the ASGI server from the root directory (use `--reload` for development, or `--no-access-log` to mute terminal stdout I/O during high-frequency benchmarking):
```bash
# Development mode
uvicorn server:app --reload

# High-throughput benchmark mode (disables console logging bottleneck)
uvicorn server:app --no-access-log
```
*   **REST API & Swagger UI:** Navigate to `http://localhost:8000/docs` to interact with `POST /order` (returns execution receipts with `orderId`, `secret_token`, `client_tag`, resting `amount`, and immediate `fills`), `POST /cancel`, `POST /amend`, or `GET /depth`.
*   **Live WebSocket Feed:** Connect any WebSocket client to `ws://localhost:8000/stream` to receive real-time JSON broadcasts of the L2 order book state upon every market event.
*   **Persistent Trade Ledger:** Executed cross-spread trades are automatically batched and committed to `ledger.db` in the root directory (inspectable via VSCode's *SQLite Viewer* extension).

### 2. Running the High-Frequency Load Tester (`~2,200 TPS`)
The `load_tester.py` script contains an asynchronous stress-testing suite powered by `numpy` and `aiohttp`. Instead of relying on static file ingestion, the load tester spins up a single persistent TCP session (`ClientSession`) and utilizes `asyncio.gather` to bombard the `POST /order` endpoint with 10,000 randomized concurrent orders.

*   **End-to-End Microservice Throughput:** Consistently processes **10,000 concurrent orders in ~4.5 seconds**, sustaining **~2,100–2,200 Trades Per Second (TPS)** (~450 microseconds per full HTTP ingestion, Pydantic validation, RAM matching, and SQLite WAL queueing lifecycle).