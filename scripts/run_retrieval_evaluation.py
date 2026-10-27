"""Run the local retrieval laboratory. No Gemini or other generation requests."""

import argparse
import http.client
import json
import time


def request(path,payload=None):
    connection=http.client.HTTPConnection('127.0.0.1',8000,timeout=15)
    try:
        connection.request('POST' if payload is not None else 'GET',path,
            json.dumps(payload) if payload is not None else None,{'Content-Type':'application/json'})
        response=connection.getresponse(); value=json.loads(response.read(1024*1024))
        if response.status>=400: raise RuntimeError(value.get('detail','Evaluation request failed.'))
        return value
    finally: connection.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--methods',nargs='+',choices=['bm25','dense','hybrid'],default=['bm25'])
    parser.add_argument('--diagnostic',action='store_true',help='Include unreviewed development examples; their quality metrics remain blank.')
    args=parser.parse_args()
    run=request('/api/evaluation/runs',{'methods':args.methods,'reviewed_only':not args.diagnostic})
    previous=-1
    while run['status']=='running':
        if run['completed']!=previous:
            print(f"{run['completed']}/{run['total']} retrieval requests",flush=True); previous=run['completed']
        time.sleep(1)
        run=next(item for item in request('/api/evaluation/runs') if item['id']==run['id'])
    print(json.dumps(run,ensure_ascii=True,indent=2))
    if run['status']!='complete': raise RuntimeError(run['error'] or 'Run did not complete.')
    print(f"JSON export: http://127.0.0.1:8000/api/evaluation/runs/{run['id']}/export?format=json")


if __name__=='__main__': main()
