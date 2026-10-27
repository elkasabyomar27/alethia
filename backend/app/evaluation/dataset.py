"""Portable, evidence-linked development examples; no implicit human approval."""

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel,ConfigDict,Field,model_validator
from app.ingestion import IngestionError

ROOT=Path(__file__).resolve().parents[3]
DATASET_PATH=ROOT/'data'/'benchmarks'/'development.json'
RESERVED_PATH=ROOT/'data'/'benchmarks'/'reserved.local.json'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class EvidenceLabel(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document: str=Field(min_length=1,max_length=180)
    quote: str=Field(min_length=12,max_length=1200)
    grade: int=Field(default=1,ge=1,le=3,strict=True)


class Example(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: str=Field(pattern=r'^[a-z0-9-]{1,64}$')
    group_id: str=Field(pattern=r'^[a-z0-9-]{1,64}$')
    split: Literal['dev','test']='dev'
    question: str=Field(min_length=1,max_length=500)
    language: Literal['en','ar_msa','ar_egy']
    category: Literal['factual','paraphrase','multi_document','unanswerable','ambiguous']
    reference_answer: str=Field(min_length=1,max_length=2000)
    answerable: bool
    evidence: list[EvidenceLabel]=Field(max_length=8)

    @model_validator(mode='after')
    def check_labels(self):
        if not self.question.strip() or not self.reference_answer.strip():
            raise ValueError('Question and reference answer cannot be blank.')
        if self.answerable != bool(self.evidence):
            raise ValueError('Answerable questions require evidence; unsupported questions must not have positive labels.')
        return self


def load_dataset(path=DATASET_PATH, *, reserved_path=None):
    if path.stat().st_size>1024*1024: raise IngestionError('Dataset exceeds 1 MiB.',413)
    data=json.loads(path.read_text(encoding='utf8'))
    examples=[Example.model_validate(item) for item in data['examples']]
    # Only the default application dataset discovers the ignored local holdout.
    # Explicit fixture/import paths never silently merge machine-local questions.
    private_path=Path(reserved_path) if reserved_path is not None else (RESERVED_PATH if Path(path)==DATASET_PATH else None)
    if private_path is not None and private_path.exists():
        if private_path.stat().st_size>1024*1024: raise IngestionError('Reserved dataset exceeds 1 MiB.',413)
        private=json.loads(private_path.read_text(encoding='utf8'))
        if private['dataset_id']!=data['dataset_id']:
            raise ValueError('Reserved dataset identity does not match development dataset.')
        reserved=[Example.model_validate(item) for item in private['examples']]
        if any(item.split!='test' for item in reserved):
            raise ValueError('Private reserved dataset must contain test examples only.')
        examples.extend(reserved)
    if not 1<=len(examples)<=250 or len({item.id for item in examples})!=len(examples):
        raise ValueError('Dataset must contain 1–250 uniquely identified questions.')
    validate_separation(examples)
    return data['dataset_id'],examples


def validate_separation(examples):
    """Check seeds and edited development overlays with the same leakage rules."""
    groups={}
    questions={}
    labels=[]
    for item in examples:
        if item.group_id in groups and groups[item.group_id]!=item.split:
            raise ValueError('A paraphrase/evidence group cannot cross dev/test splits.')
        groups[item.group_id]=item.split
        question=' '.join(unicodedata.normalize('NFKC',item.question).casefold().split())
        if question in questions:
            raise ValueError('Duplicate normalized question text is not allowed, including across splits.')
        questions[question]=item.id
        for label in item.evidence:
            for split,document,quote in labels:
                if split!=item.split and document==label.document and (quote in label.quote or label.quote in quote):
                    raise ValueError('Overlapping labelled evidence cannot cross dev/test splits.')
            labels.append((item.split,label.document,label.quote))


def read_encoder_corpus(dense):
    """Read verified chunk offsets without loading an embedding worker."""
    from app.rag.dense_artifacts import read_chunk_db,verify_generation
    with dense._artifacts:
        active=dense._active()
        if active is None: raise IngestionError('Encoder snapshot missing.',409)
        folder,manifest=active
        verify_generation(folder,manifest)
        with dense.store.connect() as connection:
            parents={row['id']:dict(row) for row in connection.execute('SELECT id,document_id,start_char FROM segments')}
        connection=read_chunk_db(folder)
        try:
            chunks=[]
            for chunk in connection.execute('SELECT * FROM chunks'):
                parent=parents.get(chunk['parent_id'])
                if parent is None: raise IngestionError('Encoder source changed. Build a current index before checking evidence.',409)
                chunks.append({'id':chunk['id'],'document_id':parent['document_id'],
                    'start_char':parent['start_char']+chunk['start'],'end_char':parent['start_char']+chunk['end']})
        finally: connection.close()
    return folder,manifest,chunks


def corpus_fingerprint(documents):
    return fingerprint(sorted((item['filename'],item['content_hash']) for item in documents.list_documents()))


def resolve_evidence(example,documents,chunks=None):
    resolved=[]; relevance={}
    for label in example.evidence:
        matches=[item for item in documents.list_documents() if item['filename']==label.document]
        if len(matches)!=1:
            raise IngestionError(f'Evidence document must resolve uniquely: {label.document}.',409)
        doc=documents.get(matches[0]['id'])
        start=doc['text'].find(label.quote)
        if start<0 or doc['text'].find(label.quote,start+1)>=0:
            raise IngestionError(f'Evidence quote is absent or ambiguous in {label.document}.',409)
        end=start+len(label.quote)
        parent=next((item for item in doc['segments'] if item['start_char']<=start and end<=item['end_char']),None)
        if parent is None: raise IngestionError('Evidence quote crosses source boundaries; use complete spans inside individual sources.',409)
        eligible=[]
        if chunks is not None:
            for chunk in chunks:
                if chunk['document_id']==doc['id'] and chunk['start_char']<=start and end<=chunk['end_char']:
                    eligible.append(chunk['id']); relevance[chunk['id']]=max(relevance.get(chunk['id'],0),label.grade)
            if not eligible:
                raise IngestionError('An evidence quote crosses chunk boundaries. Choose a complete supporting span within a chunk.',409)
        resolved.append({'document':label.document,'document_id':doc['id'],'source_id':parent['id'],'content_hash':doc['content_hash'],
            'quote':label.quote,'start_char':start,'end_char':end,'grade':label.grade,'chunk_ids':eligible})
    return resolved,relevance
