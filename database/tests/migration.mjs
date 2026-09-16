// Runs the actual migration in embedded PostgreSQL. Auth/Storage are minimal
// harness schemas, so this supplements (never substitutes for) Supabase API tests.
import { PGlite } from '@electric-sql/pglite';
import { readFile, readdir } from 'node:fs/promises';
import assert from 'node:assert/strict';

const db = await PGlite.create();
let checks = 0;
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const C = '33333333-3333-4333-8333-333333333333';
const role = async (name, id='') => {
  await db.exec('reset role');
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[id]);
  await db.exec(`set role ${name}`); // Only fixed test constants, never external input.
};
const command = async (action, id=null, name=null, positions=null, revision=null, key=null) =>
  (await db.query('select public.portfolio_command($1,$2,$3,$4,$5,$6) result',
  [action,id,name,positions===null?null:JSON.stringify(positions),revision,key])).rows[0].result;
const rejects = async (operation, code) => {
  await assert.rejects(operation, e=>e.code===code); checks++;
};
try {
  await db.exec(`
    create role anon nologin; create role authenticated nologin;
    create role service_role nologin bypassrls; create role supabase_auth_admin nologin;
    create schema auth; create schema storage;
    create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql stable as
      $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    grant usage on schema auth to authenticated, anon, service_role;
    grant execute on function auth.uid() to authenticated, anon, service_role;
    create table storage.buckets(id text primary key,name text not null,public boolean not null);
  `);
  const root = new URL('../../supabase/migrations/',import.meta.url);
  const migrations = (await readdir(root)).filter(f=>f.endsWith('.sql')).sort();
  for (const file of migrations) {
    await db.exec(await readFile(new URL(file,root),'utf8'));
    if (file === '20260916144520_core_foundation.sql') {
      // Simulate a pointer written before the version-retention upgrade.
      const old = {format_version:1,kind:'value',bucket:'market-data',object_key:'equities/preexisting/v1.json',
        object_version:'preexisting-v1',checksum_sha256:'a'.repeat(64),content_type:'application/json',
        source:'fixture',observed_at:'2026-09-16',retrieved_at:'2026-09-16T00:00:00Z',
        coverage_start:null,coverage_end:null,row_count:null,quality_json:{status:'fresh'}};
      await db.query('insert into public.market_data_metadata(dataset_key,record,lease_fence) values($1,$2,$3)',
        ['preexisting',JSON.stringify(old),1]);
    }
  }
  checks++;
  assert.equal((await db.query("select object_version from public.market_data_versions where dataset_key='preexisting'")).rows[0].object_version,'preexisting-v1'); checks++;
  await db.query('insert into auth.users values($1),($2),($3)',[A,B,C]);
  await db.query('insert into public.app_members(user_id,active) values($1,true),($2,true),($3,false)',[A,B,C]);
  await role('authenticated',A);
  const positions = [{symbol:'MSFT',weight_bps:4500}];
  const first = await command('create',null,'Draft',positions,null,'once');
  assert.equal(first.revision,1); assert.equal(first.positions[0].weight_bps,4500); checks++;
  assert.deepEqual(await command('create',null,'Draft',positions,null,'once'),first); checks++;
  await rejects(()=>command('create',null,'Different',positions,null,'once'),'PT409');
  await role('authenticated',B);
  assert.deepEqual((await db.query('select * from public.portfolios')).rows,[]); checks++;
  assert.deepEqual((await db.query('select * from public.portfolio_positions')).rows,[]); checks++;
  await rejects(()=>command('get',first.id),'PT404');
  await rejects(()=>command('delete',first.id,null,null,1),'PT404');
  await rejects(()=>db.query("insert into public.portfolio_positions values($1,$2,'AAPL',1,2)",[first.id,B]),'42501');
  await role('authenticated',C);
  await rejects(()=>command('create',null,'No admission',positions),'42501');
  await role('anon');
  await rejects(()=>db.query('select * from public.portfolios'),'42501');
  await rejects(()=>command('list'),'42501');
  await role('authenticated',A);
  await rejects(()=>command(null,null,'Invalid',positions),'PT422');
  await rejects(()=>command('create',null,'Invalid',[{symbol:'MSFT',weight_bps:1,unused:'oversized'}]),'PT422');
  await rejects(()=>db.query("update public.portfolios set name='Bypass' where id=$1",[first.id]),'42501');
  await rejects(()=>command('create',null,'Non-equity',[{symbol:'BTC-USD',weight_bps:10000}]),'PT422');
  const second = await command('update',first.id,'Updated',positions,1);
  assert.equal(second.revision,2); checks++;
  await rejects(()=>command('update',first.id,'Stale',positions,1),'PT409');
  await rejects(()=>command('delete',first.id,null,null,1),'PT409');
  await rejects(()=>command('update',first.id,'Invalid',[...positions,...positions],2),'PT422');
  assert.equal((await command('get',first.id)).name,'Updated'); checks++;
  await role('postgres');
  await db.query('update public.app_members set active=false where user_id=$1',[A]);
  await role('authenticated',A);
  assert.deepEqual((await db.query('select * from public.portfolios')).rows,[]); checks++;
  await rejects(()=>command('get',first.id),'42501');
  await role('service_role');
  await rejects(()=>db.query('update public.app_members set active=true'),'42501');
  await rejects(()=>db.query("update public.instrument_universe set active=false where symbol='MSFT'"),'42501');
  await rejects(()=>command('list'),'42501');
  await rejects(()=>db.query('select * from public.portfolios'),'42501');
  const claim = async key=> (await db.query('select public.claim_market_refresh_lease($1,60) v',[key])).rows[0].v;
  const lease = await claim('test'); assert.ok(lease.lease_token); checks++;
  assert.equal(await claim('test'),null); checks++;
  const record = {format_version:1,bucket:'market-data',object_version:'v1',checksum_sha256:'a'.repeat(64)};
  const publish = async (key,fence,token,value)=> (await db.query('select public.publish_market_dataset($1,$2,$3,$4) v',[key,fence,token,JSON.stringify(value)])).rows[0].v;
  assert.equal(await publish('test',lease.lease_fence+1,lease.lease_token,record),false); checks++;
  assert.equal(await publish('test',lease.lease_fence,lease.lease_token,record),true); checks++;
  assert.equal(await publish('test',lease.lease_fence,lease.lease_token,record),false); checks++;
  await rejects(()=>db.query("update public.market_data_metadata set record='{}'"),'42501');
  await rejects(()=>db.query("insert into public.market_data_versions(dataset_key,object_version,record,lease_fence) values('test','fake','{}',999)"),'42501');
  const lease2 = await claim('test');
  assert.equal(await publish('test',lease2.lease_fence,lease2.lease_token,{...record,object_version:'v2'}),true); checks++;
  assert.equal((await db.query("select count(*)::int n from public.market_data_versions where dataset_key='test'")).rows[0].n,2); checks++;
  const reuseLease = await claim('test');
  await rejects(()=>publish('test',reuseLease.lease_fence,reuseLease.lease_token,{...record,object_version:'v2'}),'23505');
  assert.equal((await db.query("select record->>'object_version' v from public.market_data_metadata where dataset_key='test'")).rows[0].v,'v2'); checks++;
  const malformedLease = await claim('malformed');
  await rejects(()=>publish('malformed',malformedLease.lease_fence,malformedLease.lease_token,{checksum_sha256:'a'.repeat(64)}),'22023');
  const constituents = (await db.query('select symbol,name,sector from public.instrument_universe order by symbol limit 400')).rows;
  const universeLease = await claim('universe:sp500');
  const universeRecord = {...record,kind:'universe',constituents};
  assert.equal(await publish('universe:sp500',universeLease.lease_fence,universeLease.lease_token,universeRecord),true); checks++;
  assert.equal((await db.query('select count(*)::int n from public.instrument_universe where active')).rows[0].n,400); checks++;
  const nextUniverseLease = await claim('universe:sp500');
  await rejects(()=>publish('universe:sp500',nextUniverseLease.lease_fence,nextUniverseLease.lease_token,{...universeRecord,constituents:constituents.slice(0,399)}),'22023');
  assert.equal((await db.query('select count(*)::int n from public.instrument_universe where active')).rows[0].n,400); checks++;
  await role('postgres');
  await db.exec('grant usage on schema auth to supabase_auth_admin; grant select, delete on auth.users to supabase_auth_admin');
  await role('supabase_auth_admin');
  await db.query('delete from auth.users where id=$1',[A]);
  await role('postgres');
  assert.equal((await db.query('select count(*)::int n from public.portfolios')).rows[0].n,0); checks++;
  console.log(`${checks} embedded PostgreSQL migration/ownership/atomicity/fencing checks passed. Supabase Data API tests remain separate.`);
} finally {
  await db.close();
}
