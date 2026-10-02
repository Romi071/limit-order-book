# High-Frequency Limit Order Book (LOB) Matching Engine

A high-performance, institutional-grade Limit Order Book (LOB) matching engine built entirely in Python. Designed with a focus on algorithmic efficiency and minimal memory footprint, this engine handles price-time priority matching, partial fills, and ultra-fast order cancellations. 

## Key Features

*   **$\mathcal{O}(1)$ Order Cancellations via Lazy Deletion:** Instead of physically scanning and removing orders from queues ($\mathcal{O}(N)$ bottleneck), the engine uses a hash map (`order_tracker`) to locate orders instantly and logically neutralizes them in-place. Ghost orders are automatically vaporized by the execution loop at zero cost.
*   **Dynamic Order Amendment (DRY):** Supports $\mathcal{O}(1)$ volume modification. Decreasing volume retains queue priority, while increasing volume dynamically triggers a `cancel-and-replace` operation to the back of the queue to maintain strict price-time fairness.
*   **Institutional Dual-ID Architecture:** Decouples internal system memory from the client API contract. The engine generates strict internal UUIDs for safe memory pointers, while seamlessly attaching an optional `client_id` for external user tracking that persists even across priority-losing volume amendments.
*   **Price-Time Priority (FIFO):** Utilizes Python's `collections.deque` to maintain strict First-In-First-Out execution for orders sitting at the same price level, ensuring absolute fairness in the queue.
*   **Logarithmic Price Discovery:** Implements Min-Heaps and Max-Heaps (`heapq`) to track the best bid and ask prices dynamically. This guarantees $\mathcal{O}(\log N)$ performance when updating the spread, even when the book is flooded with hundreds of different price levels.
*   **C-Level Memory Optimization:** Employs Python's `__slots__` directive on all `Order` and `OrderQueue` objects. This disables dynamic dictionary allocation per object, drastically reducing RAM usage and speeding up attribute access for high-frequency object creation.
*   **Strict Boundary Safeguards:** Built-in validation intercepts invalid data (e.g., negative prices, zero volumes, or corrupted sides) at object instantiation, throwing a `ValueError` before bad data can taint the matching engine's state.

---

## Time Complexity Benchmarks

| Operation | Time Complexity | Implementation Mechanism |
| :--- | :--- | :--- |
| **Look up Best Bid/Ask** | $\mathcal{O}(1)$ | Reading the 0-index of the `heapq` arrays. |
| **Add New Price Level** | $\mathcal{O}(\log N)$ | Pushing a new price integer to the min/max heap. |
| **Add Order to Queue** | $\mathcal{O}(1)$ | `deque.append()` at the specified price level. |
| **Cancel Order** | $\mathcal{O}(1)$ | Hash map lookup + logical state modification (Lazy Deletion). |
| **Amend Order** | $\mathcal{O}(1)$ | Hash map lookup + volume mutation / lazy deletion routing. |
| **Execute Trade** | $\mathcal{O}(1)$ | `deque.popleft()` operation for instant eviction. |

## Architecture & Logic Flow

1. **The Bouncer (`Order` Object):** Every incoming request is strictly filtered. A unique 8-character UUID is generated for internal system tracking, and an optional `client_id` is attached for external user tracking. If an order passes the checks, it is instantiated in memory.
2. **The Tracker (`order_tracker`):** Every valid order is logged into a global dictionary mapped as `{order_id: Order_Object}`. This grants the engine instant $\mathcal{O}(1)$ omnipresence over every order's location and status.
3. **The Matching Loop (`add_order`):** 
    *   **Taker Orders:** If a new buy order crosses the best available ask (or vice versa), the engine sweeps the liquidity. It handles partial fills and completely empties queues, gracefully skipping over any "ghost" (cancelled) orders.
    *   **Maker Orders:** If the order cannot be instantly filled, it is routed to its respective `OrderQueue` based on price, and the price is pushed to the heap.
4. **Volume Mathematics:** Price levels dynamically track their aggregate volume. When a level's volume hits `0` (either through trades or cancellations), the price is popped from the heap, keeping the spread incredibly tight and accurate.
