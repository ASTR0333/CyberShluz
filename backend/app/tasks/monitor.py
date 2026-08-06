 
import os
import json
import tempfile
import subprocess
from app.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.models import Stand, StandStatusEnum

@celery_app.task
def monitor_all_stands_task():
    """
    Мастер-таска (запускается по таймеру).
    Ищет все готовые стенды и ставит для каждого отдельную задачу сбора метрик.
    """
    with SessionLocal() as db:
        stands = db.query(Stand).filter(Stand.status == StandStatusEnum.READY).all()
        for stand in stands:
            if stand.ip_address and stand.private_key:
                monitor_single_stand_task.delay(stand.id)
    return f"Triggered monitoring for {len(stands)} stands."

@celery_app.task(bind=True, max_retries=1)
def monitor_single_stand_task(self, stand_id: int):
    """
    Изолированная таска для одного стенда. Запускает Ansible и парсит метрики.
    """
    with SessionLocal() as db:
        stand = db.query(Stand).filter(Stand.id == stand_id).first()
        if not stand or stand.status != StandStatusEnum.READY or not stand.ip_address:
            return "Стенд не готов к мониторингу."

        ip = stand.ip_address
        private_key = stand.private_key

     
    fd, key_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd, 'w') as f:
        f.write(private_key)
    os.chmod(key_path, 0o600)

    try:
        playbook_path = "/app/ansible/monitor_stands.yml"
        if not os.path.exists(playbook_path):
            return "Плейбук мониторинга не найден в контейнере!"

        env = os.environ.copy()
        env["ANSIBLE_STDOUT_CALLBACK"] = "json"
        env["ANSIBLE_HOST_KEY_CHECKING"] = "False"

        cmd = [
            "ansible-playbook",
            playbook_path,
            "-i", f"{ip},",
            "--private-key", key_path,
            "-u", "student"
        ]

         
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
         
        try:
            json_start = result.stdout.find("{")
            if json_start != -1:
                parsed_data = json.loads(result.stdout[json_start:])
                metrics = None
                
                 
                for play in parsed_data.get("plays", []):
                    for task in play.get("tasks", []):
                        for _host, host_data in task.get("hosts", {}).items():
                            if "ansible_facts" in host_data and "metrics" in host_data["ansible_facts"]:
                                metrics = host_data["ansible_facts"]["metrics"]
                            elif "metrics" in host_data:
                                metrics = host_data["metrics"]
                            elif "msg" in host_data and isinstance(host_data["msg"], dict) and "cpu" in host_data["msg"]:
                                metrics = host_data["msg"]

                 
                if metrics:
                    with SessionLocal() as db:
                        stand = db.query(Stand).filter(Stand.id == stand_id).first()
                        if stand:
                            stand.vm_details = metrics 
                            db.commit()
                    return f"Monitoring success for stand {stand_id}: {metrics}"
        except Exception as e:
            print(f"Failed to parse Ansible JSON: {e}")
            
        return f"Monitoring completed but metrics not found/parsed for stand {stand_id}."
    finally:
         
        if os.path.exists(key_path):
            os.remove(key_path)