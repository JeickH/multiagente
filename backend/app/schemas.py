from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    nombre: str
    tipo_documento: str
    documento: str
    correo: EmailStr
    password: str

class UserLogin(BaseModel):
    correo: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    nombre: str
    tipo_documento: str
    documento: str
    correo: EmailStr
    class Config:
        orm_mode = True
