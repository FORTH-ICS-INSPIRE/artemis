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
  begin
    row := row_to_json(new)::jsonb;
    perform rabbitmq.send_message('events', 'update-insert', row::text);
    return null;
  end;
$$ stable language plpgsql;
