"""Initial database layout

Revision ID: 89a17b25959f
Revises: 
Create Date: 2026-05-20 16:20:51.315104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


 
revision: str = '89a17b25959f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
     
    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('openstack_project_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('network_id', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_id'), 'projects', ['id'], unique=False)
    op.create_index(op.f('ix_projects_openstack_project_id'), 'projects', ['openstack_project_id'], unique=True)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lms_id', sa.String(), nullable=False),
    sa.Column('role', sa.Enum('STUDENT', 'TEACHER', name='roleenum'), nullable=True),
    sa.Column('ssh_private_key', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_lms_id'), 'users', ['lms_id'], unique=True)
    op.create_table('stands',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('FREE', 'PENDING', 'DEPLOYING', 'READY', 'FREEZE', 'CLEANING', name='standstatusenum'), nullable=False),
    sa.Column('ip_address', sa.String(), nullable=True),
    sa.Column('private_key', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('frozen_until', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stands_id'), 'stands', ['id'], unique=False)
     


def downgrade() -> None:
     
    op.drop_index(op.f('ix_stands_id'), table_name='stands')
    op.drop_table('stands')
    op.drop_index(op.f('ix_users_lms_id'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_projects_openstack_project_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_id'), table_name='projects')
    op.drop_table('projects')
     
