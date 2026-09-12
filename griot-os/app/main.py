from __future__ import annotations
import os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("GRIOT_DB_PATH", ROOT / "griot.db"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECTS = {
 "speakpower":"Brand storytelling, communications, market development",
 "tonninyira":"Marketplace product, software, growth and operations",
 "cuepointe":"Community, tournament operations, brand and growth",
 "ubf":"Conservation communications and AI/process automation",
 "fob":"Biodiversity/community ecosystem and operations",
 "other":"Business analysis, brand strategy and project operations",
}
AGENTS = {"story":"StoryAgent","market":"MarketAgent","data":"DataAgent","dev":"DevAgent","research":"ResearchAgent","growth":"GrowthAgent","operations":"OperationsAgent","brand":"BrandAgent","strategy":"StrategyAgent"}
STEPS = ["UNDERSTAND","CONTEXT","EVIDENCE","DIAGNOSE","OPTIONS","RECOMMEND","EXECUTE","MEASURE","LEARN"]

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    project: str | None = None
    mode: str = "think"
    approved: bool = False
class MemoryRequest(BaseModel):
    project: str; kind: str; title: str; content: str; confidence: str = "inference"
class ApprovalRequest(BaseModel):
    action_id: str; approved: bool

app = FastAPI(title="GRIOT OS", version="0.1.1")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def now(): return datetime.now(timezone.utc).isoformat()
def conn():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row
    c.execute("create table if not exists memories(id text primary key,project text,kind text,title text,content text,confidence text,created_at text)")
    c.execute("create table if not exists decisions(id text primary key,project text,request text,recommendation text,status text,created_at text)")
    c.execute("create table if not exists actions(id text primary key,project text,action_type text,payload text,status text,created_at text)")
    c.commit(); return c

def memories(project=None, limit=8):
    c=conn()
    if project: rows=c.execute("select * from memories where project in (?, 'global') order by created_at desc limit ?",(project,limit)).fetchall()
    else: rows=c.execute("select * from memories order by created_at desc limit ?",(limit,)).fetchall()
    c.close(); return [dict(x) for x in rows]

def route(text):
    t=text.lower(); a=[]
    if any(x in t for x in ["brand","story","copy","campaign","content","audience"]): a += ["story","brand"]
    if any(x in t for x in ["market","customer","competitor","growth","sales","revenue"]): a += ["market","growth"]
    if any(x in t for x in ["data","kpi","metric","sql","python","analysis"]): a += ["data"]
    if any(x in t for x in ["code","github","supabase","bug","app","software","api"]): a += ["dev"]
    if any(x in t for x in ["research","latest","evidence","trend"]): a += ["research"]
    if any(x in t for x in ["process","workflow","sop","automation","operations"]): a += ["operations"]
    if not a: a=["strategy"]
    if "strategy" not in a: a.append("strategy")
    return list(dict.fromkeys(a))

def prompt(req, mems, agents):
    pm=PROJECTS.get(req.project or "other", "Cross-project strategic work")
    m="\n".join(f"- [{x['confidence']}] {x['title']}: {x['content']}" for x in mems) or "- No stored memories retrieved."
    return f'''You are GRIOT OS, Thomas's strategic intelligence and execution agent.\n\nMISSION: Think like a strategist. Validate like a data scientist. Build like a software engineer. Communicate like a storyteller. Operate like an owner.\n\nPROJECT: {req.project or 'cross-project'}\nCONTEXT: {pm}\nACTIVE AGENTS: {', '.join(AGENTS[x] for x in agents)}\nDECISION PROTOCOL: {' → '.join(STEPS)}\n\nEVIDENCE DISCIPLINE: FACT, INFERENCE, HYPOTHESIS, RECOMMENDATION, UNKNOWN. Never present an inference or hypothesis as a fact. Challenge weak assumptions. Never confuse activity with progress.\n\nSTORED MEMORY:\n{m}\n\nREQUEST:\n{req.message}\n\nReturn: 1) Diagnosis 2) Evidence/unknowns 3) Recommendation 4) Next actions 5) Measurement 6) Approval requirement.'''

async def model(prompt_text):
    key=os.getenv("OPENAI_API_KEY")
    if not key: return "GRIOT OS is running in offline orchestration mode. Add OPENAI_API_KEY and OPENAI_MODEL to enable full model reasoning. Routing, memory and decision logging are active."
    base=os.getenv("OPENAI_BASE_URL","https://api.openai.com/v1").rstrip("/")
    payload={"model":os.getenv("OPENAI_MODEL","gpt-4.1-mini"),"messages":[{"role":"system","content":prompt_text}],"temperature":0.2}
    async with httpx.AsyncClient(timeout=90) as client:
        r=await client.post(base+"/chat/completions",headers={"Authorization":"Bearer "+key},json=payload)
        if r.status_code>=400: raise HTTPException(r.status_code,r.text[:1000])
        data=r.json(); choices=data.get("choices",[])
        if not choices: raise HTTPException(502,"Model returned no choices")
        return choices[0]["message"]["content"]

@app.get("/health")
def health(): conn().close(); return {"status":"ok","agent":"GRIOT OS","version":app.version}
@app.get("/projects")
def projects(): return PROJECTS
@app.get("/agents")
def agents(): return AGENTS
@app.get("/memories")
def get_memories(project: str|None=None): return memories(project)
@app.post("/memory")
def create_memory(req: MemoryRequest):
    if req.project not in PROJECTS and req.project!="global": raise HTTPException(400,"Unknown project")
    item={"id":str(uuid.uuid4()),"project":req.project,"kind":req.kind,"title":req.title,"content":req.content,"confidence":req.confidence,"created_at":now()}
    c=conn(); c.execute("insert into memories values(?,?,?,?,?,?,?)",tuple(item.values())); c.commit(); c.close(); return item
@app.post("/chat")
async def chat(req: ChatRequest):
    if req.project and req.project not in PROJECTS: raise HTTPException(400,"Unknown project")
    agents_=route(req.message); mems=memories(req.project); answer=await model(prompt(req,mems,agents_)); did=str(uuid.uuid4())
    c=conn(); c.execute("insert into decisions values(?,?,?,?,?,?)",(did,req.project or "global",req.message,answer[:5000],"analyzed",now())); c.commit(); c.close()
    return {"decision_id":did,"project":req.project,"mode":req.mode,"agents":[AGENTS[x] for x in agents_],"memory_used":len(mems),"answer":answer}
@app.post("/approval")
def approval(req: ApprovalRequest):
    c=conn(); row=c.execute("select * from actions where id=?",(req.action_id,)).fetchone()
    if not row: c.close(); raise HTTPException(404,"Action not found")
    s="approved" if req.approved else "rejected"; c.execute("update actions set status=? where id=?",(s,req.action_id)); c.commit(); c.close(); return {"action_id":req.action_id,"status":s}
@app.get("/")
def root(): return FileResponse(STATIC_DIR / "index.html")
