import fastapi

app = fastapi.FastAPI()

@app.get("/check")
def check_status():
    return {"status": "Online"}

#Type 'uvicorn server:app --return' in the terminal to initialize the server aside from running the script