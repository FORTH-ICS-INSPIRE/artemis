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
    row jsonb;
    routing_key text;
  begin
    row := row_to_json(new)::jsonb;
    routing_key := TG_ARGV[0];
    perform rabbitmq.send_message('events', routing_key, row::text);
    return null;
  end;
$$ stable language plpgsql;
