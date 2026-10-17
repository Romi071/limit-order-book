# Algorithmic Limit Order Book (LOB) Matching Engine

An algorithmic Limit Order Book (LOB) matching engine and asynchronous exchange server built entirely in Python. Designed as a proof-of-concept mimicking institutional architecture, this engine focuses on computational efficiency, non-blocking network I/O, and minimal memory footprint. It handles price-time priority matching, advanced execution types (IOC, FOK), partial fills, token-authenticated `O(1)` order cancellations and amendments, real-time WebSocket depth broadcasting, and a batched asynchronous SQLite WAL ledger.

## Key Features

*   **Atomic Advanced Order Types:** Native support for GTC (Good-'Til-Cancelled), IOC (Immediate-Or-Cancel), and FOK (Fill-Or-Kill). FOK orders guarantee strict all-or-nothing execution via a surgical state-rollback mechanism that prevents partial fills.
*   **Maker/Taker ID Handshake & Token Security:** Flattens the matching execution into a continuous `O(K)` loop to seamlessly capture both the public `takerId` and `makerId` for every match, generating a traceable trade tape. To prevent malicious actors from using public trade tape IDs to snipe resting liquidity, every order is issued a server-generated cryptographic `secret_token` required for `O(1)` cancellations and amendments, alongside an optional `client_tag` for user-side strategy metadata.
*   **Hybrid RAM/Disk Ledger Pattern:** The core matching engine operates 100% synchronously in RAM to maintain nanosecond/microsecond execution speeds. Network I/O and disk persistence are strictly decoupled into the asynchronous routing layer—streaming live L2 market depth over WebSockets and batch-committing executed trade receipts via a Producer-Consumer buffer into an ACID-compliant SQLite (WAL) database without blocking the matching loop.
*   **`O(1)` Order Cancellations via Lazy Deletion:** Instead of physically scanning and removing orders from queues (`O(N)` bottleneck), the engine uses a hash map (`order_tracker`) exclusively tracking resting GTC orders to locate targets instantly and logically neutralize them in-place. Transient IOC/FOK orders bypass tracker registration to prevent memory leaks, and cancelled orders are automatically evicted by the execution loop at zero cost.
*   **Dynamic Order Amendment (DRY):** Supports `O(1)` volume modification. Decreasing volume retains queue priority in-place, while increasing volume dynamically triggers a `cancel-and-replace` operation to the back of the queue while preserving the order's `id` and `secret_token` to maintain strict price-time fairness.
*   **Price-Time Priority (FIFO):** Utilizes Python's `collections.deque` to maintain strict First-In-First-Out execution for orders sitting at the same price level, ensuring absolute fairness in the queue.
*   **Logarithmic Price Discovery & Deduplication:** Implements Min-Heaps and Max-Heaps (`heapq`) to track the best bid and ask prices dynamically in `O(log N)` time. Each `OrderQueue` maintains an `O(1)` `heapq_exists` boolean state guard to prevent duplicate price pushes when new liquidity arrives at a previously cancelled price level still awaiting lazy eviction.
*   **IEEE 754 Floating-Point Drift Armor:** Queue depletion inside the matching loop is governed strictly by integer queue length (`len(queue) == 0`) rather than floating-point volume comparisons. Combined with a `min_lot_size` (`1e-8`) "Heal-on-Read" dust sweeper during L2 depth exports, the engine is completely immune to IEEE 754 residual float drift.
*   **Object Memory Optimization:** Employs Python's `__slots__` directive on all `Order` and `OrderQueue` objects. This disables dynamic dictionary allocation per object, drastically reducing RAM usage and speeding up attribute access for high-frequency object creation.
*   **Strict Boundary Safeguards:** Built-in validation intercepts invalid data (e.g., negative prices, sub-minimum lot volumes, invalid order types) at both the network gateway (via Pydantic) and object instantiation, throwing a `ValueError` or `TypeError` before bad data can taint the matching engine's state.

---

## Time Complexity Benchmarks

| Operation | Time Complexity | Implementation Mechanism |
| :--- | :--- | :--- |
| **Look up Best Bid/Ask** | `O(1)` | Reading the 0-index of the `heapq` arrays. |
| **Add New Price Level** | `O(log N)` | Pushing a new price float/int to the min/max heap (guarded by `heapq_exists`). |
| **Add Order to Queue** | `O(1)` | `deque.append()` at the specified price level. |
| **Execute Trade (Match)** | `O(K)` | Single `while` loop over `K` resting orders to capture Taker/Maker IDs. |
| **FOK Liquidity Dry-Run** | `O(K log N)` | Peek-and-Restore state rollback (popping/restoring `K` eligible price levels). |
| **Cancel / Amend Order** | `O(1)` | Hash map lookup + `secret_token` verification + logical state modification. |

---

## Architecture & Logic Flow

1. **The Bouncer (`Order` Object):** Every incoming request is strictly filtered against minimum lot size (`1e-8`) and type constraints. The server generates two distinct 8-character UUID hex strings: a public `id` (exposed on the trade tape) and a private `secret_token` (returned only to the order creator as an authentication PIN for lifecycle modifications), alongside an optional user-defined `client_tag`.
2. **The Tracker (`order_tracker`):** Valid `GTC` orders are logged into a global dictionary mapped as `{order_id: Order_Object}`. This grants the engine instant `O(1)` lookup and authentication over every resting order while allowing transient `IOC` and `FOK` orders to be garbage-collected immediately upon completion.
3. **The Matching Loop (`add_order`):** 
    *   **FOK Dry-Run:** If an order is Fill-Or-Kill, the engine temporarily lifts price levels off the heap to verify absolute liquidity before mutating any state. If it fails, the heap is restored and the order is killed instantly.
    *   **Taker Orders:** If a buy order crosses the best available ask (or vice versa), the engine aggressively sweeps the liquidity. It handles partial fills, records the Taker/Maker ID handshake, and empties queues based on integer queue length (`len(queue)`), gracefully skipping over any zero-volume cancelled orders. IOC orders that fail to fully fill evaporate here.
    *   **Maker Orders:** If a GTC order cannot be instantly filled, it is routed to its respective `OrderQueue` based on price, and the price is pushed to the heap if `heapq_exists` is `False`.
4. **Volume Mathematics & Dust Sweeping:** Price levels dynamically track their aggregate volume. When a queue's integer length hits `0` during matching, the price is popped from the heap (`heapq_exists = False`) and any residual floating-point dust is zeroed out. When exporting L2 market depth (`export_market`), the engine skips lazy-deleted levels below `min_lot_size` (`1e-8`) and heals residual float drift on read.

---

## Engineering Trade-off: FOK Atomicity vs. Data Structures

Guaranteeing atomicity for Fill-Or-Kill (FOK) orders presents a unique systems design challenge. The engine must mathematically prove that sufficient volume exists at valid prices *before* mutating a single variable. 

In hardware-accelerated environments, professional exchanges often utilize contiguous memory arrays or Red-Black Trees (e.g., C++ `std::map`) to sequentially walk down the price levels in purely `O(K)` time without altering the data structure.

Because this engine relies on Python's `heapq` for ultra-fast `O(1)` best-price lookups and `O(log N)` insertions, looking at the *second* or *third* best price requires physically popping the best price off the heap. To solve this without triggering a catastrophic `O(N)` deep copy of the entire market depth, this engine utilizes a **Peek-and-Restore (State Rollback)** pattern. 

For FOK orders, the engine pops `K` eligible price levels, tallies the valid liquidity, and immediately pushes the prices back onto the heap in `O(K log N)`. While this introduces a small multiplier constant to the time complexity, `K` remains exceptionally small in live markets, making it a highly efficient, memory-cheap compromise for a locally run Python matching engine.

---

## Network Infrastructure & Persistence (`server.py`)

The core algorithmic matching logic is wrapped inside an asynchronous, non-blocking microservice architecture designed to handle concurrent order flow without race conditions or I/O bottlenecks:

*   **ASGI Server & Concurrency Control:** Powered by **FastAPI** and Uvicorn. To protect the in-memory `heapq` and `deque` structures from asynchronous race conditions during high-frequency state mutations, order ingestion, cancellation, and amendment are guarded by a strict `asyncio.Lock()` mutex that releases immediately after RAM execution.
*   **Strict Gateway Validation & Semantic HTTP Errors:** Utilizes **Pydantic** `BaseModel` schemas (`IncomingOrder`, `CancelOrder`, `AmendOrder`) backed by a Rust core to validate and type-check incoming JSON payloads at the network boundary. Lifecycle endpoints (`/cancel`, `/amend`) enforce strict HTTP status semantics: `200 OK` on state mutation, `400 Bad Request` if targeting an already-filled order, `401 Unauthorized` on a `PermissionError` (invalid `secret_token`), and `404 Not Found` on a `KeyError` (non-existent or transient `orderId`).
*   **Concurrent WebSocket Broadcasting (`ConnectionManager`):** Encapsulates active client connections into a dedicated OOP manager. Whenever an order addition, cancellation, or amendment mutates the book, the L2 market snapshot is computed outside the engine lock and broadcasted concurrently to all connected listeners via `asyncio.gather`, preventing slow clients from lagging the main event loop.
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
