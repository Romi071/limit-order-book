from order_book import Order
from order_book import OrderBook
import json

#orders.json is a list of dictionaries containing order info
with open("orders.json", 'r') as f:
    orders = json.load(f)

order_book = OrderBook()
for order in orders:
    #Bad order format handling armor
    try:
        verified_order = Order(order['side'], order['price'], order['amount'], order.get('client_id'))
        #If the Order object was succesfully initialized add it to the book
        order_book.add_order(verified_order)

    except ValueError as error:
        print(f"\033[93m ⚠️ Order initialization failed due to the following ValueError: {error} \033[0m")