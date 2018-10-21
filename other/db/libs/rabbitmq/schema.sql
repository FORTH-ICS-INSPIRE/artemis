drop schema if exists rabbitmq cascade;
create schema rabbitmq;
grant usage on schema rabbitmq to public;

create or replace function rabbitmq.send_message(
  channel text,
  routing_key text,
  message text) returns void as $$

  select  pg_notify(
    channel,
    routing_key || '|' || message
  );
$$ stable language sql;

create or replace function rabbitmq.on_row_change() returns trigger as $$
  declare
    routing_key text;
    row jsonb;
    config text;
    excluded_columns text[];
    col text;
  begin
    routing_key := 'row_change'
                   '.table-'::text || TG_TABLE_NAME::text ||
                   '.event-'::text || TG_OP::text;
    if (TG_OP = 'DELETE') then
        row := row_to_json(old)::jsonb;
    elsif (TG_OP = 'UPDATE') then
        row := row_to_json(new)::jsonb;
    elsif (TG_OP = 'INSERT') then
        row := row_to_json(new)::jsonb;
    end if;

    -- decide what row columns to send based on the config parameter
    -- there is a 8000 byte hard limit on the payload size so sending many big columns is not possible
    if ( TG_NARGS = 1 ) then
      config := TG_ARGV[0];

      routing_key := 'row_change'
                     '.table-'::text || config::text ||
                     '.event-'::text || TG_OP::text;
    end if;
    perform rabbitmq.send_message('events', routing_key, row::text);
    return null;
  end;
$$ stable language plpgsql;

