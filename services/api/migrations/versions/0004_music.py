"""Persistent musical plans and immutable version history (existing data preserved)."""
import sqlalchemy as sa
from alembic import op

revision = '0004_music'
down_revision = '0003_external_render'
branch_labels = None
depends_on = None


def upgrade():
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('video_projects')}
    for name in ('music_plan', 'music_state'):
        if name not in existing:
            op.add_column('video_projects', sa.Column(name, sa.JSON(), nullable=False, server_default='{}'))
    if 'music_versions' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('music_versions',
                    sa.Column('id', sa.String(), primary_key=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('project_id', sa.String(), sa.ForeignKey('video_projects.id'), nullable=False),
                    sa.Column('revision', sa.Integer(), nullable=False),
                    sa.Column('content', sa.JSON(), nullable=False),
                    sa.Column('takes', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('music_versions')
    op.drop_column('video_projects', 'music_state')
    op.drop_column('video_projects', 'music_plan')
