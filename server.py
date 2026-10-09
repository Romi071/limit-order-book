import fastapi
from pydantic import BaseModel, Field
from typing import Literal
from order_book import OrderBook
from order_book import Order

#Define the pydantic class declaring the expected shape of the input variables to generate orders
class IncomingOrder(BaseModel):
    side: Literal["buy", "sell"]
    price: float = Field(gt=0)
    amount: float = Field(gt=0)
    order_type: Literal["GTC", "IOC", "FOK"] = 'GTC'
    client_id: str | None = None

#Initialize the fastAPI and OrderBook object
app = fastapi.FastAPI()
matching_engine = OrderBook()

#Test GET request
@app.get("/check")
def check_status():
    return {"status": "Online"}

#POST order request backed up by pydantic´s BaseModel
@app.post("/order")
def handle_request(data: IncomingOrder):
    #Take the incoming order params, generate an Order object and add it to the OrderBook
    order = Order(data.side, data.price, data.amount, data.order_type, data.client_id)
    matching_engine.add_order(order)
    return f"Ingested {data.side} order at price: {data.price}"

#GET market depth using the dedicated method
@app.get("/depth")
def get_market(depth: int | None = None):
    market = matching_engine.export_market(depth)
    return market

#Type 'uvicorn server:app --reload' in the terminal to initialize the server aside from running the script