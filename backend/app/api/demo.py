"""Attack Lab endpoints: list the demo scenarios and run them from the dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.common import get_services, require_admin
from app.services import Services

router = APIRouter(prefix="/api/demo", tags=["attack lab"])


class RunRequest(BaseModel):
    scenario: str


@router.get("/scenarios")
def list_scenarios(svc: Services = Depends(get_services)):
    return svc.demo.scenarios()


@router.post("/run", dependencies=[Depends(require_admin)])
async def run_scenario(body: RunRequest, svc: Services = Depends(get_services)):
    try:
        return svc.demo.start(body.scenario).model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown scenario {body.scenario!r}") from None


@router.get("/runs")
def list_runs(svc: Services = Depends(get_services)):
    return [r.model_dump(mode="json") for r in svc.demo.list()]


@router.get("/runs/{run_id}")
def get_run(run_id: str, svc: Services = Depends(get_services)):
    run = svc.demo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run.model_dump(mode="json")
