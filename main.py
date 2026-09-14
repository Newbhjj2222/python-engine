from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from football_engine import FootballMatch


app = FastAPI(
    title="Virtual Football Manager Match Engine",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://fmnet-seven.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

matches: dict[str, FootballMatch] = {}


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Virtual Football Manager Match Engine",
        "version": "3.0.0",
        "matches": len(matches),
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "football-engine",
        "version": "3.0.0",
        "matches": len(matches),
    }


@app.post("/match/create")
def create_match(config: dict[str, Any]):
    match_id = str(
        config.get("matchId")
        or config.get("id")
        or ""
    ).strip()

    if not match_id:
        raise HTTPException(
            status_code=400,
            detail="matchId is required",
        )

    if match_id in matches:
        return matches[match_id].snapshot()

    try:
        match = FootballMatch(config)
        matches[match_id] = match
        return match.snapshot()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not create match: {exc}",
        )


@app.post("/match/{match_id}/start")
def start_match(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.start()


@app.post("/match/{match_id}/pause")
def pause_match(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.pause()


@app.get("/match/{match_id}/state")
def get_match_state(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.snapshot()


@app.post("/match/{match_id}/finish")
def finish_match(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.finish()


@app.post("/match/{match_id}/tactics")
def update_tactics(
    match_id: str,
    body: dict[str, Any],
):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.set_tactics(
        body.get("side", "home"),
        body.get("tactics", {}),
    )


@app.post("/match/{match_id}/formation")
def update_formation(
    match_id: str,
    body: dict[str, Any],
):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.set_formation(
        body.get("side", "home"),
        body.get("formation", "4-3-3"),
    )


@app.post("/match/{match_id}/substitute")
def substitute(
    match_id: str,
    body: dict[str, Any],
):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.substitute(
        body.get("side", "home"),
        body.get("outgoingId"),
        body.get("incomingId"),
    )


@app.delete("/match/{match_id}")
def delete_match(match_id: str):
    match = matches.pop(match_id, None)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    match.pause()

    return {
        "ok": True,
        "message": "Match deleted",
    }
