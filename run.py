# run.py
import uvicorn

if __name__ == "__main__":
    # app.main:app means "look in the 'app' package, inside 'main.py', for the 'app' object"
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )