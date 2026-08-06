 
from celery.schedules import crontab

 
 

BEAT_SCHEDULE = {
     
    "cleanup-expired-stands": {
        "task": "app.tasks.cleanup.cleanup_expired_stands",
        "schedule": 60.0,   
        "options": {"queue": "celery"}
    },
    
     
    "sync-project-pool": {
        "task": "app.tasks.pool.sync_pool_status",
        "schedule": 300.0,
        "options": {"queue": "celery"}
    },
    
     
    "monitor-active-stands": {
        "task": "app.tasks.monitor.monitor_all_stands_task",
        "schedule": 300.0,   
        "options": {"queue": "celery"}
    },
    
     
    "cleanup-old-logs": {
        "task": "app.tasks.maintenance.cleanup_old_logs",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "maintenance"}
    }
}