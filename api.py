from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import initialize_database, get_runs, get_run
import json

app = FastAPI(
    title="Policy as Code API",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_database()


@app.get("/")
def root():
    return {"message": "Policy as Code API is running"}


@app.get("/api/runs")
def api_get_runs():
    return get_runs()


@app.get("/api/runs/{run_id}")
def api_get_run(run_id: int):

    run = get_run(run_id)

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Run not found"
        )

    # Force a JSON-safe conversion before FastAPI sees the data.
    try:
        return json.loads(
            json.dumps(
                run,
                allow_nan=False,
                default=str
            )
        )

    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"JSON serialization error: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )