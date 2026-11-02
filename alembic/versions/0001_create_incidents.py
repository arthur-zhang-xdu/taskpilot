"""创建故障表及服务时间索引。"""
from alembic import op
import sqlalchemy as sa

revision = "0001_create_incidents"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.Text(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("incident_id"),
        *(sa.CheckConstraint(f"{field} ~ '[^[:space:]]'", name=f"ck_incidents_{field}_nonblank")
          for field in ("incident_id", "service", "error_type", "message")),
        sa.CheckConstraint("severity IN ('P1', 'P2', 'P3')", name="ck_incidents_severity"),
    )
    op.create_index("ix_incidents_service_occurred_at", "incidents", ["service", "occurred_at"])


def downgrade():
    op.drop_index("ix_incidents_service_occurred_at", table_name="incidents")
    op.drop_table("incidents")
