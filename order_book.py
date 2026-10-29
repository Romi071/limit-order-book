from collections import deque
import heapq
import uuid

class Order:
    #Rigid Memory Allocation to optimize RAM usage and speed
    __slots__ = ['side', 'price', 'amount', 'order_type', 'id', 'secret_token', 'client_tag', 'active'] 

    #Initiate the Order object
    def __init__(self, side: str, price: float, amount: float, order_type: str = 'GTC', client_tag: str | None = None):
            #Safeguards against bad input
            if isinstance(side, str):
                if side not in ['buy', 'sell']:
                    raise ValueError(f"Invalid side value: '{side}'. Must be 'buy' or 'sell'.")
            else:
                raise TypeError(f"Invalid type for order side input. Must be a string with value 'buy' or 'sell'.")
            if isinstance(order_type, str):
                if order_type not in ['GTC', 'IOC', 'FOK']:
                    raise ValueError(f"Invalid order type value: '{order_type}'. Must be 'GTC' (default), 'IOC' or 'FOK'.")
            else:
                raise TypeError(f"Invalid type for order type input. Must be a string with value 'GTC' (default), 'IOC' or 'FOK'.")
            if isinstance(price, float) or isinstance(price, int):
                if price <= 0:
                    raise ValueError(f"Invalid price value: '{price}'. Must be a strictly positive number.")
            else:
                raise TypeError(f"Invalid type for price input. Must be a float or int with a strictly positive value.")
            if isinstance(amount, float) or isinstance(amount, int): 
                if amount < 1e-8:
                    raise ValueError(f"Invalid amount value: '{amount}'. Must be a positive number >= 1e-8.")
            else:
                raise TypeError(f"Invalid type for amount input. Must be a float or int with a strictly positive value.")
            #Variable assignment
            self.side = side
            self.price = price
            self.amount = amount
            self.order_type = order_type
            self.id = uuid.uuid4().hex[:8]
            self.secret_token = uuid.uuid4().hex[:8]
            self.client_tag = str(client_tag) if client_tag is not None else None
            self.active = True
    #For debugging, make Orders printable
    def __repr__(self):
        return f'Order: side = {self.side}, price = {self.price}, amount = {self.amount}, id = {self.id}, active = {self.active}'
    
    #Method to reduce the executed amount from the order and deactivate it if it was fully filled
    def reduce_amount(self, executed_amount):
        if self.amount - executed_amount >= 1e-8:
            self.amount -= executed_amount
        else:
             self.amount = 0
             self.active = False

