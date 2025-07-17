from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession, AsyncAttrs
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no definida")

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    future=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

class Personas(Base, AsyncAttrs):
    __tablename__ = "personas"

    rut = Column(String,nullable = False, primary_key=True, index=True)
    nombre = Column(String,nullable = False, unique=True, index=True)
    apellido = Column(String,nullable = False, unique=True, index=True)
    religion = Column(String,nullable = False, unique=True, index=True)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

class PersonaCreate(BaseModel):
    rut: str
    nombre: str
    apellido: str
    religion: str

class PersonasRead(BaseModel):
    rut: str
    nombre: str
    apellido: str
    religion: str

    class Config:
        orm_mode = True



app = FastAPI(
    title = "Servidor backend",
    openapi_url = "/openapi.json",
    docs_url = "/docs",
    redoc_url = "/redoc",
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.post("/personas/", response_model=PersonasRead)
async def create_persona(
    persona: PersonaCreate, 
    session: AsyncSession = Depends(get_session)):
    nueva = Personas(rut=persona.rut, nombre=persona.nombre, apellido=persona.apellido, religion=persona.religion)
    session.add(nueva)
    await session.commit()
    await session.refresh(nueva)
    return nueva

@app.get("/personas/{rut}", response_model=PersonasRead)
async def read_persona(rut: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Personas).filter(Personas.rut == rut)
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    return persona

class PersonaUpdate(BaseModel):
    nombre: str
    apellido: str
    religion: str

@app.put("/personas/{rut}", response_model=PersonasRead)
async def update_persona(
    rut: str, persona_update: PersonaUpdate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Personas).filter(Personas.rut == rut)
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    
    persona.nombre = persona_update.nombre
    persona.apellido = persona_update.apellido
    persona.religion = persona_update.religion
    
    await session.commit()
    await session.refresh(persona)
    return persona

@app.delete("/personas/{rut}", status_code=204)
async def delete_persona(rut: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Personas).filter(Personas.rut == rut)
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    await session.delete(persona)
    await session.commit()


@app.get("/health")
async def health():
    return {"status": "ok"}