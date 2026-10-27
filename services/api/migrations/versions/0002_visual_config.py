"""Keep existing projects on their original compositor; new 3D selection is explicit."""
import sqlalchemy as sa
from alembic import op

revision = "0002_visual_config"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("video_projects")}
    if "visual_config" not in columns:
        op.add_column("video_projects", sa.Column("visual_config", sa.JSON(), nullable=False,
                      server_default='{"engine":"compositor_2d"}'))


def downgrade():
    op.drop_column("video_projects", "visual_config")
