"""Hermes' Dispatch: explicitly created local tickets only."""

from typing import Literal
from fastapi import APIRouter,Request,Response,Query
from pydantic import BaseModel,ConfigDict,Field

router = APIRouter(prefix='/api/tickets',tags=["Hermes' Dispatch"])
TicketStatus = Literal['open','in_progress','resolved']


class CreateTicket(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    turn_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class UpdateTicket(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1,strict=True)
    status: TicketStatus
    note: str = Field(default='',max_length=2000)


@router.get('')
def list_tickets(request: Request,status: TicketStatus | None=None):
    return request.app.state.tickets.list(status)


@router.post('')
def create_ticket(request: Request,body: CreateTicket,response: Response):
    result=request.app.state.tickets.create(body.conversation_id,body.turn_id)
    response.status_code=201 if result['outcome']=='created' else 200
    return result


@router.get('/{identity}')
def ticket(request: Request,identity: str):
    return request.app.state.tickets.get(identity)


@router.patch('/{identity}')
def update_ticket(request: Request,identity: str,body: UpdateTicket):
    return request.app.state.tickets.update(identity,body.expected_revision,body.status,body.note)


@router.delete('/{identity}',status_code=204)
def delete_ticket(request: Request,identity: str,expected_revision: int=Query(ge=1)):
    request.app.state.tickets.delete(identity,expected_revision)
    return Response(status_code=204)