class OrderQueue:
    #Rigid Memory Allocation to optimize RAM usage and speed
    __slots__ = ['price', 'queue', 'volume', 'heapq_exists'] 

    #Initiate the OrderQueue object
    def __init__(self, price):
        self.price = price
        self.queue = deque()
        self.volume = 0
        self.heapq_exists = True
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
        self.min_lot_size = 1e-8
    #For debugging, make it printable
    def __repr__(self):
        return f'OrderBook Object:\nCurrent bids = {self.bids}\nCurrent asks = {self.asks}'
    
    #Method to fill orders or keep them in the book (ordered using heapq O(log(N))) if current market does not allow for instant filling
    def add_order(self, order):
        trade_logs = []
        #Only track orders that stay in the book
        if order.order_type == 'GTC':
            self.order_tracker[order.id] = order
        #Buy orders:
        if order.side == "buy":
            #For FOK-type orders:
            if order.order_type == 'FOK':
                #Peek-and-restore approach on the heapq to determine whether the order can be filled instantly
                total_valid_liquidity = 0
                checked_prices = []
                while order.amount > total_valid_liquidity and len(self.sells_heap) > 0:
                    best_price = self.sells_heap[0]
                    if order.price >= best_price:
                        total_valid_liquidity += self.asks[best_price].volume
                        checked_prices.append(best_price)
                        heapq.heappop(self.sells_heap)
                    #Valid liquidity was not enough, break
                    else:
                        break
                #Restore Heapq
                for price in checked_prices:
                    heapq.heappush(self.sells_heap, price)
                #If valid liquidity was not enough, return, else let the order enter the market normally
                if order.amount > total_valid_liquidity:
                    return trade_logs
            #Loop over the sells_heap best prices
            while order.active == True and len(self.sells_heap) > 0:
                best_sell_price = self.sells_heap[0]
                best_orderq = self.asks[best_sell_price]
                #If the best available sell price is under the buy order's offer
                if order.price >= best_sell_price:
                    #Loop over the OrderQueue orders until the order is filled or the queue is emptied at this price
                    while order.active == True and len(best_orderq.queue) > 0:
                        maker_order = best_orderq.queue[0]
                        trade_amount = min(order.amount, maker_order.amount)
                        order.reduce_amount(trade_amount)
                        if maker_order.amount - trade_amount < self.min_lot_size:
                            best_orderq.evict_order()
                            del self.order_tracker[maker_order.id]
                        else:
                            maker_order.reduce_amount(trade_amount)
                            best_orderq.volume -= trade_amount
                        if trade_amount > 0:
                            trade_logs.append({"takerId": order.id, "makerId": maker_order.id, "price": best_sell_price, "volume": trade_amount})
                    #If the OrderQueue entry at this price is fully filled, pop price from the heapq
                    if len(best_orderq.queue) == 0:
                        heapq.heappop(self.sells_heap)
                        best_orderq.heapq_exists = False
                        #Floating-point dust sweeper
                        best_orderq.volume = 0
                #Best available sell price is above the buy order's offer
                else:
                    break
            #If the buy order still remains to be filled and its type is GTC, place it waiting in the book
            if order.active == True and order.order_type == 'GTC':
                if order.price not in self.bids:
                    self.bids[order.price] = OrderQueue(order.price)
                    self.bids[order.price].ingest_order(order)
                    #Store the price as negative to use the Min-Heap module as a Max-Heap for the buys heapq
                    heapq.heappush(self.buys_heap, -order.price)
                else:
                    if self.bids[order.price].heapq_exists == False:
                        heapq.heappush(self.buys_heap, -order.price)
                        self.bids[order.price].heapq_exists = True
                    self.bids[order.price].ingest_order(order)

        #Sell orders:
        if order.side == "sell":
            #For FOK-type orders:
            if order.order_type == 'FOK':
                #Peek-and-restore approach using the heapq to determine whether the order can be filled instantly
                total_valid_liquidity = 0
                checked_prices = []
                while order.amount > total_valid_liquidity and len(self.buys_heap) > 0:
                    best_price = -self.buys_heap[0]
                    if order.price <= best_price:
                        total_valid_liquidity += self.bids[best_price].volume
                        checked_prices.append(best_price)
                        heapq.heappop(self.buys_heap)
                    #Valid liquidity was not enough, break
                    else:
                        break
                #Restore Heapq
                for price in checked_prices:
                    heapq.heappush(self.buys_heap, -price)
                #If valid liquidity was not enough, return, else let the order enter the market normally
                if order.amount > total_valid_liquidity:
                    return trade_logs
            #Loop over the buys_heap best prices
            while order.active == True and len(self.buys_heap) > 0:
                best_buy_price = -self.buys_heap[0]
                best_orderq = self.bids[best_buy_price]
                #If the best available buy price is above the sell order's offer
                if order.price <= best_buy_price:
                    #Loop over the OrderQueue orders until the order is filled or the queue is emptied at this price
                    while order.active == True and len(best_orderq.queue) > 0:
                        maker_order = best_orderq.queue[0]
                        trade_amount = min(order.amount, maker_order.amount)
                        order.reduce_amount(trade_amount)
                        if maker_order.amount - trade_amount < self.min_lot_size:
                            best_orderq.evict_order()
                            del self.order_tracker[maker_order.id]
                        else:
                            maker_order.reduce_amount(trade_amount)
                            best_orderq.volume -= trade_amount
                        if trade_amount > 0:
                            trade_logs.append({"takerId": order.id, "makerId": maker_order.id, "price": best_buy_price, "volume": trade_amount})
                    #If the OrderQueue entry at this price is fully filled, pop price from the heapq
                    if len(best_orderq.queue) == 0:
                        heapq.heappop(self.buys_heap)
                        best_orderq.heapq_exists = False
                        #Floating-point dust sweeper
                        best_orderq.volume = 0
                #Best available buy price is below the sell order's offer
                else:
                    break
            #If the sell order still remains to be filled and its type is GTC, place it waiting in the book
            if order.active == True and order.order_type == 'GTC':
                if order.price not in self.asks:
                    self.asks[order.price] = OrderQueue(order.price)
                    self.asks[order.price].ingest_order(order)
                    heapq.heappush(self.sells_heap, order.price)
                else:
                    if self.asks[order.price].heapq_exists == False:
                        heapq.heappush(self.sells_heap, order.price)
                        self.asks[order.price].heapq_exists = True
                    self.asks[order.price].ingest_order(order)

        return trade_logs

    #Method to cancel a specific order in O(1) given its Id
    def cancel_order(self, orderId, secret_token):
        #Armor against bad input
        if orderId not in self.order_tracker:
            #print(f"The order with Id {orderId} is already filled (or it doesn't exist) and couldn't be cancelled.")
            return {'success': False, 'cancelled_amount': 0, 'detail': "The order is already filled (or it doesn't exist) and couldn't be cancelled."}
        order = self.order_tracker[orderId]
        if secret_token != order.secret_token:
            raise PermissionError("Unauthorized procedure. Incorrect secret token.")
        
        #Logical (lazy) deletion of the order
        amount = order.amount
        order.amount = 0
        order.active = False
        del self.order_tracker[orderId]
        if order.side == "buy":
            self.bids[order.price].volume -= amount
            if self.bids[order.price].volume < self.min_lot_size:
                self.bids[order.price].empty_queue()
        elif order.side == "sell":
            self.asks[order.price].volume -= amount
            if self.asks[order.price].volume < self.min_lot_size:
                self.asks[order.price].empty_queue()
        #print(f"The order with Id {orderId} was succesfully cancelled.")
        return {'success': True, 'cancelled_amount': amount, 'detail': "The order was succesfully cancelled."}

    #Method to change amount of a specific order in O(1) featuring loss in priority for increments in volume
    def amend_order(self, orderId, secret_token, new_amount):
        #Armor against bad input
        if orderId not in self.order_tracker:
            #print(f"The order with Id {orderId} is already filled (or it doesn't exist) and couldn't be amended.")
            return {'success': False, 'detail': "The order is already filled (or it doesn't exist) and couldn't be amended."}
        if isinstance(new_amount, int) == False and isinstance(new_amount, float) == False:
            raise TypeError(f"Invalid amount type: '{new_amount}'. Must be int or float.")
        if new_amount < self.min_lot_size:
            raise ValueError(f"Invalid amount value: '{new_amount}'. Must be a positive number >= {self.min_lot_size}.")
        order = self.order_tracker[orderId]
        if secret_token != order.secret_token:
            raise PermissionError("Unauthorized procedure. Incorrect secret token.")
        
        #If new amount increased volume: logical deletion of the order and placement of a new order at the back of the deque
        amount = order.amount
        if new_amount > amount:
            prio_lost = True
            self.cancel_order(orderId, secret_token)
            new_order = Order(order.side, order.price, new_amount, 'GTC', order.client_tag)
            new_order.id = orderId
            new_order.secret_token = secret_token
            order.id = None
            self.add_order(new_order)
            #print(f"The order with Id {orderId} was succesfully amended. New amount: {new_amount}. Priority was lost at this price.")
        #Else: modification of the order volume without affecting deque priority
        else:
            prio_lost = False
            order.amount = new_amount
            if order.side == "buy":
                self.bids[order.price].volume -= amount
                self.bids[order.price].volume += new_amount
            elif order.side == "sell":
                self.asks[order.price].volume -= amount
                self.asks[order.price].volume += new_amount
            #print(f"The order with Id {orderId} was succesfully amended. New amount: {new_amount}.")
        return {'success': True, 'old_amount': amount, 'new_amount': new_amount, 'priority_lost': prio_lost, 'detail': "The order was succesfully amended."}

    #Method to export market depth as a dictionary following the industry's conventions, accepting a depth input.
    def export_market(self, depth: int | None = None):
        #Armor against bad input
        if isinstance(depth, int) == False and depth != None:
            raise TypeError(f"Invalid depth type: '{depth}'. Must be a strictly positive integer.")
        if isinstance(depth, int) and depth <= 0:
            raise ValueError(f"Invalid depth value: '{depth}'. Must be a strictly positive integer.")
        market = {"bids": [], "asks": []}
        #Create copies of the OrderBooks´s heaps to ensure state persistence when checking
        bids_ss = self.buys_heap[:]
        asks_ss = self.sells_heap[:]
        #If no depth was specified, output the whole market depth in O((N + M)log(N)) time
        if depth == None:
            while len(bids_ss) > 0:
                best_bid = -bids_ss[0]
                if self.bids[best_bid].volume >= self.min_lot_size:
                    market["bids"].append([best_bid, self.bids[best_bid].volume])
                #Floating point dust sweeper
                else:
                    self.bids[best_bid].volume = 0
                heapq.heappop(bids_ss)
            while len(asks_ss) > 0:
                best_ask = asks_ss[0]
                if self.asks[best_ask].volume >= self.min_lot_size:
                    market["asks"].append([best_ask, self.asks[best_ask].volume])
                #Floating point dust sweeper
                else:
                    self.asks[best_ask].volume = 0
                heapq.heappop(asks_ss)
        #If depth was specified, output the market up to the specified depth in O((M + K)*log(N)) time
        else:
            while len(market['bids']) < depth and len(bids_ss) > 0:
                best_bid = -bids_ss[0]
                if self.bids[best_bid].volume >= self.min_lot_size:
                    market["bids"].append([best_bid, self.bids[best_bid].volume])
                #Floating point dust sweeper
                else:
                    self.bids[best_bid].volume = 0
                heapq.heappop(bids_ss)
            while len(market['asks']) < depth and len(asks_ss) > 0:
                best_ask = asks_ss[0]
                if self.asks[best_ask].volume >= self.min_lot_size:
                    market["asks"].append([best_ask, self.asks[best_ask].volume])
                #Floating point dust sweeper
                else:
                    self.asks[best_ask].volume = 0
                heapq.heappop(asks_ss)
        return market