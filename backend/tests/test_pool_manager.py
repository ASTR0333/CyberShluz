import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.models import Project, RoleEnum, Stand, StandStatusEnum, User
from app.core.pool_manager import ActiveStandExistsError, PoolManager


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    project = Project(
        openstack_project_id="demo:slot01",
        name="slot",
        network_id="isolated-per-stand",
    )
    session.add(project)
    session.flush()
    session.add_all(
        [
            Stand(project_id=project.id, status=StandStatusEnum.FREE),
            Stand(project_id=project.id, status=StandStatusEnum.FREE),
            Stand(project_id=project.id, status=StandStatusEnum.FREE),
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_student_cannot_allocate_a_second_active_stand(db_session) -> None:
    db_session.add(User(lms_id="student-1", role=RoleEnum.STUDENT))
    db_session.commit()
    manager = PoolManager(db_session)

    first = manager.allocate_stand("student-1", RoleEnum.STUDENT)

    assert first is not None
    with pytest.raises(ActiveStandExistsError) as error:
        manager.allocate_stand("student-1", RoleEnum.STUDENT)
    assert error.value.stand_id == first.id
    assert error.value.stand_status == StandStatusEnum.PENDING.value


def test_teacher_can_allocate_multiple_stands(db_session) -> None:
    db_session.add(User(lms_id="admin-1", role=RoleEnum.TEACHER))
    db_session.commit()
    manager = PoolManager(db_session)

    first = manager.allocate_stand("admin-1", RoleEnum.TEACHER)
    second = manager.allocate_stand("admin-1", RoleEnum.TEACHER)

    assert first is not None
    assert second is not None
    assert first.id != second.id
