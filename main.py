from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from football_engine import FootballMatch


app = FastAPI(
    title="Virtual Football Manager Engine",
    version="1.0.0",
    description="Python football simulation engine for Virtual Football Manager.",
)


# ============================================================
# CORS
# ============================================================

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


# ============================================================
# MATCH STORAGE
# ============================================================

matches: dict[str, FootballMatch] = {}


# ============================================================
# HEALTH
# ============================================================

@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Virtual Football Manager Python Engine",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "football-engine",
        "matches": len(matches),
    }


# ============================================================
# CREATE MATCH
# ============================================================

@app.post("/match/create")
def create_match(config: dict[str, Any]):
    match_id = str(
        config.get("matchId", "")
    ).strip()

    if not match_id:
        raise HTTPException(
            status_code=400,
            detail="matchId is required",
        )

    # If this match already exists in memory,
    # don't create another simulation.
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


# ============================================================
# START
# ============================================================

@app.post("/match/{match_id}/start")
def start_match(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    try:
        return match.start()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not start match: {exc}",
        )


# ============================================================
# PAUSE
# ============================================================

@app.post("/match/{match_id}/pause")
def pause_match(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    try:
        return match.pause()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not pause match: {exc}",
        )


# ============================================================
# STATE
# ============================================================

@app.get("/match/{match_id}/state")
def match_state(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    return match.snapshot()


# ============================================================
# TACTICS
# ============================================================

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

    side = body.get(
        "side",
        "home",
    )

    tactics = body.get(
        "tactics",
        {},
    )

    try:
        return match.set_tactics(
            side,
            tactics,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not update tactics: {exc}",
        )


# ============================================================
# FORMATION
# ============================================================

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

    side = body.get(
        "side",
        "home",
    )

    formation = body.get(
        "formation"
    )

    if not formation:
        raise HTTPException(
            status_code=400,
            detail="formation is required",
        )

    try:
        return match.set_formation(
            side,
            formation,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not update formation: {exc}",
        )


# ============================================================
# SUBSTITUTION
# ============================================================

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

    side = body.get(
        "side",
        "home",
    )

    outgoing_id = body.get(
        "outgoingId"
    )

    incoming_id = body.get(
        "incomingId"
    )

    if not outgoing_id:
        raise HTTPException(
            status_code=400,
            detail="outgoingId is required",
        )

    if not incoming_id:
        raise HTTPException(
            status_code=400,
            detail="incomingId is required",
        )

    try:
        return match.substitute(
            side,
            outgoing_id,
            incoming_id,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not substitute player: {exc}",
        )


# ============================================================
# FORCE FINISH
# ============================================================

@app.post("/match/{match_id}/finish")
def finish_match(match_id: str):
    match = matches.get(match_id)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    try:
        return match.finish()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not finish match: {exc}",
        )


# ============================================================
# DELETE
# ============================================================

@app.delete("/match/{match_id}")
def delete_match(match_id: str):
    match = matches.pop(
        match_id,
        None,
    )

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found",
        )

    try:
        match.pause()
    except Exception:
        pass

    return {
        "ok": True,
        "message": "Match deleted",
    }
