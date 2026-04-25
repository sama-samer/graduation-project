"""
EVOX AI Dashboard — Python FastAPI Backend
------------------------------------------
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, text, Enum as SAEnum
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel, ConfigDict
import os
import bcrypt
import paho.mqtt.client as mqtt
import json
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# ─── Database Setup ────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:graduation2026@localhost:5432/graduation_project")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── DB Models ──────────────────────────────────────────────────────────────────
class EmployeeUserDB(Base):
    __tablename__ = "employees_users"
    id = Column(String(50), primary_key=True, index=True)
    user_name = Column(String(100), unique=True, nullable=False)
    user_password = Column(String(255), nullable=False)
    devices_assigned = Column(String(255), nullable=True)
    role_commend = Column(String(50), default="employee")

class MachineDB(Base):
    __tablename__ = "machines"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    model = Column(String(100), nullable=False)
    status = Column(SAEnum("online", "offline", "maintenance", name="machine_status"), default="online")

Base.metadata.create_all(bind=engine)


# ─── Pydantic Schemas ──────────────────────────────────────────────────────────
class EmployeeCreate(BaseModel):
    id: str  
    user_name: str
    password: str
    devices_assigned: str
    role_commend: str

class EmployeeResponse(BaseModel):
    id: str
    user_name: str
    devices_assigned: str
    role_commend: str
    model_config = ConfigDict(from_attributes=True)

class MachineCreate(BaseModel):
    id: int
    name: str
    model: str
    status: str = "online"

class MachineResponse(BaseModel):
    id: int
    name: str
    model: str
    status: str
    model_config = ConfigDict(from_attributes=True)

class MqttLogin(BaseModel):
    username: int
    password: int


# ─── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(title="EVOX AI Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Employee Routes ────────────────────────────────────────────────────────────
@app.get("/users", response_model=list[EmployeeResponse])
def get_employees(db: Session = Depends(get_db)):
    return db.query(EmployeeUserDB).all()

@app.post("/users", response_model=EmployeeResponse, status_code=201)
def create_employee(emp: EmployeeCreate, db: Session = Depends(get_db)):
    try:
        if db.query(EmployeeUserDB).filter(EmployeeUserDB.id == emp.id).first():
            raise HTTPException(status_code=400, detail=f"Employee ID #{emp.id} already exists.")
        if db.query(EmployeeUserDB).filter(EmployeeUserDB.user_name == emp.user_name).first():
            raise HTTPException(status_code=400, detail=f"Username '{emp.user_name}' already exists.")

        hashed_password = bcrypt.hashpw(emp.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        new_emp = EmployeeUserDB(
            id=emp.id,
            user_name=emp.user_name,
            user_password=hashed_password,
            devices_assigned=emp.devices_assigned,
            role_commend=emp.role_commend
        )
        db.add(new_emp)
        db.commit()
        db.refresh(new_emp)
        return new_emp
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database insertion failed: {str(e)}")

@app.delete("/users/{user_id}", status_code=204)
def delete_employee(user_id: str, db: Session = Depends(get_db)):
    """Deletes an employee from the database."""
    emp = db.query(EmployeeUserDB).filter(EmployeeUserDB.id == user_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    try:
        db.delete(emp)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete employee: {str(e)}")


# ─── Machine Routes ─────────────────────────────────────────────────────────────
@app.get("/machines", response_model=list[MachineResponse])
def get_machines(db: Session = Depends(get_db)):
    query = text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name ILIKE 'Device_%'")
    existing_tables = db.execute(query).fetchall()

    active_device_ids = set()
    for row in existing_tables:
        t_name = row[0]
        dev_id_str = t_name.split('_')[1] if '_' in t_name else ""
        if dev_id_str.isdigit():
            active_device_ids.add(int(dev_id_str))

    for dev_id in active_device_ids:
        if not db.query(MachineDB).filter(MachineDB.id == dev_id).first():
            auto_machine = MachineDB(id=dev_id, name=f"Auto-Detected {dev_id}", model="Unknown (Legacy)", status="offline")
            db.add(auto_machine)
            
    all_tracked_machines = db.query(MachineDB).all()
    for m in all_tracked_machines:
        if m.id not in active_device_ids:
            db.delete(m)  
            
    db.commit()
    return db.query(MachineDB).all()

@app.post("/machines", response_model=MachineResponse, status_code=201)
def create_machine(machine: MachineCreate, db: Session = Depends(get_db)):
    try:
        if db.query(MachineDB).filter(MachineDB.id == machine.id).first():
            raise HTTPException(status_code=400, detail=f"Device ID #{machine.id} already exists.")

        new_machine = MachineDB(id=machine.id, name=machine.name, model=machine.model, status=machine.status)
        db.add(new_machine)
        
        table_name = f'Device_{machine.id}'
        create_table_sql = text(f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id SERIAL PRIMARY KEY,
                machine_id_range INTEGER,
                id_empluyee_response VARCHAR(20),
                analysis_volte DOUBLE PRECISION,
                analysis_amper DOUBLE PRECISION,
                analysis_productivity TEXT,
                analysis_stat INTEGER,
                analysis_temperature DOUBLE PRECISION,
                order_stat INTEGER,
                order_production TEXT,
                "timestamp" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        db.execute(create_table_sql)
        db.commit()
        db.refresh(new_machine)
        return new_machine
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create machine table: {str(e)}")

@app.delete("/machines/{machine_id}", status_code=204)
def delete_machine(machine_id: int, db: Session = Depends(get_db)):
    """Removes the machine from tracking AND drops the Device table entirely."""
    machine = db.query(MachineDB).filter(MachineDB.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    try:
        # 1. Delete from Master Tracking
        db.delete(machine)
        
        # 2. DROP the Device_XXX table physically from PostgreSQL
        table_name = f'Device_{machine_id}'
        drop_table_sql = text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
        db.execute(drop_table_sql)
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete machine: {str(e)}")


# ─── Login Publishing Route ────────────────────────────────────────────────────
@app.post("/publish_login")
def publish_login(data: MqttLogin):
    try:
        client = mqtt.Client()
        client.connect("192.168.1.8", 1884, 60) 
        payload = json.dumps({"username": data.username, "password": data.password})
        client.publish("test", payload)
        client.disconnect()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    print("🚀 Starting FastAPI Server on port 8000...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)