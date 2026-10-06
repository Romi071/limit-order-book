# High-Frequency Limit Order Book (LOB) Matching Engine

A high-performance, institutional-grade Limit Order Book (LOB) matching engine built entirely in Python. Designed with a focus on algorithmic efficiency and minimal memory footprint, this engine handles price-time priority matching, advanced execution types (IOC, FOK), partial fills, ultra-fast order cancellations, and a decoupled on-disk ledger pattern.

## Key Features

*   **Atomic Advanced Order Types:** Native support for GTC (Good-'Til-Cancelled), IOC (Immediate-Or-Cancel), and FOK (Fill-Or-Kill). FOK orders guarantee strict all-or-nothing execution via a surgical state-rollback mechanism that prevents partial fills.
*   **Institutional Clearinghouse Handshake:** Flattens the matching execution into a continuous $\mathcal{O}(K)$ loop to seamlessly capture both the `takerId` and `makerID` for every match. This generates a continuous, professional trade tape ready for clearinghouse settlement.
*   **Decoupled Ledger Pattern:** The core engine operates 100% in RAM to maintain microsecond execution speeds. Executed trade logs and the asymmetrical L2 market depth are flushed to an on-disk JSON ledger only at the gateway level, avoiding I/O bottlenecks during live matching.
*   **$\mathcal{O}(1)$ Order Cancellations via Lazy Deletion:** Instead of physically scanning and removing orders from queues ($\mathcal{O}(N)$ bottleneck), the engine uses a hash map (`order_tracker`) to locate orders instantly and logically neutralizes them in-place. Ghost orders are automatically vaporized by the execution loop at zero cost.
*   **Dynamic Order Amendment (DRY):** Supports $\mathcal{O}(1)$ volume modification. Decreasing volume retains queue priority, while increasing volume dynamically triggers a `cancel-and-replace` operation to the back of the queue to maintain strict price-time fairness.
*   **Price-Time Priority (FIFO):** Utilizes Python's `collections.deque` to maintain strict First-In-First-Out execution for orders sitting at the same price level, ensuring absolute fairness in the queue.
*   **Logarithmic Price Discovery:** Implements Min-Heaps and Max-Heaps (`heapq`) to track the best bid and ask prices dynamically. This guarantees $\mathcal{O}(\log N)$ performance when updating the spread, even when the book is flooded with hundreds of different price levels.
*   **C-Level Memory Optimization:** Employs Python's `__slots__` directive on all `Order` and `OrderQueue` objects. This disables dynamic dictionary allocation per object, drastically reducing RAM usage and speeding up attribute access for high-frequency object creation.
*   **Strict Boundary Safeguards:** Built-in validation intercepts invalid data (e.g., negative prices, zero volumes, invalid order types) at object instantiation, throwing a `ValueError` or `TypeError` before bad data can taint the matching engine's state.

---

## Time Complexity Benchmarks

| Operation | Time Complexity | Implementation Mechanism |
| :--- | :--- | :--- |
| **Look up Best Bid/Ask** | $\mathcal{O}(1)$ | Reading the 0-index of the `heapq` arrays. |
| **Add New Price Level** | $\mathcal{O}(\log N)$ | Pushing a new price integer to the min/max heap. |
| **Add Order to Queue** | $\mathcal{O}(1)$ | `deque.append()` at the specified price level. |
| **Execute Trade (Match)** | $\mathcal{O}(K)$ | Single `while` loop over $K$ resting orders to capture Taker/Maker IDs. |
| **FOK Liquidity Dry-Run** | $\mathcal{O}(K \log N)$ | Peek-and-Restore state rollback (popping/restoring $K$ eligible price levels). |
| **Cancel / Amend Order** | $\mathcal{O}(1)$ | Hash map lookup + logical state modification (Lazy Deletion). |

## Architecture & Logic Flow

1. **The Bouncer (`Order` Object):** Every incoming request is strictly filtered. A unique 8-character UUID is generated for internal system tracking, alongside an optional `client_id` for external user mapping. If an order passes the checks, it is instantiated in memory.
2. **The Tracker (`order_tracker`):** Every valid order is logged into a global dictionary mapped as `{order_id: Order_Object}`. This grants the engine instant $\mathcal{O}(1)$ omnipresence over every order's location and status.
3. **The Matching Loop (`add_order`):** 
    *   **FOK Dry-Run:** If an order is Fill-Or-Kill, the engine temporarily lifts price levels off the heap to verify absolute liquidity before mutating any state. If it fails, the heap is restored and the order is killed instantly.
    *   **Taker Orders:** If a buy order crosses the best available ask (or vice versa), the engine aggressively sweeps the liquidity. It handles partial fills, records the Taker/Maker ID handshake, and completely empties queues, gracefully skipping over any "ghost" (cancelled) orders. IOC orders that fail to fully fill evaporate here.
    *   **Maker Orders:** If a GTC order cannot be instantly filled, it is routed to its respective `OrderQueue` based on price, and the price is pushed to the heap.
4. **Volume Mathematics:** Price levels dynamically track their aggregate volume. When a level's volume hits `0` (either through trades or cancellations), the price is popped from the heap, keeping the spread incredibly tight and accurate without relying on global volume trackers that are prone to state drift.

---

## Engineering Trade-off: FOK Atomicity vs. Data Structures

Guaranteeing atomicity for Fill-Or-Kill (FOK) orders presents a unique systems design challenge. The engine must mathematically prove that sufficient volume exists at valid prices *before* mutating a single variable. 

In hardware-accelerated environments, professional exchanges often utilize contiguous memory arrays or Red-Black Trees (e.g., C++ `std::map`) to sequentially walk down the price levels in purely $\mathcal{O}(K)$ time without altering the data structure.

Because this engine relies on Python's `heapq` for ultra-fast $\mathcal{O}(1)$ best-price lookups and $\mathcal{O}(\log N)$ insertions, looking at the *second* or *third* best price requires physically popping the best price off the heap. To solve this without triggering a catastrophic $\mathcal{O}(N)$ deep copy of the entire market depth, this engine utilizes a **Peek-and-Restore (State Rollback)** pattern. 

For FOK orders, the engine pops $K$ eligible price levels, tallies the valid liquidity, and immediately pushes the prices back onto the heap ($\mathcal{O}(K \log N)$). While this introduces a small multiplier constant to the time complexity, $K$ remains exceptionally small in live markets, making it a highly efficient, memory-cheap compromise for a locally run Python matching engine.
