"""
EVOX AI Dashboard — Python FastAPI Backend
------------------------------------------
"""

from fastapi import FastAPI, HTTPException, Depends, Request
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
MQTT_BROKER_IP = os.getenv("MQTT_BROKER_IP", "192.168.1.8")

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
    last_ip = Column(String(45), nullable=True)

class MachineDB(Base):
    __tablename__ = "machines"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    model = Column(String(100), nullable=False)
    status = Column(SAEnum("online", "offline", "maintenance", name="machine_status"), default="online")
    device_ip = Column(String(45), nullable=True)

Base.metadata.create_all(bind=engine)


# ─── Pydantic Schemas ──────────────────────────────────────────────────────────
class EmployeeCreate(BaseModel):
    id: str  
    user_name: str
    password: str
    devices_assigned: str
    role_commend: str

class EmployeeUpdate(BaseModel):
    user_name: str | None = None
    password: str | None = None
    devices_assigned: str | None = None
    role_commend: str | None = None

class EmployeeResponse(BaseModel):
    id: str
    user_name: str
    devices_assigned: str
    role_commend: str
    last_ip: str | None = None
    model_config = ConfigDict(from_attributes=True)

class MachineCreate(BaseModel):
    id: int
    name: str
    model: str
    status: str = "online"
    device_ip: str | None = None

class MachineUpdate(BaseModel):
    name: str | None = None
    model: str | None = None
    status: str | None = None
    device_ip: str | None = None

class MachineResponse(BaseModel):
    id: int
    name: str
    model: str
    status: str
    device_ip: str | None = None
    model_config = ConfigDict(from_attributes=True)

class MqttLogin(BaseModel):
    username: int
    password: int

class AdminLogin(BaseModel):
    username: str
    password: str


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


# ─── Auth Route ─────────────────────────────────────────────────────────────────
@app.post("/login")
def login_admin(req: AdminLogin, db: Session = Depends(get_db)):
    # Master Fallback Login (In case you lock yourself out)
    if req.username == "admin" and req.password == "admin":
        return {"status": "success", "user": "admin"}
    
    user = db.query(EmployeeUserDB).filter(EmployeeUserDB.user_name == req.username).first()
    
    if not user or user.role_commend != 'manager':
        raise HTTPException(status_code=401, detail="Invalid credentials or you are not a manager.")
        
    if not bcrypt.checkpw(req.password.encode('utf-8'), user.user_password.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid password.")
        
    return {"status": "success", "user": user.user_name}


# ─── Employee Routes ────────────────────────────────────────────────────────────
@app.get("/users", response_model=list[EmployeeResponse])
def get_employees(db: Session = Depends(get_db)):
    return db.query(EmployeeUserDB).all()

@app.post("/users", response_model=EmployeeResponse, status_code=201)
def create_employee(emp: EmployeeCreate, request: Request, db: Session = Depends(get_db)):
    try:
        if db.query(EmployeeUserDB).filter(EmployeeUserDB.id == emp.id).first():
            raise HTTPException(status_code=400, detail=f"Employee ID #{emp.id} already exists.")
        if db.query(EmployeeUserDB).filter(EmployeeUserDB.user_name == emp.user_name).first():
            raise HTTPException(status_code=400, detail=f"Username '{emp.user_name}' already exists.")

        hashed_password = bcrypt.hashpw(emp.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        client_ip = request.client.host 

        new_emp = EmployeeUserDB(
            id=emp.id,
            user_name=emp.user_name,
            user_password=hashed_password,
            devices_assigned=emp.devices_assigned,
            role_commend=emp.role_commend,
            last_ip=client_ip  
        )
        db.add(new_emp)
        db.commit()
        db.refresh(new_emp)
        return new_emp
    except HTTPException: raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database insertion failed: {str(e)}")

@app.put("/users/{user_id}", response_model=EmployeeResponse)
def update_employee(user_id: str, emp: EmployeeUpdate, db: Session = Depends(get_db)):
    db_emp = db.query(EmployeeUserDB).filter(EmployeeUserDB.id == user_id).first()
    if not db_emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    if emp.user_name: db_emp.user_name = emp.user_name
    if emp.password: 
        db_emp.user_password = bcrypt.hashpw(emp.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    if emp.devices_assigned is not None: db_emp.devices_assigned = emp.devices_assigned
    if emp.role_commend: db_emp.role_commend = emp.role_commend
    
    db.commit()
    db.refresh(db_emp)
    return db_emp

@app.delete("/users/{user_id}", status_code=204)
def delete_employee(user_id: str, db: Session = Depends(get_db)):
    emp = db.query(EmployeeUserDB).filter(EmployeeUserDB.id == user_id).first()
    if not emp: raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(emp)
    db.commit()
# ─── Machine Routes ─────────────────────────────────────────────────────────────
@app.get("/machines", response_model=list[MachineResponse])
def get_machines(db: Session = Depends(get_db)):
    # UPDATED: Changed ILIKE to LIKE so it strictly looks for a capital "D"
    query = text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'Device_%'")
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

        new_machine = MachineDB(id=machine.id, name=machine.name, model=machine.model, status=machine.status, device_ip=machine.device_ip)
        db.add(new_machine)
        
        # UPDATED: Strictly capital "D"
        table_name = f'Device_{machine.id}'
        create_table_sql = text(f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id SERIAL PRIMARY KEY,
                machine_id_range INTEGER,
                device_ip VARCHAR(45),
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
    except HTTPException: raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create machine table: {str(e)}")

@app.put("/machines/{machine_id}", response_model=MachineResponse)
def update_machine(machine_id: int, mac: MachineUpdate, db: Session = Depends(get_db)):
    db_mac = db.query(MachineDB).filter(MachineDB.id == machine_id).first()
    if not db_mac:
        raise HTTPException(status_code=404, detail="Machine not found")
        
    if mac.name: db_mac.name = mac.name
    if mac.model: db_mac.model = mac.model
    if mac.status: db_mac.status = mac.status
    if mac.device_ip is not None: db_mac.device_ip = mac.device_ip
    
    db.commit()
    db.refresh(db_mac)
    return db_mac

@app.delete("/machines/{machine_id}", status_code=204)
def delete_machine(machine_id: int, db: Session = Depends(get_db)):
    machine = db.query(MachineDB).filter(MachineDB.id == machine_id).first()
    if not machine: raise HTTPException(status_code=404, detail="Machine not found")
    
    db.delete(machine)
    
    # UPDATED: Targets exact capital "D" table name and drops it directly
    table_name = f'Device_{machine_id}'
    db.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;'))
        
    db.commit()
    
# ─── Login Publishing Route ────────────────────────────────────────────────────
@app.post("/publish_login")
def publish_login(data: MqttLogin):
    try:
        client = mqtt.Client()
        client.connect(MQTT_BROKER_IP, 1884, 60) 
        payload = json.dumps({"username": data.username, "password": data.password})
        client.publish("test", payload)
        client.disconnect()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)