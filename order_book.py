from collections import deque
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
            self.queue.popleft()
        else:
            print("The operation couldn't be completed, there are no orders left to evict")

class OrderBook:
    #Initiate the OrderBook object
    def __init__(self):
        self.bids = {}
        self.asks = {}
    #For debugging, make it printable
    def __repr__(self):
        return f'OrderBook Object:\nCurrent bids = {self.bids}\nCurrent asks = {self.asks}'

    def add_order(self, order):
        if order.side == "buy":
            if order.price not in self.bids:
                self.bids[order.price] = OrderQueue(order.price)
                self.bids[order.price].ingest_order(order)
            else:
                self.bids[order.price].ingest_order(order)
        elif order.side == "sell":
            if order.price not in self.asks:
                self.asks[order.price] = OrderQueue(order.price)
                self.asks[order.price].ingest_order(order)
            else:
                self.asks[order.price].ingest_order(order)