from alembic import context

from hiring.config import Settings
from hiring.database import make_engine
from hiring.models import Base


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=Settings().database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    run(context.config.attributes["connection"])
else:
    engine = make_engine(Settings().database_url)
    with engine.connect() as connection:
        run(connection)
        connection.commit()
    engine.dispose()
