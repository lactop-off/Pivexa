"""add indexes and unique constraints

Revision ID: 127d2002987a
Revises: 13f85f8b639a
Create Date: 2026-06-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = '127d2002987a'
down_revision: Union[str, None] = '13f85f8b639a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 6: ステータス絞り込み・データセット別取得・結果取得を高速化する索引
    op.create_index('idx_jobs_status', 'analysis_jobs', ['status'])
    op.create_index('idx_jobs_dataset', 'analysis_jobs', ['dataset_id'])
    op.create_index('idx_results_job', 'analysis_results', ['job_id'])
    # 6: 同一データセット内の列名は一意（複合 UNIQUE 制約）
    op.create_unique_constraint(
        'uq_dataset_columns_dataset_name', 'dataset_columns', ['dataset_id', 'name']
    )


def downgrade() -> None:
    op.drop_constraint('uq_dataset_columns_dataset_name', 'dataset_columns', type_='unique')
    op.drop_index('idx_results_job', table_name='analysis_results')
    op.drop_index('idx_jobs_dataset', table_name='analysis_jobs')
    op.drop_index('idx_jobs_status', table_name='analysis_jobs')
