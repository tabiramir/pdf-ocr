import uvicorn

if __name__ == "__main__":
    # This starts the server using the Python API instead of the CLI executable
    uvicorn.run(
        "app.main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True
    )