drop trigger if exists send_update_event on bgp_updates;
drop function if exists rabbitmq.send_message;
create function rabbitmq.send_message(
  channel text,
  routing_key text,
  message text) returns void as $$

  select  pg_notify(
    channel,
    routing_key || '|' || message
  );
$$ stable language sql;

drop function if exists rabbitmq.on_row_change;
create function rabbitmq.on_row_change() returns trigger as $$
  declare
    row jsonb;
  begin
    row := row_to_json(new)::jsonb;
    perform rabbitmq.send_message('events', 'update-insert', row::text);
    return null;
  end;
$$ stable language plpgsql;

create trigger send_update_event
after insert on bgp_updates
for each row execute procedure rabbitmq.on_row_change();
