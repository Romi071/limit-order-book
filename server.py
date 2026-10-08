import fastapi
from pydantic import BaseModel, Field
from typing import Literal

#Define the pydantic class declaring the expected shape of the input variables to generate orders
class IncomingOrder(BaseModel):
    side: Literal["buy", "sell"]
    price: float = Field(gt=0)
    amount: float = Field(gt=0)
    order_type: Literal["GTC", "IOC", "FOK"] = 'GTC'
    client_id: str | None = None

app = fastapi.FastAPI()

@app.get("/check")
def check_status():
    return {"status": "Online"}

@app.post("/order")
def handle_request(data: IncomingOrder):
    print(f"Ingested order at price: {data.price}")
    return data

#Type 'uvicorn server:app --reload' in the terminal to initialize the server aside from running the script