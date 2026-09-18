import numpy as np
import uuid

class Order:
    def __init__(self, side: str, price: float, amount: float):
            self.side = side
            self.price = price
            self.amount = amount
            self.id = uuid.uuid4().hex[:8]
            self.active = True

    def __repr__(self):
        return f'Order: side = {self.side}, price = {self.price}, amount = {self.amount}, active = {self.active}'
        
    def reduce_amount(self, executed_amount):
        if self.amount > executed_amount:
            self.amount -= executed_amount
        else:
             self.amount = 0
             self.active = False