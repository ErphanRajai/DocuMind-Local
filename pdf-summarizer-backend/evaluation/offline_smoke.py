"""Run inside the configured container; deny non-local sockets in this process.

This verifies core runtime assets without disabling the user's network or firewall.
"""
import argparse
import asyncio
import json
import socket

allowed={'127.0.0.1','::1'}
for name in ('host.docker.internal','qdrant_service','localhost'):
    try: allowed.update(item[4][0] for item in socket.getaddrinfo(name,None))
    except OSError: pass
original_connect=socket.socket.connect
connections=[]
denied=[]


def connect(instance,address):
    if isinstance(address,tuple):
        if address[0] not in allowed:
            denied.append(address[0]);raise OSError('Offline smoke test blocked a non-local connection')
        connections.append((address[0],address[1]))
    return original_connect(instance,address)


socket.socket.connect=connect


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reference-id',type=int,required=True);args=parser.parse_args()
    from app.services.llm_service import LLMService
    from app.services.vector_db import search_page_sources
    from app.services.advanced_retrieval import rerank
    from app.services.math_engine import calculate
    await LLMService.startup()
    try:
        vector=await LLMService.get_embedding('انرژی چیست؟')
        pages,_=await search_page_sources([args.reference_id],'انرژی چیست؟')
        ranked=await asyncio.to_thread(rerank,'energy',[{'text':'Energy is the ability to do work.'}])
        answer=''
        async for part in LLMService.stream_messages([{'role':'user','content':'فقط بنویس: آماده'}]): answer+=part
        result=calculate({'expression':'x^2-5*x+6=0'})
        checks={'embedding_1024':len(vector)==1024,'local_retrieval':bool(pages),'cached_reranker':bool(ranked),'local_generation':bool(answer.strip()),'checked_math':result['result']=='{2, 3}' and result['verified'],'no_nonlocal_connections':not denied}
        print(json.dumps({'checks':checks,'connections':sorted(set(connections)),'denied':denied,'scope':'Core runtime in this process under a socket guard; not an OS-wide disconnected-network test.'}))
        if not all(checks.values()):raise SystemExit(1)
    finally: await LLMService.shutdown()


if __name__=='__main__':asyncio.run(main())
