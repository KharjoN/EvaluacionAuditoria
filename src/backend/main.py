from typing import Literal, Annotated
from fastapi import FastAPI, Depends, HTTPException, status, Response, Request, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession, AsyncAttrs
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, text
import os
from dotenv import load_dotenv
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import hmac
import hashlib

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

SECRET_KEY = os.getenv("SECRET_KEY")
TOKENIZATION_KEY = os.getenv("TOKENIZATION_KEY", "default_token_key").encode('utf-8')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no definida")

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

class Personas(Base, AsyncAttrs):
    __tablename__ = "personas"

    rut = Column(String, unique=True, nullable = False, index=True)
    public_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String,nullable = False,  index=True)
    apellido = Column(String,nullable = False, index=True)
    id_religion = Column(String, nullable=False)
    
class Usuarios(Base, AsyncAttrs):
    __tablename__ = "usuarios"

    id_usuario = Column(Integer, primary_key=True, index=True)
    correo = Column(String, unique=True, nullable = False,  index=True)
    password = Column(String, nullable = False)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

class PersonaCreate(BaseModel):
    rut: str
    nombre: str
    apellido: str
    id_religion: int

class PersonasRead(BaseModel):
    public_id: uuid.UUID
    rut_token: str
    nombre: str
    apellido: str

class PersonaUpdate(BaseModel):
    nombre: str
    apellido: str
    id_religion: int
class UsuariosRead(BaseModel):
    id_usuario: int
    correo: str

    class Config:
        from_attributes = True

app = FastAPI(
    title = "Servidor backend",
    openapi_url = "/openapi.json",
    docs_url = "/docs",
    redoc_url = "/redoc",
)

#esto es para evitar problemas de conexion en diferentes sistemas.

origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",  
    "http://127.0.0.1:5500",
    "http://localhost:8080", 
    "null",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          
    allow_credentials=True,        
    allow_methods=["*"],           
    allow_headers=["*"],            
)

def _map_persona_to_read_model(persona: Personas) -> PersonasRead:
    """Helper para convertir un modelo de DB Personas a un modelo Pydantic PersonasRead."""
    return PersonasRead(
        public_id=persona.public_id,
        rut_token=create_rut_token(persona.rut),
        nombre=persona.nombre,
        apellido=persona.apellido,
    )

def create_rut_token(rut: str) -> str:
    """Creates a non-reversible, consistent token from a RUT for display purposes."""
    return "rut-" + hmac.new(TOKENIZATION_KEY, rut.encode('utf-8'), hashlib.sha256).hexdigest()[:12]

#codigo para tokenizacion de la contraseña.

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    access_token: Annotated[str | None, Cookie()] = None,
    session: AsyncSession = Depends(get_session)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales. Inicie sesión.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if access_token is None:
        raise credentials_exception
    
    try:
        
        parts = access_token.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise credentials_exception
        token = parts[1]
    except Exception:
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await session.execute(select(Usuarios).where(Usuarios.correo == username))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    return user

CurrentUser = Annotated[Usuarios, Depends(get_current_user)]

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

#end point usado para el uso de token

@app.post("/token", tags=["Autenticación"])
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Usuarios).where(Usuarios.correo == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.correo}, expires_delta=access_token_expires
    )
    
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="none",  
        secure=True   
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/logout", tags=["Autenticación"])
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logout successful"}


@app.post("/personas/", response_model=PersonasRead)
async def create_persona(
    persona: PersonaCreate, 
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session)):
    
   
    existing = await session.execute(select(Personas).where(Personas.rut == persona.rut))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El RUT ya está registrado.")

   
    hashed_religion = get_password_hash(str(persona.id_religion))
    nueva = Personas(rut=persona.rut, nombre=persona.nombre, apellido=persona.apellido, id_religion=hashed_religion)
    session.add(nueva)
    await session.commit()
    await session.refresh(nueva)

    return _map_persona_to_read_model(nueva)

@app.get("/personas/", response_model=list[PersonasRead])
async def read_persona(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Personas).order_by(Personas.nombre)
    )
    personas_db = result.scalars().all()
    
    response_list = [_map_persona_to_read_model(p) for p in personas_db]
    return response_list

@app.get("/personas/{public_id}", response_model=PersonasRead)
async def read_single_persona(
    public_id: uuid.UUID, 
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Personas).where(Personas.public_id == public_id)
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    
    return _map_persona_to_read_model(persona)

@app.put("/personas/{public_id}", response_model=PersonasRead)
async def update_persona(
    public_id: uuid.UUID, 
    persona_update: PersonaUpdate, 
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Personas).where(Personas.public_id == public_id)
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    
   
    hashed_religion = get_password_hash(str(persona_update.id_religion))
    persona.nombre = persona_update.nombre
    persona.apellido = persona_update.apellido
    persona.id_religion = hashed_religion
    
    await session.commit()
    await session.refresh(persona)
    return _map_persona_to_read_model(persona)

@app.delete("/personas/{public_id}", status_code=204)
async def delete_persona(
    public_id: uuid.UUID, 
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Personas).where(Personas.public_id == public_id)
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    await session.delete(persona)
    await session.commit()


@app.post("/users/", response_model=UsuariosRead, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user(correo: str, password: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Usuarios).where(Usuarios.correo == correo))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El correo ya está registrado")

    hashed_password = get_password_hash(password)
    db_user = Usuarios(correo=correo, password=hashed_password)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user

#Estado del servidor
@app.get("/health")
async def health():
    return {"status": "ok"}