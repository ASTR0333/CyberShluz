from app.core.database import SessionLocal, engine
from app.core.models import Project, Stand, StandStatusEnum, Base
import os

def seed():
     
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
         
        if db.query(Project).count() > 0:
            print("[SEED] Projects already exist. Skipping.")
            return

        print("[SEED] Seeding projects and stands pool...")
        
         
         
        projects_data = [
            {"name": f"LabProject_{i:02d}", "os_id": f"os-prj-uuid-{i:03d}", "net_id": f"net-uuid-{i:03d}"}
            for i in range(1, 11)
        ]

        for p_data in projects_data:
            project = Project(
                name=p_data["name"],
                openstack_project_id=p_data["os_id"],
                network_id=p_data["net_id"]
            )
            db.add(project)
            db.flush()   

             
            stand = Stand(
                project_id=project.id,
                status=StandStatusEnum.FREE
            )
            db.add(stand)
        
        db.commit()
        print(f"[SEED] Successfully created {len(projects_data)} projects and stands.")

    except Exception as e:
        print(f"[SEED] Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed()
