"""Multi-washroom schema expansion, neutral seed data, and sensor record backfill

Revision ID: 0001
Revises:
Create Date: 2026-11-06 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----------------------------------------------------
    # 1. Create users table
    # ----------------------------------------------------
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=100), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='USER'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_role', 'users', ['role'], unique=False)

    # ----------------------------------------------------
    # 2. Create washrooms table
    # ----------------------------------------------------
    op.create_table(
        'washrooms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('building', sa.String(length=100), nullable=True),
        sa.Column('floor', sa.String(length=50), nullable=True),
        sa.Column('room_number', sa.String(length=50), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('gender_type', sa.String(length=20), nullable=False, server_default='UNKNOWN'),
        sa.Column('is_accessible', sa.Boolean(), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_hardware', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('operating_status', sa.String(length=20), nullable=False, server_default='UNKNOWN'),
        sa.Column('manual_occupancy_override', sa.String(length=20), nullable=True),
        sa.Column('operating_hours', sa.String(length=100), nullable=True),
        sa.Column('amenities', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_washrooms_slug', 'washrooms', ['slug'], unique=True)
    op.create_index('ix_washrooms_gender_type', 'washrooms', ['gender_type'], unique=False)
    op.create_index('ix_washrooms_is_active', 'washrooms', ['is_active'], unique=False)
    op.create_index('ix_washrooms_has_hardware', 'washrooms', ['has_hardware'], unique=False)

    # ----------------------------------------------------
    # 3. Create devices table (Many devices per washroom)
    # ----------------------------------------------------
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_uid', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('api_key', sa.String(length=128), nullable=True),
        sa.Column('washroom_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('is_legacy', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('firmware_version', sa.String(length=30), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['washroom_id'], ['washrooms.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_devices_device_uid', 'devices', ['device_uid'], unique=True)
    op.create_index('ix_devices_api_key', 'devices', ['api_key'], unique=False)
    op.create_index('ix_devices_washroom_id', 'devices', ['washroom_id'], unique=False)

    # Enforce database-level partial unique index for active legacy device
    op.execute(
        "CREATE UNIQUE INDEX uq_devices_active_legacy ON devices (is_legacy, status) "
        "WHERE is_legacy = 1 AND status = 'ACTIVE';"
    )

    # ----------------------------------------------------
    # 4. Seed Default Washroom #1 & Legacy Device #1 FIRST
    #    (Ensures foreign key targets exist before batch alter)
    # ----------------------------------------------------
    bind = op.get_bind()
    bind.execute(
        sa.text("""
            INSERT INTO washrooms (
                id, slug, name, building, floor, room_number,
                latitude, longitude, gender_type, is_accessible,
                capacity, is_active, is_demo, has_hardware,
                operating_status, manual_occupancy_override, operating_hours, amenities,
                created_at
            ) VALUES (
                1, 'primary-washroom', 'Primary Washroom', NULL, NULL, NULL,
                NULL, NULL, 'UNKNOWN', NULL,
                NULL, 1, 0, 1,
                'UNKNOWN', NULL, NULL, NULL,
                CURRENT_TIMESTAMP
            )
        """)
    )
    bind.execute(
        sa.text("""
            INSERT INTO devices (
                id, device_uid, name, api_key, washroom_id,
                status, is_legacy, firmware_version, ip_address, last_heartbeat,
                created_at
            ) VALUES (
                1, 'ESP32-PRIMARY-DEVICE', 'Primary ESP32', NULL, 1,
                'ACTIVE', 1, NULL, NULL, NULL,
                CURRENT_TIMESTAMP
            )
        """)
    )

    # ----------------------------------------------------
    # 5. Batch Alter sensor_records
    #    - Add washroom_id (NOT NULL, server_default='1', FK -> washrooms.id)
    #    - Add device_id (server_default='1', FK -> devices.id)
    #    - Preserve all 1,658 existing rows, types, and primary key
    # ----------------------------------------------------
    with op.batch_alter_table('sensor_records', recreate='always') as batch_op:
        batch_op.add_column(
            sa.Column('washroom_id', sa.Integer(), nullable=False, server_default='1')
        )
        batch_op.add_column(
            sa.Column('device_id', sa.Integer(), nullable=True, server_default='1')
        )
        batch_op.create_foreign_key(
            'fk_sensor_records_washroom', 'washrooms', ['washroom_id'], ['id'], ondelete='RESTRICT'
        )
        batch_op.create_foreign_key(
            'fk_sensor_records_device', 'devices', ['device_id'], ['id'], ondelete='SET NULL'
        )
        batch_op.create_index(
            'ix_sensor_records_washroom_time', ['washroom_id', 'timestamp'], unique=False
        )
        batch_op.create_index(
            'ix_sensor_records_device_id', ['device_id'], unique=False
        )

    # Explicit backfill assertion to ensure 100% of rows have washroom_id=1 and device_id=1
    bind.execute(
        sa.text("UPDATE sensor_records SET washroom_id = 1 WHERE washroom_id IS NULL OR washroom_id != 1")
    )
    bind.execute(
        sa.text("UPDATE sensor_records SET device_id = 1 WHERE device_id IS NULL")
    )

    # ----------------------------------------------------
    # 6. Create cleanliness_ratings table
    # ----------------------------------------------------
    op.create_table(
        'cleanliness_ratings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('washroom_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('reported_issue', sa.String(length=50), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('aspects', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['washroom_id'], ['washrooms.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cleanliness_ratings_washroom_id', 'cleanliness_ratings', ['washroom_id'], unique=False)
    op.create_index('ix_cleanliness_ratings_user_id', 'cleanliness_ratings', ['user_id'], unique=False)
    op.create_index('ix_cleanliness_ratings_created_at', 'cleanliness_ratings', ['created_at'], unique=False)

    # ----------------------------------------------------
    # 7. Create maintenance_logs table
    # ----------------------------------------------------
    op.create_table(
        'maintenance_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('washroom_id', sa.Integer(), nullable=False),
        sa.Column('staff_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['washroom_id'], ['washrooms.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['staff_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_maintenance_logs_washroom_id', 'maintenance_logs', ['washroom_id'], unique=False)


def downgrade() -> None:
    op.drop_table('maintenance_logs')
    op.drop_table('cleanliness_ratings')

    with op.batch_alter_table('sensor_records', recreate='always') as batch_op:
        batch_op.drop_index('ix_sensor_records_device_id')
        batch_op.drop_index('ix_sensor_records_washroom_time')
        batch_op.drop_constraint('fk_sensor_records_device', type_='foreignkey')
        batch_op.drop_constraint('fk_sensor_records_washroom', type_='foreignkey')
        batch_op.drop_column('device_id')
        batch_op.drop_column('washroom_id')

    op.execute("DROP INDEX IF EXISTS uq_devices_active_legacy")
    op.drop_table('devices')
    op.drop_table('washrooms')
    op.drop_table('users')
