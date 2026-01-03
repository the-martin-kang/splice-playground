from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Splice Playground API")

app.add_middleware(
   CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 질환 데이터
diseases = [
    {"id": 1, "name": "Spinal Muscular Atrophy", "gene": "SMN1", "description": "척수성 근 위축증"},
    {"id": 2, "name": "Sickle Cell Disease", "gene": "HBB", "description": "낫모양 적혈구 증후군"},
    {"id": 3, "name": "Cystic Fibrosis", "gene": "CFTR", "description": "낭포성 섬유증"},
    {"id": 4, "name": "Duchenne Muscular Dystrophy", "gene": "DMD", "description": "뒤센 근이영양증"},
    {"id": 5, "name": "Familial Hypercholesterolemia", "gene": "LDLR", "description": "가족성 고콜레스테롤혈증"},
    {"id": 6, "name": "Retinitis Pigmentosa", "gene": "RHO", "description": "망막색소변성증"}
]

class DiseaseSelection(BaseModel):
    disease_id: int

@app.get("/")
def index():
    return {"message": "Splice Playground API"}

@app.get("/api/v1/diseases")
def get_diseases():
    return {"diseases": diseases}

@app.post("/api/v1/select-disease")
def select_disease(selection: DiseaseSelection):
    disease = next((d for d in diseases if d["id"] == selection.disease_id), None)
    if not disease:
        return {"error": "Disease not found"}
    
    return {
        "selected_disease": disease,
        "next_step": "dna_manipulation",
        "message": f"{disease['name']} 선택됨"
    }
