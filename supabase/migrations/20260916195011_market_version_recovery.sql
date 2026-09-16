-- Retain published immutable versions for recovery. No deletion/GC yet: preserving
-- objects is safer until reader-grace and backup retention are implemented.
create table public.market_data_versions (
  dataset_key text not null,
  object_version text not null,
  record jsonb not null,
  lease_fence bigint not null,
  published_at timestamptz not null default now(),
  primary key(dataset_key, object_version)
);
create index market_versions_recent on public.market_data_versions(dataset_key,published_at desc);
alter table public.market_data_versions enable row level security;
revoke all on public.market_data_versions from anon, authenticated, service_role;
grant select, insert on public.market_data_versions to service_role;

create function private.market_pointer_guard() returns trigger language plpgsql security invoker
set search_path='' as $$
begin
  if current_user <> 'postgres' and coalesce(current_setting('quant.market_publish',true),'') <> 'on' then
    raise exception using errcode='42501',message='Use fenced market publication';
  end if;
  return new;
end;
$$;
revoke all on function private.market_pointer_guard() from public;
revoke all on public.market_data_metadata from service_role;
grant select, insert, update on public.market_data_metadata to service_role;
create trigger fenced_pointer before insert or update on public.market_data_metadata
for each row execute function private.market_pointer_guard();

create function private.market_version_guard() returns trigger language plpgsql security invoker
set search_path='' as $$
begin
  if current_user <> 'postgres' and (pg_trigger_depth() < 2 or coalesce(current_setting('quant.market_publish',true),'') <> 'on') then
    raise exception using errcode='42501',message='Versions are recorded by fenced publication';
  end if;
  return new;
end;
$$;
revoke all on function private.market_version_guard() from public;
create trigger version_insert_guard before insert on public.market_data_versions
for each row execute function private.market_version_guard();

create function private.record_market_version() returns trigger language plpgsql security invoker
set search_path='' as $$
begin
  if new.record->>'object_version' is null then
    raise exception using errcode='22023',message='Object version is required';
  end if;
  insert into public.market_data_versions(dataset_key,object_version,record,lease_fence,published_at)
  values(new.dataset_key,new.record->>'object_version',new.record,new.lease_fence,new.published_at);
  return new;
end;
$$;
revoke all on function private.record_market_version() from public;
create trigger retain_published_version after insert or update on public.market_data_metadata
for each row execute function private.record_market_version();
insert into public.market_data_versions(dataset_key,object_version,record,lease_fence,published_at)
select dataset_key,record->>'object_version',record,lease_fence,published_at
from public.market_data_metadata;

create or replace function public.publish_market_dataset(p_dataset_key text,p_fence bigint,p_lease_token uuid,p_record jsonb)
returns boolean language plpgsql security invoker set search_path='' as $$
begin
  perform 1 from public.data_refresh_status where dataset_key=p_dataset_key and lease_fence=p_fence
    and lease_token=p_lease_token and lease_expires_at>clock_timestamp() for update;
  if not found then return false; end if;
  if p_record->>'format_version' is distinct from '1'
    or p_record->>'bucket' is distinct from 'market-data'
    or p_record->>'checksum_sha256' is null
    or p_record->>'checksum_sha256' !~ '^[a-f0-9]{64}$' then
    raise exception using errcode='22023',message='Invalid artifact metadata';
  end if;
  if p_dataset_key='universe:sp500' then
    if p_record->>'kind' is distinct from 'universe'
      or jsonb_typeof(p_record->'constituents') is distinct from 'array' then
      raise exception using errcode='22023',message='Invalid constituent snapshot';
    end if;
    if jsonb_array_length(p_record->'constituents') not between 400 and 600
      or exists(select 1 from jsonb_array_elements(p_record->'constituents') x
        where jsonb_typeof(x->'symbol') is distinct from 'string'
          or x->>'symbol' !~ '^[A-Z0-9.^=-]{1,20}$'
          or jsonb_typeof(x->'name') is distinct from 'string' or length(x->>'name') not between 1 and 300)
      or (select count(distinct x->>'symbol') from jsonb_array_elements(p_record->'constituents') x)
        <> jsonb_array_length(p_record->'constituents') then
      raise exception using errcode='22023',message='Invalid constituent snapshot';
    end if;
    perform set_config('quant.universe_write','on',true);
    update public.instrument_universe set active=false;
    insert into public.instrument_universe(symbol,name,sector,active)
      select symbol,name,sector,true from jsonb_to_recordset(p_record->'constituents') as x(symbol text,name text,sector text)
      on conflict(symbol) do update set name=excluded.name,sector=excluded.sector,active=true,updated_at=clock_timestamp();
    perform set_config('quant.universe_write','off',true);
  end if;
  perform set_config('quant.market_publish','on',true);
  insert into public.market_data_metadata(dataset_key,record,lease_fence) values(p_dataset_key,p_record,p_fence)
    on conflict(dataset_key) do update set record=excluded.record,lease_fence=excluded.lease_fence,published_at=clock_timestamp();
  update public.data_refresh_status set lease_expires_at=clock_timestamp(),last_success_at=clock_timestamp() where dataset_key=p_dataset_key;
  perform set_config('quant.market_publish','off',true);
  return true;
end;
$$;
