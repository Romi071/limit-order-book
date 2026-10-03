from collections import deque
import heapq
import uuid

class Order:
    #Rigid Memory Allocation to optimize RAM usage and speed
    __slots__ = ['side', 'price', 'amount', 'id', 'client_id', 'active'] 

    #Initiate the Order object
    def __init__(self, side: str, price: float, amount: float, client_id = None):
            #Safeguards against bad input
            if isinstance(side, str):
                if side not in ['buy', 'sell']:
                    raise ValueError(f"Invalid side value: '{side}'. Must be 'buy' or 'sell'.")
            else:
                raise TypeError(f"Invalid type for side input. Must be a string with value 'buy' or 'sell'.")
            if isinstance(price, float) or isinstance(price, int):
                if price <= 0:
                    raise ValueError(f"Invalid price value: '{price}'. Must be a strictly positive number.")
            else:
                raise TypeError(f"Invalid type for price input. Must be a float or int with a strictly positive value.")
            if isinstance(amount, float) or isinstance(amount, int): 
                if amount <= 0:
                    raise ValueError(f"Invalid amount value: '{amount}'. Must be a strictly positive number.")
            else:
                raise TypeError(f"Invalid type for amount input. Must be a float or int with a strictly positive value.")
            #Variable assignment
            self.side = side
            self.price = price
            self.amount = amount
            self.id = uuid.uuid4().hex[:8]
            self.client_id = str(client_id) if client_id is not None else None
            self.active = True
    #For debugging, make Orders printable
    def __repr__(self):
        return f'Order: side = {self.side}, price = {self.price}, amount = {self.amount}, active = {self.active}'
    
    #Method to reduce the executed amount from the order and deactivate it if it was fully filled
    def reduce_amount(self, executed_amount):
        if self.amount > executed_amount:
            self.amount -= executed_amount
        else:
             self.amount = 0
             self.active = False

class OrderQueue:
    #Rigid Memory Allocation to optimize RAM usage and speed
    __slots__ = ['price', 'queue', 'volume'] 

    #Initiate the OrderQueue object
    def __init__(self, price):
        self.price = price
        self.queue = deque()
        self.volume = 0
    #For debugging, make Queue printable
    def __repr__(self):
        return f'OrderQueue: price = {self.price}, n_orders = {len(self.queue)}'

    #Methods to add and remove orders in O(1) on a FIFO queue
    def ingest_order(self, order):
        self.queue.append(order)
        self.volume += order.amount
    def evict_order(self):
        if len(self.queue) > 0:
            self.volume -= (self.queue[0]).amount
            self.queue[0].active = False
            self.queue.popleft()
        else:
            print("The operation couldn't be completed, there are no orders left to evict")
    def empty_queue(self):
        self.queue.clear()
        self.volume = 0


