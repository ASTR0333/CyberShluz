import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1 import deploy as deploy_api
from app.core.database import Base
from app.core.models import Project, RoleEnum, Stand, StandStatusEnum, User
from app.core.topology import default_lab3_config
from app.schemas.contracts import DeployRequest


def test_student_payload_is_ignored_and_subnet_comes_from_stand_id(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    project = Project(
        openstack_project_id="demo:slot01",
        name="slot-01",
        network_id="isolated-per-stand",
    )
    user = User(lms_id="student-1", role=RoleEnum.STUDENT)
    db.add_all([project, user])
    db.flush()
    stand = Stand(project_id=project.id, status=StandStatusEnum.FREE)
    db.add(stand)
    db.commit()

    capacity_configs = []

    class FakeOpenStackClient:
        def required_vcpus(self, deployment):
            capacity_configs.append(deployment)
            return 1

        def check_capacity(self, required_vcpus):
            assert required_vcpus == 1
            return 0.1

    queued = {}
    monkeypatch.setattr(deploy_api, "OpenStackClient", FakeOpenStackClient)
    monkeypatch.setattr(deploy_api.celery_app.backend, "forget", lambda _task_id: None)
    monkeypatch.setattr(
        deploy_api.deploy_stand_task,
        "apply_async",
        lambda **kwargs: queued.update(kwargs),
    )

    spoofed = default_lab3_config().model_dump()
    spoofed["network"] = {
        "cidr": "10.200.0.0/24",
        "gateway": "10.200.0.1",
        "dhcp_start": "10.200.0.100",
        "dhcp_end": "10.200.0.200",
        "dns_nameservers": ["8.8.8.8"],
        "external_network": "attacker-selected-network",
    }
    for vm in spoofed["vms"]:
        vm["ip"] = vm["ip"].replace("10.10.0", "10.200.0")

    response = asyncio.run(
        deploy_api.deploy(
            DeployRequest(
                user_id="ignored",
                lab_id=3,
                role="teacher",
                deployment=spoofed,
            ),
            db=db,
            user={"sub": "student-1", "role": "student", "user_id": user.id},
        )
    )

    assert response.stand_id == str(stand.id)
    assert capacity_configs[0].network.external_network != "attacker-selected-network"
    queued_deployment = queued["args"][4]
    assert queued_deployment["network"]["cidr"] == "10.10.0.0/24"
    assert queued_deployment["vms"][0]["ip"] == "10.10.0.10"
    assert queued_deployment["network"]["external_network"] != "attacker-selected-network"
    db.close()
