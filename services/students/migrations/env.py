from alembic import context
from sqlalchemy import create_engine
from students.core import Base, Settings

url = context.config.attributes.get("database_url") or Settings().database_url
engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
