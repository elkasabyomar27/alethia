"""Themis: review attestations and actual retrieval runs. No Gemini calls."""

from typing import Literal
from fastapi import APIRouter,Request,Response
from pydantic import BaseModel,ConfigDict,Field
from app.evaluation.dataset import Example,resolve_evidence
from app.evaluation.runner import markdown_report
from app.evaluation.audit import development_audit,review_packet

router=APIRouter(prefix='/api/evaluation',tags=["Themis' Tribunal"])


class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    example: Example
    expected_revision: int=Field(ge=0,strict=True)
    approve: bool=False
    reviewer: str=Field(default='',max_length=80)


class Run(BaseModel):
    model_config=ConfigDict(extra='forbid')
    methods: list[Literal['bm25','dense','hybrid']]=Field(default=['bm25'],min_length=1,max_length=3)
    reviewed_only: bool=True


@router.get('/dataset')
def dataset(request: Request): return request.app.state.evaluations.dataset()


@router.get('/preflight')
def preflight(request: Request): return development_audit(request.app.state.evaluations,request.app.state.dense)


@router.get('/review-packet')
def packet(request: Request):
    import json
    return Response(json.dumps(review_packet(request.app.state.evaluations),ensure_ascii=False,indent=2),
        media_type='application/json',headers={'Content-Disposition':'attachment; filename="alethia-development-review.json"'})


@router.post('/reviews/{identity}')
def review(request: Request,identity: str,body: Review):
    return request.app.state.evaluations.review(identity,body.example,body.expected_revision,body.approve,body.reviewer)


@router.post('/evidence')
def evidence(request: Request,body: Example):
    return resolve_evidence(body,request.app.state.documents)[0]


@router.get('/runs')
def runs(request: Request): return request.app.state.evaluations.runs()


@router.post('/runs',status_code=202)
def start(request: Request,body: Run): return request.app.state.evaluation_runner.start(body.methods,body.reviewed_only)


@router.get('/runs/{identity}')
def report(request: Request,identity: str): return request.app.state.evaluations.report(identity)


@router.get('/runs/{identity}/export')
def export(request: Request,identity: str,format: Literal['json','markdown']='json'):
    import json
    value=request.app.state.evaluations.report(identity)
    content=json.dumps(value,ensure_ascii=False,indent=2) if format=='json' else markdown_report(value)
    suffix='json' if format=='json' else 'md'
    return Response(content,media_type='application/json' if format=='json' else 'text/markdown',
        headers={'Content-Disposition':f'attachment; filename="alethia-evaluation-{identity}.{suffix}"'})
