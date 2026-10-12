from order_book import Order
from order_book import OrderBook
import json

#orders.json is a list of dictionaries containing order info
with open("orders.json", 'r') as f:
    orders = json.load(f)

#Initialize the matching engine and process the orders one by one
order_book = OrderBook()
order_logs = []
for order in orders:
    try:
        verified_order = Order(order['side'], order['price'], order['amount'], order.get('client_id'))
        #If the Order object was succesfully initialized add it to the book
        order_log = order_book.add_order(verified_order)
        if len(order_log) > 0:
            order_logs.append(order_log)

    #Bad order format handling armor
    except TypeError as error:
        print(f"\033[93m ⚠️ Order initialization failed due to the following TypeError: {error} \033[0m")
    except ValueError as error:
        print(f"\033[93m ⚠️ Order initialization failed due to the following ValueError: {error} \033[0m")

#Save to the disk the executed logs and the current depth of the market
market_depth = order_book.export_market()
with open('order_logs.json', 'w') as f:
    json.dump(order_logs, f)
with open('market_depth.json', 'w') as f:
    json.dump(market_depth, f)