"""Run with the schema-owner DATABASE_URL before starting the restricted API."""
import os

from sqlalchemy import inspect, text

from .database import Base, engine
from .models import AUDIT_ACTION_VALUES


def install_audit_guards(connection):
    if connection.dialect.name == "postgresql":
        connection.execute(text("""
            CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              RAISE EXCEPTION 'audit_logs is append-only';
            END $$
        """))
        connection.execute(text("DROP TRIGGER IF EXISTS audit_no_mutation ON audit_logs"))
        connection.execute(text("""
            CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE OR TRUNCATE
            ON audit_logs FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation()
        """))
        connection.execute(text("ALTER TABLE audit_logs ENABLE ALWAYS TRIGGER audit_no_mutation"))
    elif connection.dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            connection.execute(text(f"""
                CREATE TRIGGER IF NOT EXISTS audit_no_{action.lower()}
                BEFORE {action} ON audit_logs BEGIN
                  SELECT RAISE(ABORT, 'audit_logs is append-only');
                END
            """))


def migrate(database_engine=engine):
    Base.metadata.create_all(database_engine)
    with database_engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "auth_version" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0"))
        if connection.dialect.name == "postgresql":
            for action in AUDIT_ACTION_VALUES:
                connection.execute(text(f"ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS '{action}'"))
        # Existing attendance coordinates receive the same minimization as new records.
        # Audit history is never rewritten by this migration.
        if connection.dialect.name == "postgresql":
            connection.execute(text("""UPDATE checkins SET
                latitude = round(latitude::numeric, 3), longitude = round(longitude::numeric, 3),
                distance_from_venue_meters = round(distance_from_venue_meters::numeric / 100) * 100
            """))
        install_audit_guards(connection)


def provision_runtime_role(database_engine=engine):
    """Optional local/deployment bootstrap; password never appears in SQL logs."""
    from psycopg2 import sql
    role = os.environ["APP_DATABASE_ROLE"]
    password = os.environ["APP_DATABASE_PASSWORD"]
    with database_engine.begin() as connection:
        cursor = connection.connection.driver_connection.cursor()
        try:
            cursor.execute("""SELECT %s = current_user OR EXISTS (
                SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
                WHERE r.rolname = %s AND c.relnamespace = 'public'::regnamespace
            )""", (role, role))
            if cursor.fetchone()[0]:
                raise ValueError("The runtime role must be separate from the schema owner")
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if not cursor.fetchone():
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)))
            else:
                cursor.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)))
            cursor.execute(sql.SQL("ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(sql.Identifier(role)))
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role)))
            cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(role)))
            cursor.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC")
            cursor.execute(sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {}").format(sql.Identifier(role)))
        finally:
            cursor.close()


def check_runtime_database(database_engine=engine):
    with database_engine.connect() as connection:
        connection.execute(text("SELECT auth_version FROM users LIMIT 0"))
        if connection.dialect.name == "postgresql":
            unsafe = connection.execute(text("""SELECT
                (SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user)
                OR has_table_privilege(current_user, 'audit_logs', 'UPDATE,DELETE,TRUNCATE')
                OR pg_has_role(current_user, (SELECT relowner FROM pg_class WHERE oid = 'audit_logs'::regclass), 'USAGE')
                OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = 'audit_logs'::regclass
                               AND tgname = 'audit_no_mutation' AND tgenabled = 'A')
            """)).scalar()
            if unsafe:
                raise RuntimeError("API database role must be restricted and audit guards installed. Run python -m app.migrate as schema owner, then use the runtime role.")


if __name__ == "__main__":
    migrate()
    if os.getenv("APP_DATABASE_ROLE"):
        provision_runtime_role()
    print("Database migration complete.")
