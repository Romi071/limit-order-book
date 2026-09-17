import numpy as np

class Order:
    def __init__(self, side: str, price: float, amount: float):
            self.side = side
            self.price = price
            self.amount = amount
            self.id = np.random.random_integers(0, 1000000)