from collections import deque
import heapq
import uuid

class Order:
    #Initiate the Order object
    def __init__(self, side: str, price: float, amount: float):
            self.side = side
            self.price = price
            self.amount = amount
            self.id = uuid.uuid4().hex[:8]
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
    #For debugging, make it printable
    def __repr__(self):
        return f'OrderBook Object:\nCurrent bids = {self.bids}\nCurrent asks = {self.asks}'
    
    #Method to fill orders or keep them in the book (ordered using heapq O(log(N))) if current market does not allow for instant filling
    def add_order(self, order):
        trades_executed = []
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
                        #Fully fill the OrderQueue at this price
                        trades_executed.append({"price": best_sell_price, "volume": best_orderq.volume})
                        best_orderq.empty_queue()
                    #Volume in the OrderQueue at this price greater than the order's amount
                    else:
                        trades_executed.append({"price": best_sell_price, "volume": order.amount})
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


        ## UNFINISHED PART:
        #Sell Orders:
        elif order.side == "sell":
            #If possible, fill the sell order instantly
            if len(self.buys_heap) > 0 and order.price <= -self.buys_heap[0]: 
                best_buy_price = -self.buys_heap[0]
                self.bids[best_buy_price].evict_order()
                #If the OrderQueue entry is fully filled, pop from the heapq
                if self.bids[best_buy_price].volume == 0:
                    heapq.heappop(self.buys_heap)
            #Place the sell order waiting in the book
            else:
                if order.price not in self.asks:
                    self.asks[order.price] = OrderQueue(order.price)
                    self.asks[order.price].ingest_order(order)
                    heapq.heappush(self.sells_heap, order.price)
                else:
                    self.asks[order.price].ingest_order(order)

        return trades_executed