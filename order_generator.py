import numpy as np
import json

#Amount of orders to generate and fake price of the active
n = 10000
cost = 100
orders = []

gen_sides = np.random.randint(0, 2, n)
gen_prices = np.random.uniform(cost - 10, cost + 10, n)
gen_amounts = np.random.uniform(0.1, 100, n)

for i in range(n):
    gen_side = gen_sides[i]
    if gen_side == 0:
        gen_side = 'buy'
    else:
        gen_side = 'sell'
    gen_price = gen_prices[i]
    gen_amount = gen_amounts[i]
    gen_order = {'side': gen_side, 'price': float(gen_price), 'amount': float(gen_amount)}
    orders.append(gen_order)

with open("orders.json", "w") as f:
    json.dump(orders, f)