class OrderBook:
    #Initiate the OrderBook object
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.buys_heap = []
        self.sells_heap = []
        self.order_tracker = {}
    #For debugging, make it printable
    def __repr__(self):
        return f'OrderBook Object:\nCurrent bids = {self.bids}\nCurrent asks = {self.asks}'
    
    #Method to fill orders or keep them in the book (ordered using heapq O(log(N))) if current market does not allow for instant filling
    def add_order(self, order):
        trade_logs = []
        self.order_tracker[order.id] = order
        #Buy orders:
        if order.side == "buy":
            #Loop over the sells_heap best prices
            while order.active == True and len(self.sells_heap) > 0:
                best_sell_price = self.sells_heap[0]
                best_orderq = self.asks[best_sell_price]
                #If the best available sell price is under the buy order's offer
                if order.price >= best_sell_price:
                    #If the order's amount is greater than the total volume in the OrderQueue at this price
                    if order.amount >= best_orderq.volume:
                        order.reduce_amount(best_orderq.volume)
                        #If any amount was traded append to the logs
                        if best_orderq.volume > 0:
                            trade_logs.append({"takerId": order.id, "price": best_sell_price, "volume": best_orderq.volume})
                        #Fully fill the OrderQueue at this price
                        best_orderq.empty_queue()
                    #Volume in the OrderQueue at this price greater than the order's amount
                    else:
                        trade_logs.append({"takerId": order.id, "price": best_sell_price, "volume": order.amount})
                        #Loop over the OrderQueue orders until the order is filled
                        while order.active == True:
                            e = best_orderq.queue[0]
                            trade_amount = min(order.amount, e.amount)
                            order.reduce_amount(trade_amount)
                            if trade_amount == e.amount:
                                best_orderq.evict_order()
                            else:
                                e.reduce_amount(trade_amount)
                                best_orderq.volume -= trade_amount
                    #If the OrderQueue entry at this price is fully filled, pop price from the heapq
                    if best_orderq.volume == 0:
                        heapq.heappop(self.sells_heap)
                #Best available sell price is above the buy order's offer
                else:
                    break
            #If the buy order still remains to be filled, place it waiting in the book
            if order.active == True:
                if order.price not in self.bids:
                    self.bids[order.price] = OrderQueue(order.price)
                    self.bids[order.price].ingest_order(order)
                    #Store the price as negative to use the Min-Heap module as a Max-Heap for the buys heapq
                    heapq.heappush(self.buys_heap, -order.price)
                else:
                    if self.bids[order.price].volume == 0:
                        heapq.heappush(self.buys_heap, -order.price)
                    self.bids[order.price].ingest_order(order)

        #Sell orders:
        if order.side == "sell":
            #Loop over the buys_heap best prices
            while order.active == True and len(self.buys_heap) > 0:
                best_buy_price = -self.buys_heap[0]
                best_orderq = self.bids[best_buy_price]
                #If the best available buy price is above the sell order's offer
                if order.price <= best_buy_price:
                    #If the order's amount is greater than the total volume in the OrderQueue at this price
                    if order.amount >= best_orderq.volume:
                        order.reduce_amount(best_orderq.volume)
                        #If any amount was traded append to the logs
                        if best_orderq.volume > 0:
                            trade_logs.append({"takerId": order.id, "price": best_buy_price, "volume": best_orderq.volume})
                        #Fully fill the OrderQueue at this price
                        best_orderq.empty_queue()
                    #Volume in the OrderQueue at this price greater than the order's amount
                    else:
                        trade_logs.append({"takerId": order.id, "price": best_buy_price, "volume": order.amount})
                        #Loop over the OrderQueue orders until the order is filled
                        while order.active == True:
                            e = best_orderq.queue[0]
                            trade_amount = min(order.amount, e.amount)
                            order.reduce_amount(trade_amount)
                            if trade_amount == e.amount:
                                best_orderq.evict_order()
                            else:
                                e.reduce_amount(trade_amount)
                                best_orderq.volume -= trade_amount
                    #If the OrderQueue entry at this price is fully filled, pop price from the heapq
                    if best_orderq.volume == 0:
                        heapq.heappop(self.buys_heap)
                #Best available buy price is below the sell order's offer
                else:
                    break
                
            #If the sell order still remains to be filled, place it waiting in the book
            if order.active == True:
                if order.price not in self.asks:
                    self.asks[order.price] = OrderQueue(order.price)
                    self.asks[order.price].ingest_order(order)
                    heapq.heappush(self.sells_heap, order.price)
                else:
                    if self.asks[order.price].volume == 0:
                        heapq.heappush(self.sells_heap, order.price)
                    self.asks[order.price].ingest_order(order)

        return trade_logs

    #Method to cancel a specific order in O(1) given its Id
    def cancel_order(self, orderId):
        #Armor against bad input
        order = self.order_tracker[orderId]
        if order.active == False:
            print(f"The order with Id {orderId} is already filled and couldn't be cancelled.")
            return
        #Logical deletion of the order
        amount = order.amount
        order.amount = 0
        order.active = False
        if order.side == "buy":
            self.bids[order.price].volume -= amount
        elif order.side == "sell":
            self.asks[order.price].volume -= amount
        print(f"The order with Id {orderId} was succesfully cancelled.")

    #Method to change amount of a specific order in O(1) featuring loss in priority for increments in volume
    def amend_order(self, orderId, new_amount):
        #Armor against bad input
        if isinstance(new_amount, int) == False and isinstance(new_amount, float) == False:
            raise TypeError(f"Invalid amount type: '{new_amount}'. Must be a strictly positive int or float.")
        if new_amount <= 0:
            raise ValueError(f"Invalid amount value: '{new_amount}'. Must be a strictly positive number.")
        order = self.order_tracker[orderId]
        if order.active == False:
            print(f"The order with Id {orderId} is already filled and couldn't be amended.")
            return
        #Logical deletion of the order and placement of a new order at the back of the deque
        if new_amount > order.amount:
            self.cancel_order(order.id)
            new_order = Order(order.side, order.price, new_amount, order.client_id)
            self.add_order(new_order)
            print(f"The order with Id {orderId} was succesfully amended. New amount: {new_amount}. Priority was lost at this price.")
        #Modification of the order volume without affecting deque priority
        else:
            amount = order.amount
            order.amount = new_amount
            if order.side == "buy":
                self.bids[order.price].volume -= amount
                self.bids[order.price].volume += new_amount
            elif order.side == "sell":
                self.asks[order.price].volume -= amount
                self.asks[order.price].volume += new_amount
            print(f"The order with Id {orderId} was succesfully amended. New amount: {new_amount}.")

    #Method to export market depth as a dictionary following the industry's conventions, accepting a depth input.
    def export_market(self, depth = None):
        #Armor against bad input
        if isinstance(depth, int) == False and depth != None:
            raise TypeError(f"Invalid depth type: '{depth}'. Must be a strictly positive integer.")
        if isinstance(depth, int) and depth <= 0:
            raise ValueError(f"Invalid depth value: '{depth}'. Must be a strictly positive integer.")
        market = {"bids": [], "asks": []}
        bids_ss = self.buys_heap[:]
        asks_ss = self.sells_heap[:]
        #If no depth was specified, output the whole market depth in O((N + M)log(N)) time
        if depth == None:
            n = len(bids_ss)
            m = len(asks_ss)
            for _ in range(n):
                best_bid = -bids_ss[0]
                market["bids"].append([best_bid, self.bids[best_bid].volume])
                heapq.heappop(bids_ss)
            for _ in range(m):
                best_ask = asks_ss[0]
                market["asks"].append([best_ask, self.asks[best_ask].volume])
                heapq.heappop(asks_ss)
        #If depth was specified, output the market up to the specified depth in O((M + K)*log(N)) time
        else:
            for _ in range(min(depth, len(bids_ss))):
                best_bid = -bids_ss[0]
                market["bids"].append([best_bid, self.bids[best_bid].volume])
                heapq.heappop(bids_ss)
            for _ in range(min(depth, len(asks_ss))):
                best_ask = asks_ss[0]
                market["asks"].append([best_ask, self.asks[best_ask].volume])
                heapq.heappop(asks_ss)
        return market