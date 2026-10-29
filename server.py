import fastapi
import asyncio
import aiosqlite
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from typing import Literal
from order_book import OrderBook, Order

#Initialize the SQLite database file using an async context manager
@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    app.state.db = await aiosqlite.connect("ledger.db")
    await app.state.db.execute("PRAGMA journal_mode=WAL;")
    await app.state.db.execute("PRAGMA synchronous=NORMAL;")
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
    #Initiate the infinite background loop sql flusher
    flusher_task = asyncio.create_task(sql_flusher())

    yield

    #If the server closed and logs were remaining in the buffer, commit them to the SQLite database to prevent state loss
    flusher_task.cancel()
    if len(logs_buffer) > 0:
        logs_buffer_tuples = [(log["makerId"], log["takerId"], log["price"], log["volume"]) for log in logs_buffer]
        await app.state.db.executemany(
            "INSERT INTO trades (makerId, takerId, price, volume) VALUES (?, ?, ?, ?)", logs_buffer_tuples)
        await app.state.db.commit()
    #Close the .db file gracefully when the server stops running
    await app.state.db.close()

#Initialize the fastAPI and OrderBook object and create an asyncio global lock instance
app = fastapi.FastAPI(lifespan=lifespan)
matching_engine = OrderBook()
engine_lock = asyncio.Lock()
logs_buffer = []

#Define the pydantic BaseModel classes declaring the expected shape of the input variables to generate/cancel/amend orders
class IncomingOrder(BaseModel):
    side: Literal["buy", "sell"]
    price: float = Field(gt=0)
    amount: float = Field(ge=1e-8)
    order_type: Literal["GTC", "IOC", "FOK"] = 'GTC'
    client_tag: str | None = None

class CancelOrder(BaseModel):
    orderId: str
    secret_token: str
    
class AmendOrder(BaseModel):
    orderId: str
    secret_token: str
    new_amount: float = Field(ge=1e-8)

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
        except fastapi.WebSocketDisconnect:
            await self.handle_disconnection(websocket)
    
    async def update_broadcast(self):
        #Update every active websocket in O(N) time without user-lag bottlenecks using asyncio.gather
        market_snapshot = matching_engine.export_market()
        sending_tasks = [websocket.send_json(market_snapshot) for websocket in self.active_sockets]
        await asyncio.gather(*sending_tasks)

#Initialize the connection manager
connection_manager = ConnectionManager()

#Background infinite loop function to commit all logs in the buffer into the SQLite database
async def sql_flusher():
    while True:
        #Leave time for the server to process between flushes
        await asyncio.sleep(0.1)
        #If there are any logs in the buffer, convert them to a tuple and insert them into db in C-speed
        if len(logs_buffer) > 0:
            logs_buffer_tuples = [(log["makerId"], log["takerId"], log["price"], log["volume"]) for log in logs_buffer]
            logs_buffer.clear()
            await app.state.db.executemany(
                "INSERT INTO trades (makerId, takerId, price, volume) VALUES (?, ?, ?, ?)", logs_buffer_tuples)
            await app.state.db.commit()

#POST order request backed up by pydantic's BaseModel and lock async handling
@app.post("/order")
async def handle_request(data: IncomingOrder):
    async with engine_lock: 
        #Take the incoming order params, generate an Order object and add it to the OrderBook
        order = Order(data.side, data.price, data.amount, data.order_type, data.client_tag)
        order_logs = matching_engine.add_order(order)

    #Broadcast the change in market depth to every active websocket
    if len(connection_manager.active_sockets) > 0:
        asyncio.create_task(connection_manager.update_broadcast())
    #Create a task to record the logs into SQLite without affecting engine performance
    if len(order_logs) > 0:
        logs_buffer.extend(order_logs)

    return {'orderId': order.id,
            'secret_token': order.secret_token,
            'client_tag': order.client_tag,
            'active': order.active,
            'amount': order.amount,
            'fills': order_logs
            }

#POST cancel order request backed up by pydantic's BaseModel and lock async handling
@app.post("/cancel")
async def cancel_request(data: CancelOrder):
    async with engine_lock: 
        try:
            response = matching_engine.cancel_order(data.orderId, data.secret_token)
        #The secret token was incorrect: HTTP 401 Unauthorized
        except PermissionError as exception:
            return fastapi.responses.JSONResponse(status_code=401, content={'success': False, 'detail': str(exception)})

    #If the cancel succeeded: return HTTP 200 OK
    if response['success']:
        #Broadcast the change in market depth to every active websocket
        if len(connection_manager.active_sockets) > 0:
            asyncio.create_task(connection_manager.update_broadcast())
        return fastapi.responses.JSONResponse(status_code=200, content=response)
    #The order was found, but it is already filled: HTTP 404 Not Found
    else:
        return fastapi.responses.JSONResponse(status_code=404, content=response)
    
#POST amend order request backed up by pydantic's BaseModel and lock async handling
@app.post("/amend")
async def amend_request(data: AmendOrder):
    async with engine_lock: 
        try:
            response = matching_engine.amend_order(data.orderId, data.secret_token, data.new_amount)
        #The secret token was incorrect: HTTP 401 Unauthorized
        except PermissionError as exception:
            return fastapi.responses.JSONResponse(status_code=401, content={'success': False, 'detail': str(exception)})
        
    #If the amend succeeded: return HTTP 200 OK
    if response['success']:
        #Broadcast the change in market depth to every active websocket
        if len(connection_manager.active_sockets) > 0:
            asyncio.create_task(connection_manager.update_broadcast())
        return fastapi.responses.JSONResponse(status_code=200, content=response)
    #The order was found, but it is already filled: HTTP 404 Not found
    else:
        return fastapi.responses.JSONResponse(status_code=404, content=response)

#Test GET request
@app.get("/check")
def check_status():
    return {"status": "Online"}

#GET market depth using the dedicated method and asynchronous handling
@app.get("/depth")
async def get_market(depth: int | None = fastapi.Query(default=None, gt=0)):
    async with engine_lock:
        market = matching_engine.export_market(depth)
        return market

#WebSocket stream to push live market depth updates to users in real time
@app.websocket("/stream")
async def stream_market(websocket: fastapi.WebSocket):
    await connection_manager.new_connection(websocket)

#Type 'uvicorn server:app --no-access-log' in the terminal to initialize the uvicorn server aside from running the script
#The server is running locally on port 8000 (default). For WebSocket connection the URL is: 'ws://localhost:8000/stream'