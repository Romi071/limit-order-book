import numpy as np
import aiohttp
import asyncio
import time

#Amount of orders to generate and fake price of the active
n = 10000
cost = 100
orders = []

#Generate the orders randomly around the cost and append the dictionaries into the 'orders' list
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

#Define an async function to prepare the orders
async def send_order(session, url, order):
    async with session.post(url, json=order) as response:
        return await response.text()

#Declare the event loop to bombard the server with the generated orders
async def main():
    async with aiohttp.ClientSession() as session:
        #Prepare the orders using the previously defined function in a list comprehension
        tasks = [send_order(session, "http://localhost:8000/order", order) for order in orders]
        #Fire them and time the engine's response
        start_time = time.perf_counter()
        await asyncio.gather(*tasks)
        end_time = time.perf_counter()

        print(f"End-to-end microservice time elapsed: {end_time - start_time:.8f} seconds. \nTrades Per Second (TPS): {n / (end_time - start_time)}")

asyncio.run(main())