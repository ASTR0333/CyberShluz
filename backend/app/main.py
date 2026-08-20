 
import sys
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

 
from app.core.database import engine, Base
import app.core.models   

 
from app.api.v1 import auth, deploy, status, freeze, check, cleanup, moodle, admin, pubkey, lti, console

 
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(" [STARTUP] Lab Orchestrator API initialized", flush=True)

    try:
        Base.metadata.create_all(bind=engine)
        print(" [DB] Таблицы созданы", flush=True)

        from sqlalchemy import text, inspect
        with engine.connect() as conn:
            inspector = inspect(engine)
            columns = [c["name"] for c in inspector.get_columns("stands")]
            if "vm_details" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN vm_details TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка vm_details", flush=True)
            if "frozen_until" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN frozen_until TIMESTAMP"))
                conn.commit()
                print(" [DB] Добавлена колонка frozen_until", flush=True)
            if "private_key" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN private_key TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка private_key", flush=True)
            if "student_private_key" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN student_private_key TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка student_private_key", flush=True)
            if "lti_context" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN lti_context TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка lti_context", flush=True)
            if "last_check_result" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN last_check_result TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка last_check_result", flush=True)
            if "network_details" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN network_details TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка network_details", flush=True)
            if "deployment_progress" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN deployment_progress INTEGER"))
                conn.commit()
                print(" [DB] Добавлена колонка deployment_progress", flush=True)
            if "deployment_message" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN deployment_message TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка deployment_message", flush=True)
            if "deployment_error" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN deployment_error TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка deployment_error", flush=True)
            if "deployment_updated_at" not in columns:
                conn.execute(text("ALTER TABLE stands ADD COLUMN deployment_updated_at TIMESTAMP"))
                conn.commit()
                print(" [DB] Добавлена колонка deployment_updated_at", flush=True)

             
             
             
             
            try:
                from app.core.config import settings as _settings
                real_pid = _settings.OS_PROJECT_NAME or "hackhaton_team01"
                 
                 
                res = conn.execute(
                    text("UPDATE projects SET "
                         "openstack_project_id = :pid || ':' || 'slot' || CAST(id AS TEXT), "
                         "network_id='isolated-per-stand' "
                         "WHERE openstack_project_id LIKE 'os-prj-uuid%'"),
                    {"pid": real_pid},
                )
                if res.rowcount:
                    conn.commit()
                    print(f" [DB] Пул переозначен на реальный проект КИ ({res.rowcount} слотов)", flush=True)
            except Exception as e:
                conn.rollback()
                print(f" [DB] Реseed пула пропущен (не критично): {e}", flush=True)

            user_columns = [c["name"] for c in inspector.get_columns("users")]
            if "lti_context" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN lti_context TEXT"))
                conn.commit()
                print(" [DB] Добавлена колонка users.lti_context", flush=True)

        from app.core.database import SessionLocal
        from app.core.models import Project, Stand, StandStatusEnum
        db = SessionLocal()
        try:
            if db.query(Project).count() == 0:
                print(" [SEED] Создание пула проектов...", flush=True)
                from app.core.config import settings as _seed_settings
                real_pid = _seed_settings.OS_PROJECT_NAME or "hackhaton_team01"
                for i in range(1, 11):
                    project = Project(
                        name=f"LabSlot_{i:02d}",
                         
                         
                        openstack_project_id=f"{real_pid}:slot{i:02d}",
                        network_id="isolated-per-stand",
                    )
                    db.add(project)
                    db.flush()
                    db.add(Stand(project_id=project.id, status=StandStatusEnum.FREE))
                db.commit()
                print(" [SEED] 10 проектов и стендов создано", flush=True)
        except Exception as e:
            db.rollback()
            print(f" [SEED] Ошибка: {e}", flush=True)
        finally:
            db.close()
    except Exception as e:
        print(f" [STARTUP FATAL] {type(e).__name__}: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        raise

    yield
    print(" [SHUTDOWN] Lab Orchestrator API stopped", flush=True)

 
app = FastAPI(
    title="Lab Orchestrator API",
    description="Secure gateway for cloud lab management",
    version="0.1.0",
    lifespan=lifespan
)

 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

 
@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "lab-orchestrator",
        "participant": "P2",
    }


@app.get("/api/v1/health", tags=["System"], include_in_schema=False)
def health_check_v1():
     
     
    return health_check()

 
app.include_router(auth.router, prefix="/api/v1", tags=["Auth"])
app.include_router(deploy.router, prefix="/api/v1", tags=["Deploy"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])
app.include_router(freeze.router, prefix="/api/v1", tags=["Freeze"])
app.include_router(check.router, prefix="/api/v1", tags=["Check"])
app.include_router(cleanup.router, prefix="/api/v1", tags=["Cleanup"])
app.include_router(moodle.router, prefix="/api/v1", tags=["Moodle Integration"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])
app.include_router(pubkey.router, prefix="/api/v1", tags=["SSH Key"])
app.include_router(lti.router, prefix="/api/v1", tags=["LTI 1.3 (Этап 4)"])
app.include_router(console.router, prefix="/api/v1", tags=["VM Console"])

 
if __name__ == "__main__":
    import uvicorn
     
     
    uvicorn.run(app, host="0.0.0.0", port=8000)
