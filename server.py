import fastapi
import asyncio
import aiosqlite
from contextlib import asynccontextmanager
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import Literal
from order_book import OrderBook
from order_book import Order

#Initialize the SQLite database file using an async context manager
@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    app.state.db = await aiosqlite.connect("ledger.db")
    await app.state.db.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        makerId TEXT,
                        takerId TEXT,
                        price REAL,
                        volume REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    ); """)
    await app.state.db.commit()
    yield
    #Close the .db file gracefully when the server stops running
    await app.state.db.close()

#Initialize the fastAPI and OrderBook object and create an asyncio global lock instance
app = fastapi.FastAPI(lifespan=lifespan)
matching_engine = OrderBook()
engine_lock = asyncio.Lock()

#Define the pydantic class declaring the expected shape of the input variables to generate orders
class IncomingOrder(BaseModel):
    side: Literal["buy", "sell"]
    price: float = Field(gt=0)
    amount: float = Field(gt=0)
    order_type: Literal["GTC", "IOC", "FOK"] = 'GTC'
    client_id: str | None = None

#WebSocket connection manager class
class ConnectionManager:
    def __init__(self):
        self.active_sockets = []

    async def handle_disconnection(self, websocket):
        self.active_sockets.remove(websocket)
        print("Client disconnected")

    async def new_connection(self, websocket):
        #Establish connection with the user
        await websocket.accept()
        self.active_sockets.append(websocket)
        await websocket.send_json(matching_engine.export_market())
        #Try-except block with infinite loop to check if the user is still connected to the websocket and make it inactive if disconnected
        try:
            while True:
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            await self.handle_disconnection(websocket)
    
    async def update_broadcast(self):
        #Update every active websocket in O(N) time without user-lag bottlenecks using asyncio.gather
        sending_tasks = [websocket.send_json(matching_engine.export_market()) for websocket in self.active_sockets]
        await asyncio.gather(*sending_tasks)

connection_manager = ConnectionManager()

#Test GET request
@app.get("/check")
def check_status():
    return {"status": "Online"}

#POST order request backed up by pydantic's BaseModel
@app.post("/order")
async def handle_request(data: IncomingOrder):
    #Take the incoming order params, generate an Order object and add it to the OrderBook with asynchronous handling
    async with engine_lock: 
        order = Order(data.side, data.price, data.amount, data.order_type, data.client_id)
        order_logs = matching_engine.add_order(order)
        
        #Broadcast the change in market depth to every active websocket
        await connection_manager.update_broadcast()

        #Write every log into the SQL database and commit them
        for log in order_logs:
            await app.state.db.execute(
                "INSERT INTO trades (makerId, takerId, price, volume) VALUES (?, ?, ?, ?)", 
                (log["makerId"], log["takerId"], log["price"], log["volume"]))
        await app.state.db.commit()

        return f"Ingested {data.side} order with amount {data.amount} at price: {data.price}"

#GET market depth using the dedicated method and asynchronous handling
@app.get("/depth")
async def get_market(depth: int | None = None):
    async with engine_lock:
        market = matching_engine.export_market(depth)
        return market

#WebSocket stream to push live market depth updates to users in real time
@app.websocket("/stream")
async def stream_market(websocket: WebSocket):
    await connection_manager.new_connection(websocket)

#Type 'uvicorn server:app --reload' in the terminal to initialize the uvicorn server aside from running the script
#The server is running locally on port 8000 (default). For WebSocket connection the URL is: 'ws://localhost:8000/stream'