from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_csrf, require_module
from app.core.database import get_db
from app.schemas.automation import DeliveryItem, EndpointCreated, EndpointInput, EndpointItem, EventType, InboundResult
from app.services import automation
from app.services.auth import Member

router = APIRouter(prefix="/automation")
hooks = APIRouter(prefix="/hooks")
automation_member = require_module("automation")
MAX_BODY = 64 * 1024


def _run(action):  # type: ignore[no-untyped-def]
    try:
        return action()
    except automation.AutomationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


@router.get("/events", response_model=list[EventType])
def read_event_types(_: Member = Depends(automation_member)) -> list[EventType]:
    return automation.event_types()


@router.get("/endpoints", response_model=list[EndpointItem])
def read_endpoints(db: Session = Depends(get_db), member: Member = Depends(automation_member)) -> list[EndpointItem]:
    return _run(lambda: automation.list_endpoints(db, member))


@router.post("/endpoints", response_model=EndpointCreated, status_code=201)
def add_endpoint(
    payload: EndpointInput,
    db: Session = Depends(get_db),
    member: Member = Depends(automation_member),
    _: None = Depends(require_csrf),
) -> EndpointCreated:
    return _run(lambda: automation.create_endpoint(db, member, payload))


@router.put("/endpoints/{endpoint_id}", response_model=EndpointItem)
def change_endpoint(
    endpoint_id: UUID,
    payload: EndpointInput,
    db: Session = Depends(get_db),
    member: Member = Depends(automation_member),
    _: None = Depends(require_csrf),
) -> EndpointItem:
    return _run(lambda: automation.update_endpoint(db, member, endpoint_id, payload))


@router.post("/endpoints/{endpoint_id}/rotate", response_model=EndpointCreated)
def rotate(
    endpoint_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(automation_member),
    _: None = Depends(require_csrf),
) -> EndpointCreated:
    return _run(lambda: automation.rotate_secret(db, member, endpoint_id))


@router.post("/endpoints/{endpoint_id}/test", response_model=DeliveryItem)
def test_endpoint(
    endpoint_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(automation_member),
    _: None = Depends(require_csrf),
) -> DeliveryItem:
    return _run(lambda: automation.send_test(db, member, endpoint_id))


@router.delete("/endpoints/{endpoint_id}", status_code=204)
def remove_endpoint(
    endpoint_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(automation_member),
    _: None = Depends(require_csrf),
) -> Response:
    _run(lambda: automation.delete_endpoint(db, member, endpoint_id))
    return Response(status_code=204)


@router.get("/deliveries", response_model=list[DeliveryItem])
def read_deliveries(
    endpoint: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    member: Member = Depends(automation_member),
) -> list[DeliveryItem]:
    return _run(lambda: automation.list_deliveries(db, member, endpoint))


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryItem)
def retry(
    delivery_id: UUID,
    db: Session = Depends(get_db),
    member: Member = Depends(automation_member),
    _: None = Depends(require_csrf),
) -> DeliveryItem:
    return _run(lambda: automation.retry_delivery(db, member, delivery_id))


@hooks.post("/{endpoint_id}", response_model=InboundResult)
async def receive(endpoint_id: UUID, request: Request, db: Session = Depends(get_db)) -> InboundResult:
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(status_code=413, detail="İstek gövdesi 64 KB sınırını aşıyor.")
    headers = {key.lower(): value for key, value in request.headers.items()}
    return _run(lambda: automation.handle_inbound(db, endpoint_id, headers, body))
