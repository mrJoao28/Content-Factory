"""External exports are registered without changing existing projects or jobs."""
import sqlalchemy as sa
from alembic import op

revision = '0003_external_render'
down_revision = '0002_visual_config'
branch_labels = None
depends_on = None


def upgrade():
    if 'external_render_exports' not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table('external_render_exports',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('project_id', sa.String(), sa.ForeignKey('video_projects.id'), nullable=False),
            sa.Column('revision', sa.Integer(), nullable=False),
            sa.Column('semantic_hash', sa.String(), nullable=False),
            sa.Column('manifest', sa.JSON(), nullable=False),
            sa.Column('path', sa.String(), nullable=False),
            sa.Column('state', sa.String(), nullable=False),
            sa.Column('artifact_hash', sa.String(), nullable=True))
        op.create_index('ix_external_render_exports_project_id', 'external_render_exports', ['project_id'])
        op.create_index('ix_external_render_exports_semantic_hash', 'external_render_exports', ['semantic_hash'])


def downgrade():
    op.drop_table('external_render_exports')
