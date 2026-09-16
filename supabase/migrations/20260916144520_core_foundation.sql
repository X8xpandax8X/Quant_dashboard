-- Private team foundation. All user paths are SECURITY INVOKER and exercise RLS.
create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated;

create table public.app_members (
  user_id uuid primary key references auth.users(id) on delete cascade,
  active boolean not null default false,
  admitted_at timestamptz not null default now()
);
alter table public.app_members enable row level security;
revoke all on public.app_members from anon, authenticated;
grant select on public.app_members to authenticated;
revoke all on public.app_members from service_role;
-- Admission is an operator SQL operation, separate from market service credentials.
create policy membership_read on public.app_members for select to authenticated
  using (user_id = (select auth.uid()));

create function private.is_member() returns boolean language sql stable security invoker
set search_path = '' as $$
  select exists(select 1 from public.app_members where user_id = (select auth.uid()) and active);
$$;
revoke all on function private.is_member() from public;
grant execute on function private.is_member() to authenticated;

create table public.portfolios (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check(length(btrim(name)) between 1 and 100),
  base_currency text not null default 'USD' check(base_currency ~ '^[A-Z]{3}$'),
  revision integer not null default 1 check(revision > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(id, owner_id)
);
create index portfolios_owner_updated on public.portfolios(owner_id, updated_at desc);
create table public.portfolio_positions (
  portfolio_id uuid not null,
  owner_id uuid not null default auth.uid(),
  symbol text not null check(symbol ~ '^[A-Z0-9.^=-]{1,20}$'),
  weight_bps integer not null check(weight_bps between 0 and 10000),
  ordinal integer not null check(ordinal between 1 and 30),
  primary key(portfolio_id, symbol),
  unique(portfolio_id, ordinal),
  foreign key(portfolio_id, owner_id) references public.portfolios(id, owner_id) on delete cascade
);
create index portfolio_positions_owner on public.portfolio_positions(owner_id);
create table public.portfolio_write_requests (
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  request_key text not null check(length(request_key) between 1 and 128),
  request_payload jsonb not null,
  result jsonb not null,
  created_at timestamptz not null default now(),
  primary key(owner_id, request_key)
);

-- Invoker RPCs need table privileges. A trigger rejects direct Data API writes
-- that skip the atomic revision/positions transaction. private is not API-exposed;
-- no set_config/SQL execution RPC is granted or exposed by this application.
create function private.portfolio_write_guard() returns trigger language plpgsql security invoker
set search_path = '' as $$
begin
  -- Auth user deletion must be able to enforce the declared ON DELETE CASCADE.
  -- The authenticated user path still needs the atomic RPC; service_role is revoked.
  if current_user not in ('postgres', 'supabase_auth_admin')
    and coalesce(current_setting('quant.portfolio_write', true), '') <> 'on' then
    raise exception using errcode = '42501', message = 'Use the portfolio command';
  end if;
  if tg_op = 'UPDATE' and new.owner_id <> old.owner_id then
    raise exception using errcode = '42501', message = 'Owner is immutable';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
revoke all on function private.portfolio_write_guard() from public;

do $$
declare t text;
begin
  foreach t in array array['portfolios','portfolio_positions','portfolio_write_requests'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
    execute format('create policy owner_access on public.%I to authenticated using (owner_id = (select auth.uid()) and (select private.is_member())) with check (owner_id = (select auth.uid()) and (select private.is_member()))', t);
    execute format('create trigger guarded_write before insert or update or delete on public.%I for each row execute function private.portfolio_write_guard()', t);
  end loop;
end $$;
revoke all on public.portfolios, public.portfolio_positions, public.portfolio_write_requests from service_role;

-- Dated, provenance-backed initial universe; refreshed atomically with its artifact.
create table public.instrument_universe (
  symbol text primary key check(symbol ~ '^[A-Z0-9.^=-]{1,20}$'),
  name text not null, sector text, active boolean not null default true,
  updated_at timestamptz not null default now()
);
alter table public.instrument_universe enable row level security;
revoke all on public.instrument_universe from anon, authenticated;
grant select on public.instrument_universe to authenticated;
revoke all on public.instrument_universe from service_role;
grant select, insert, update on public.instrument_universe to service_role;
create policy team_universe_read on public.instrument_universe for select to authenticated
  using ((select private.is_member()));
-- Source: shipped sp500_snapshot_2026-09-15.json, Wikipedia constituent table.
insert into public.instrument_universe(symbol,name,sector)
select symbol,name,sector from jsonb_to_recordset($snapshot$[{"symbol":"MMM","name":"3M","sector":"Industrials"},{"symbol":"AOS","name":"A. O. Smith","sector":"Industrials"},{"symbol":"ABT","name":"Abbott Laboratories","sector":"Health Care"},{"symbol":"ABBV","name":"AbbVie","sector":"Health Care"},{"symbol":"ACN","name":"Accenture","sector":"Information Technology"},{"symbol":"ADBE","name":"Adobe Inc.","sector":"Information Technology"},{"symbol":"AMD","name":"Advanced Micro Devices","sector":"Information Technology"},{"symbol":"AES","name":"AES Corporation","sector":"Utilities"},{"symbol":"AFL","name":"Aflac","sector":"Financials"},{"symbol":"A","name":"Agilent Technologies","sector":"Health Care"},{"symbol":"APD","name":"Air Products","sector":"Materials"},{"symbol":"ABNB","name":"Airbnb","sector":"Consumer Discretionary"},{"symbol":"AKAM","name":"Akamai Technologies","sector":"Information Technology"},{"symbol":"ALB","name":"Albemarle Corporation","sector":"Materials"},{"symbol":"ARE","name":"Alexandria Real Estate Equities","sector":"Real Estate"},{"symbol":"ALGN","name":"Align Technology","sector":"Health Care"},{"symbol":"ALLE","name":"Allegion","sector":"Industrials"},{"symbol":"LNT","name":"Alliant Energy","sector":"Utilities"},{"symbol":"ALL","name":"Allstate","sector":"Financials"},{"symbol":"GOOGL","name":"Alphabet Inc. (Class A)","sector":"Communication Services"},{"symbol":"GOOG","name":"Alphabet Inc. (Class C)","sector":"Communication Services"},{"symbol":"MO","name":"Altria","sector":"Consumer Staples"},{"symbol":"AMZN","name":"Amazon","sector":"Consumer Discretionary"},{"symbol":"AMCR","name":"Amcor","sector":"Materials"},{"symbol":"AEE","name":"Ameren","sector":"Utilities"},{"symbol":"AEP","name":"American Electric Power","sector":"Utilities"},{"symbol":"AXP","name":"American Express","sector":"Financials"},{"symbol":"AIG","name":"American International Group","sector":"Financials"},{"symbol":"AMT","name":"American Tower","sector":"Real Estate"},{"symbol":"AWK","name":"American Water Works","sector":"Utilities"},{"symbol":"AMP","name":"Ameriprise Financial","sector":"Financials"},{"symbol":"AME","name":"Ametek","sector":"Industrials"},{"symbol":"AMGN","name":"Amgen","sector":"Health Care"},{"symbol":"APH","name":"Amphenol","sector":"Information Technology"},{"symbol":"ADI","name":"Analog Devices","sector":"Information Technology"},{"symbol":"AON","name":"Aon plc","sector":"Financials"},{"symbol":"APA","name":"APA Corporation","sector":"Energy"},{"symbol":"APO","name":"Apollo Global Management","sector":"Financials"},{"symbol":"AAPL","name":"Apple Inc.","sector":"Information Technology"},{"symbol":"AMAT","name":"Applied Materials","sector":"Information Technology"},{"symbol":"APP","name":"AppLovin","sector":"Communication Services"},{"symbol":"APTV","name":"Aptiv","sector":"Consumer Discretionary"},{"symbol":"ACGL","name":"Arch Capital Group","sector":"Financials"},{"symbol":"ADM","name":"Archer Daniels Midland","sector":"Consumer Staples"},{"symbol":"ARES","name":"Ares Management","sector":"Financials"},{"symbol":"ANET","name":"Arista Networks","sector":"Information Technology"},{"symbol":"AJG","name":"Arthur J. Gallagher & Co.","sector":"Financials"},{"symbol":"AIZ","name":"Assurant","sector":"Financials"},{"symbol":"T","name":"AT&T","sector":"Communication Services"},{"symbol":"ATO","name":"Atmos Energy","sector":"Utilities"},{"symbol":"ADSK","name":"Autodesk","sector":"Information Technology"},{"symbol":"ADP","name":"Automatic Data Processing","sector":"Industrials"},{"symbol":"AZO","name":"AutoZone","sector":"Consumer Discretionary"},{"symbol":"AVY","name":"Avery Dennison","sector":"Materials"},{"symbol":"AXON","name":"Axon Enterprise","sector":"Industrials"},{"symbol":"BKR","name":"Baker Hughes","sector":"Energy"},{"symbol":"BALL","name":"Ball Corporation","sector":"Materials"},{"symbol":"BAC","name":"Bank of America","sector":"Financials"},{"symbol":"BAX","name":"Baxter International","sector":"Health Care"},{"symbol":"BDX","name":"Becton Dickinson","sector":"Health Care"},{"symbol":"BRK-B","name":"Berkshire Hathaway","sector":"Financials"},{"symbol":"BBY","name":"Best Buy","sector":"Consumer Discretionary"},{"symbol":"TECH","name":"Bio-Techne","sector":"Health Care"},{"symbol":"BIIB","name":"Biogen","sector":"Health Care"},{"symbol":"BLK","name":"BlackRock","sector":"Financials"},{"symbol":"BX","name":"Blackstone Inc.","sector":"Financials"},{"symbol":"XYZ","name":"Block, Inc.","sector":"Financials"},{"symbol":"BNY","name":"BNY Mellon","sector":"Financials"},{"symbol":"BA","name":"Boeing","sector":"Industrials"},{"symbol":"BKNG","name":"Booking Holdings","sector":"Consumer Discretionary"},{"symbol":"BSX","name":"Boston Scientific","sector":"Health Care"},{"symbol":"BMY","name":"Bristol Myers Squibb","sector":"Health Care"},{"symbol":"AVGO","name":"Broadcom","sector":"Information Technology"},{"symbol":"BR","name":"Broadridge Financial Solutions","sector":"Industrials"},{"symbol":"BRO","name":"Brown & Brown","sector":"Financials"},{"symbol":"BF-B","name":"Brown\u2013Forman","sector":"Consumer Staples"},{"symbol":"BLDR","name":"Builders FirstSource","sector":"Industrials"},{"symbol":"BG","name":"Bunge Global","sector":"Consumer Staples"},{"symbol":"BXP","name":"BXP, Inc.","sector":"Real Estate"},{"symbol":"CHRW","name":"C.H. Robinson","sector":"Industrials"},{"symbol":"CDNS","name":"Cadence Design Systems","sector":"Information Technology"},{"symbol":"CPT","name":"Camden Property Trust","sector":"Real Estate"},{"symbol":"COF","name":"Capital One","sector":"Financials"},{"symbol":"CAH","name":"Cardinal Health","sector":"Health Care"},{"symbol":"CCL","name":"Carnival Corporation","sector":"Consumer Discretionary"},{"symbol":"CARR","name":"Carrier Global","sector":"Industrials"},{"symbol":"CVNA","name":"Carvana","sector":"Consumer Discretionary"},{"symbol":"CASY","name":"Casey's","sector":"Consumer Staples"},{"symbol":"CAT","name":"Caterpillar Inc.","sector":"Industrials"},{"symbol":"CBOE","name":"Cboe Global Markets","sector":"Financials"},{"symbol":"CBRE","name":"CBRE Group","sector":"Real Estate"},{"symbol":"CDW","name":"CDW Corporation","sector":"Information Technology"},{"symbol":"COR","name":"Cencora","sector":"Health Care"},{"symbol":"CNC","name":"Centene Corporation","sector":"Health Care"},{"symbol":"CNP","name":"CenterPoint Energy","sector":"Utilities"},{"symbol":"CF","name":"CF Industries","sector":"Materials"},{"symbol":"CRL","name":"Charles River Laboratories","sector":"Health Care"},{"symbol":"SCHW","name":"Charles Schwab Corporation","sector":"Financials"},{"symbol":"CHTR","name":"Charter Communications","sector":"Communication Services"},{"symbol":"CVX","name":"Chevron Corporation","sector":"Energy"},{"symbol":"CMG","name":"Chipotle Mexican Grill","sector":"Consumer Discretionary"},{"symbol":"CB","name":"Chubb Limited","sector":"Financials"},{"symbol":"CHD","name":"Church & Dwight","sector":"Consumer Staples"},{"symbol":"CIEN","name":"Ciena","sector":"Information Technology"},{"symbol":"CI","name":"Cigna","sector":"Health Care"},{"symbol":"CINF","name":"Cincinnati Financial","sector":"Financials"},{"symbol":"CTAS","name":"Cintas","sector":"Industrials"},{"symbol":"CSCO","name":"Cisco","sector":"Information Technology"},{"symbol":"C","name":"Citigroup","sector":"Financials"},{"symbol":"CFG","name":"Citizens Financial Group","sector":"Financials"},{"symbol":"CLX","name":"Clorox","sector":"Consumer Staples"},{"symbol":"CME","name":"CME Group","sector":"Financials"},{"symbol":"CMS","name":"CMS Energy","sector":"Utilities"},{"symbol":"KO","name":"Coca-Cola Company (The)","sector":"Consumer Staples"},{"symbol":"CTSH","name":"Cognizant","sector":"Information Technology"},{"symbol":"COHR","name":"Coherent Corp.","sector":"Information Technology"},{"symbol":"COIN","name":"Coinbase","sector":"Financials"},{"symbol":"CL","name":"Colgate-Palmolive","sector":"Consumer Staples"},{"symbol":"CMCSA","name":"Comcast","sector":"Communication Services"},{"symbol":"FIX","name":"Comfort Systems USA","sector":"Industrials"},{"symbol":"COP","name":"ConocoPhillips","sector":"Energy"},{"symbol":"ED","name":"Consolidated Edison","sector":"Utilities"},{"symbol":"STZ","name":"Constellation Brands","sector":"Consumer Staples"},{"symbol":"CEG","name":"Constellation Energy","sector":"Utilities"},{"symbol":"COO","name":"Cooper Companies (The)","sector":"Health Care"},{"symbol":"CPRT","name":"Copart","sector":"Industrials"},{"symbol":"GLW","name":"Corning Inc.","sector":"Information Technology"},{"symbol":"CPAY","name":"Corpay","sector":"Financials"},{"symbol":"CTVA","name":"Corteva","sector":"Materials"},{"symbol":"CSGP","name":"CoStar Group","sector":"Real Estate"},{"symbol":"COST","name":"Costco","sector":"Consumer Staples"},{"symbol":"CRH","name":"CRH plc","sector":"Materials"},{"symbol":"CRWD","name":"CrowdStrike","sector":"Information Technology"},{"symbol":"CCI","name":"Crown Castle","sector":"Real Estate"},{"symbol":"CSX","name":"CSX Corporation","sector":"Industrials"},{"symbol":"CMI","name":"Cummins","sector":"Industrials"},{"symbol":"CVS","name":"CVS Health","sector":"Health Care"},{"symbol":"DHR","name":"Danaher Corporation","sector":"Health Care"},{"symbol":"DRI","name":"Darden Restaurants","sector":"Consumer Discretionary"},{"symbol":"DDOG","name":"Datadog","sector":"Information Technology"},{"symbol":"DVA","name":"DaVita","sector":"Health Care"},{"symbol":"DECK","name":"Deckers Brands","sector":"Consumer Discretionary"},{"symbol":"DE","name":"Deere & Company","sector":"Industrials"},{"symbol":"DELL","name":"Dell Technologies","sector":"Information Technology"},{"symbol":"DAL","name":"Delta Air Lines","sector":"Industrials"},{"symbol":"DVN","name":"Devon Energy","sector":"Energy"},{"symbol":"DXCM","name":"Dexcom","sector":"Health Care"},{"symbol":"FANG","name":"Diamondback Energy","sector":"Energy"},{"symbol":"DLR","name":"Digital Realty","sector":"Real Estate"},{"symbol":"DG","name":"Dollar General","sector":"Consumer Staples"},{"symbol":"DLTR","name":"Dollar Tree","sector":"Consumer Staples"},{"symbol":"D","name":"Dominion Energy","sector":"Utilities"},{"symbol":"DPZ","name":"Domino's","sector":"Consumer Discretionary"},{"symbol":"DASH","name":"DoorDash","sector":"Consumer Discretionary"},{"symbol":"DOV","name":"Dover Corporation","sector":"Industrials"},{"symbol":"DOW","name":"Dow Inc.","sector":"Materials"},{"symbol":"DHI","name":"D. R. Horton","sector":"Consumer Discretionary"},{"symbol":"DTE","name":"DTE Energy","sector":"Utilities"},{"symbol":"DUK","name":"Duke Energy","sector":"Utilities"},{"symbol":"DD","name":"DuPont","sector":"Industrials"},{"symbol":"ETN","name":"Eaton Corporation","sector":"Industrials"},{"symbol":"EBAY","name":"eBay Inc.","sector":"Consumer Discretionary"},{"symbol":"ECHO","name":"EchoStar","sector":"Communication Services"},{"symbol":"ECL","name":"Ecolab","sector":"Materials"},{"symbol":"EIX","name":"Edison International","sector":"Utilities"},{"symbol":"EW","name":"Edwards Lifesciences","sector":"Health Care"},{"symbol":"ELV","name":"Elevance Health","sector":"Health Care"},{"symbol":"EME","name":"Emcor","sector":"Industrials"},{"symbol":"EMR","name":"Emerson Electric","sector":"Industrials"},{"symbol":"ETR","name":"Entergy","sector":"Utilities"},{"symbol":"EOG","name":"EOG Resources","sector":"Energy"},{"symbol":"EQT","name":"EQT Corporation","sector":"Energy"},{"symbol":"EFX","name":"Equifax","sector":"Industrials"},{"symbol":"EQIX","name":"Equinix","sector":"Real Estate"},{"symbol":"ERIE","name":"Erie Indemnity","sector":"Financials"},{"symbol":"ESS","name":"Essex Property Trust","sector":"Real Estate"},{"symbol":"EL","name":"Est\u00e9e Lauder Companies (The)","sector":"Consumer Staples"},{"symbol":"EG","name":"Everest Group","sector":"Financials"},{"symbol":"EVRG","name":"Evergy","sector":"Utilities"},{"symbol":"ES","name":"Eversource Energy","sector":"Utilities"},{"symbol":"EXC","name":"Exelon","sector":"Utilities"},{"symbol":"EXE","name":"Expand Energy","sector":"Energy"},{"symbol":"EXPE","name":"Expedia Group","sector":"Consumer Discretionary"},{"symbol":"EXPD","name":"Expeditors International","sector":"Industrials"},{"symbol":"EXR","name":"Extra Space Storage","sector":"Real Estate"},{"symbol":"XOM","name":"ExxonMobil","sector":"Energy"},{"symbol":"FFIV","name":"F5, Inc.","sector":"Information Technology"},{"symbol":"FDS","name":"FactSet","sector":"Financials"},{"symbol":"FICO","name":"Fair Isaac","sector":"Information Technology"},{"symbol":"FAST","name":"Fastenal","sector":"Industrials"},{"symbol":"FRT","name":"Federal Realty Investment Trust","sector":"Real Estate"},{"symbol":"FDX","name":"FedEx","sector":"Industrials"},{"symbol":"FDXF","name":"FedEx Freight","sector":"Industrials"},{"symbol":"FERG","name":"Ferguson Enterprises","sector":"Industrials"},{"symbol":"FIS","name":"Fidelity National Information Services","sector":"Financials"},{"symbol":"FITB","name":"Fifth Third Bancorp","sector":"Financials"},{"symbol":"FSLR","name":"First Solar","sector":"Information Technology"},{"symbol":"FE","name":"FirstEnergy","sector":"Utilities"},{"symbol":"FISV","name":"Fiserv","sector":"Financials"},{"symbol":"FLEX","name":"Flex Ltd.","sector":"Information Technology"},{"symbol":"F","name":"Ford Motor Company","sector":"Consumer Discretionary"},{"symbol":"FTNT","name":"Fortinet","sector":"Information Technology"},{"symbol":"FTV","name":"Fortive","sector":"Industrials"},{"symbol":"FOXA","name":"Fox Corporation (Class A)","sector":"Communication Services"},{"symbol":"FOX","name":"Fox Corporation (Class B)","sector":"Communication Services"},{"symbol":"BEN","name":"Franklin Resources","sector":"Financials"},{"symbol":"FCX","name":"Freeport-McMoRan","sector":"Materials"},{"symbol":"GRMN","name":"Garmin","sector":"Consumer Discretionary"},{"symbol":"IT","name":"Gartner","sector":"Information Technology"},{"symbol":"GE","name":"GE Aerospace","sector":"Industrials"},{"symbol":"GEHC","name":"GE HealthCare","sector":"Health Care"},{"symbol":"GEV","name":"GE Vernova","sector":"Industrials"},{"symbol":"GEN","name":"Gen Digital","sector":"Information Technology"},{"symbol":"GNRC","name":"Generac","sector":"Industrials"},{"symbol":"GD","name":"General Dynamics","sector":"Industrials"},{"symbol":"GIS","name":"General Mills","sector":"Consumer Staples"},{"symbol":"GM","name":"General Motors","sector":"Consumer Discretionary"},{"symbol":"GPC","name":"Genuine Parts Company","sector":"Consumer Discretionary"},{"symbol":"GILD","name":"Gilead Sciences","sector":"Health Care"},{"symbol":"GPN","name":"Global Payments","sector":"Financials"},{"symbol":"GL","name":"Globe Life","sector":"Financials"},{"symbol":"GDDY","name":"GoDaddy","sector":"Information Technology"},{"symbol":"GS","name":"Goldman Sachs","sector":"Financials"},{"symbol":"HAL","name":"Halliburton","sector":"Energy"},{"symbol":"HIG","name":"Hartford (The)","sector":"Financials"},{"symbol":"HAS","name":"Hasbro","sector":"Consumer Discretionary"},{"symbol":"HCA","name":"HCA Healthcare","sector":"Health Care"},{"symbol":"DOC","name":"Healthpeak Properties","sector":"Real Estate"},{"symbol":"HSIC","name":"Henry Schein","sector":"Health Care"},{"symbol":"HSY","name":"Hershey Company (The)","sector":"Consumer Staples"},{"symbol":"HPE","name":"Hewlett Packard Enterprise","sector":"Information Technology"},{"symbol":"HLT","name":"Hilton Worldwide","sector":"Consumer Discretionary"},{"symbol":"HD","name":"Home Depot (The)","sector":"Consumer Discretionary"},{"symbol":"HONA","name":"Honeywell Aerospace","sector":"Industrials"},{"symbol":"HON","name":"Honeywell Technologies","sector":"Industrials"},{"symbol":"HRL","name":"Hormel Foods","sector":"Consumer Staples"},{"symbol":"HST","name":"Host Hotels & Resorts","sector":"Real Estate"},{"symbol":"HWM","name":"Howmet Aerospace","sector":"Industrials"},{"symbol":"HPQ","name":"HP Inc.","sector":"Information Technology"},{"symbol":"HUBB","name":"Hubbell Incorporated","sector":"Industrials"},{"symbol":"HUM","name":"Humana","sector":"Health Care"},{"symbol":"HBAN","name":"Huntington Bancshares","sector":"Financials"},{"symbol":"HII","name":"Huntington Ingalls Industries","sector":"Industrials"},{"symbol":"IBM","name":"IBM","sector":"Information Technology"},{"symbol":"IEX","name":"IDEX Corporation","sector":"Industrials"},{"symbol":"IDXX","name":"Idexx Laboratories","sector":"Health Care"},{"symbol":"ITW","name":"Illinois Tool Works","sector":"Industrials"},{"symbol":"INCY","name":"Incyte","sector":"Health Care"},{"symbol":"IR","name":"Ingersoll Rand","sector":"Industrials"},{"symbol":"PODD","name":"Insulet Corporation","sector":"Health Care"},{"symbol":"INTC","name":"Intel","sector":"Information Technology"},{"symbol":"IBKR","name":"Interactive Brokers","sector":"Financials"},{"symbol":"ICE","name":"Intercontinental Exchange","sector":"Financials"},{"symbol":"IFF","name":"International Flavors & Fragrances","sector":"Materials"},{"symbol":"IP","name":"International Paper","sector":"Materials"},{"symbol":"INTU","name":"Intuit","sector":"Information Technology"},{"symbol":"ISRG","name":"Intuitive Surgical","sector":"Health Care"},{"symbol":"IVZ","name":"Invesco","sector":"Financials"},{"symbol":"INVH","name":"Invitation Homes","sector":"Real Estate"},{"symbol":"IQV","name":"IQVIA","sector":"Health Care"},{"symbol":"IRM","name":"Iron Mountain","sector":"Real Estate"},{"symbol":"JBHT","name":"J.B. Hunt","sector":"Industrials"},{"symbol":"JBL","name":"Jabil","sector":"Information Technology"},{"symbol":"JKHY","name":"Jack Henry & Associates","sector":"Financials"},{"symbol":"J","name":"Jacobs Solutions","sector":"Industrials"},{"symbol":"JNJ","name":"Johnson & Johnson","sector":"Health Care"},{"symbol":"JCI","name":"Johnson Controls","sector":"Industrials"},{"symbol":"JPM","name":"JPMorgan Chase","sector":"Financials"},{"symbol":"KVUE","name":"Kenvue","sector":"Consumer Staples"},{"symbol":"KDP","name":"Keurig Dr Pepper","sector":"Consumer Staples"},{"symbol":"KEY","name":"KeyCorp","sector":"Financials"},{"symbol":"KEYS","name":"Keysight Technologies","sector":"Information Technology"},{"symbol":"KMB","name":"Kimberly-Clark","sector":"Consumer Staples"},{"symbol":"KIM","name":"Kimco Realty","sector":"Real Estate"},{"symbol":"KMI","name":"Kinder Morgan","sector":"Energy"},{"symbol":"KKR","name":"KKR & Co.","sector":"Financials"},{"symbol":"KLAC","name":"KLA Corporation","sector":"Information Technology"},{"symbol":"KHC","name":"Kraft Heinz","sector":"Consumer Staples"},{"symbol":"KR","name":"Kroger","sector":"Consumer Staples"},{"symbol":"LHX","name":"L3Harris","sector":"Industrials"},{"symbol":"LH","name":"Labcorp","sector":"Health Care"},{"symbol":"LRCX","name":"Lam Research","sector":"Information Technology"},{"symbol":"LVS","name":"Las Vegas Sands","sector":"Consumer Discretionary"},{"symbol":"LDOS","name":"Leidos","sector":"Industrials"},{"symbol":"LEN","name":"Lennar","sector":"Consumer Discretionary"},{"symbol":"LII","name":"Lennox International","sector":"Industrials"},{"symbol":"LLY","name":"Lilly (Eli)","sector":"Health Care"},{"symbol":"LIN","name":"Linde plc","sector":"Materials"},{"symbol":"LYV","name":"Live Nation Entertainment","sector":"Communication Services"},{"symbol":"LMT","name":"Lockheed Martin","sector":"Industrials"},{"symbol":"L","name":"Loews Corporation","sector":"Financials"},{"symbol":"LOW","name":"Lowe's","sector":"Consumer Discretionary"},{"symbol":"LULU","name":"Lululemon Athletica","sector":"Consumer Discretionary"},{"symbol":"LITE","name":"Lumentum","sector":"Information Technology"},{"symbol":"LYB","name":"LyondellBasell","sector":"Materials"},{"symbol":"MTB","name":"M&T Bank","sector":"Financials"},{"symbol":"MPC","name":"Marathon Petroleum","sector":"Energy"},{"symbol":"MAR","name":"Marriott International","sector":"Consumer Discretionary"},{"symbol":"MRSH","name":"Marsh McLennan","sector":"Financials"},{"symbol":"MLM","name":"Martin Marietta Materials","sector":"Materials"},{"symbol":"MRVL","name":"Marvell Technology","sector":"Information Technology"},{"symbol":"MAS","name":"Masco","sector":"Industrials"},{"symbol":"MA","name":"Mastercard","sector":"Financials"},{"symbol":"MKC","name":"McCormick & Company","sector":"Consumer Staples"},{"symbol":"MCD","name":"McDonald's","sector":"Consumer Discretionary"},{"symbol":"MCK","name":"McKesson Corporation","sector":"Health Care"},{"symbol":"MDT","name":"Medtronic","sector":"Health Care"},{"symbol":"MRK","name":"Merck & Co.","sector":"Health Care"},{"symbol":"META","name":"Meta Platforms","sector":"Communication Services"},{"symbol":"MET","name":"MetLife","sector":"Financials"},{"symbol":"MTD","name":"Mettler Toledo","sector":"Health Care"},{"symbol":"MGM","name":"MGM Resorts","sector":"Consumer Discretionary"},{"symbol":"MCHP","name":"Microchip Technology","sector":"Information Technology"},{"symbol":"MU","name":"Micron Technology","sector":"Information Technology"},{"symbol":"MSFT","name":"Microsoft","sector":"Information Technology"},{"symbol":"MAA","name":"Mid-America Apartment Communities","sector":"Real Estate"},{"symbol":"MRNA","name":"Moderna","sector":"Health Care"},{"symbol":"TAP","name":"Molson Coors Beverage Company","sector":"Consumer Staples"},{"symbol":"MDLZ","name":"Mondelez International","sector":"Consumer Staples"},{"symbol":"MPWR","name":"Monolithic Power Systems","sector":"Information Technology"},{"symbol":"MNST","name":"Monster Beverage","sector":"Consumer Staples"},{"symbol":"MCO","name":"Moody's Corporation","sector":"Financials"},{"symbol":"MS","name":"Morgan Stanley","sector":"Financials"},{"symbol":"MOS","name":"Mosaic Company (The)","sector":"Materials"},{"symbol":"MSI","name":"Motorola Solutions","sector":"Information Technology"},{"symbol":"MSCI","name":"MSCI","sector":"Financials"},{"symbol":"NDAQ","name":"Nasdaq, Inc.","sector":"Financials"},{"symbol":"NTAP","name":"NetApp","sector":"Information Technology"},{"symbol":"NFLX","name":"Netflix","sector":"Communication Services"},{"symbol":"NEM","name":"Newmont","sector":"Materials"},{"symbol":"NWSA","name":"News Corp (Class A)","sector":"Communication Services"},{"symbol":"NWS","name":"News Corp (Class B)","sector":"Communication Services"},{"symbol":"NEE","name":"NextEra Energy","sector":"Utilities"},{"symbol":"NKE","name":"Nike, Inc.","sector":"Consumer Discretionary"},{"symbol":"NI","name":"NiSource","sector":"Utilities"},{"symbol":"NDSN","name":"Nordson Corporation","sector":"Industrials"},{"symbol":"NSC","name":"Norfolk Southern","sector":"Industrials"},{"symbol":"NTRS","name":"Northern Trust","sector":"Financials"},{"symbol":"NOC","name":"Northrop Grumman","sector":"Industrials"},{"symbol":"NCLH","name":"Norwegian Cruise Line Holdings","sector":"Consumer Discretionary"},{"symbol":"NRG","name":"NRG Energy","sector":"Utilities"},{"symbol":"NUE","name":"Nucor","sector":"Materials"},{"symbol":"NVDA","name":"Nvidia","sector":"Information Technology"},{"symbol":"NVR","name":"NVR, Inc.","sector":"Consumer Discretionary"},{"symbol":"NXPI","name":"NXP Semiconductors","sector":"Information Technology"},{"symbol":"ORLY","name":"O'Reilly Automotive","sector":"Consumer Discretionary"},{"symbol":"OXY","name":"Occidental Petroleum","sector":"Energy"},{"symbol":"ODFL","name":"Old Dominion","sector":"Industrials"},{"symbol":"OMC","name":"Omnicom Group","sector":"Communication Services"},{"symbol":"ON","name":"ON Semiconductor","sector":"Information Technology"},{"symbol":"OKE","name":"Oneok","sector":"Energy"},{"symbol":"ORCL","name":"Oracle Corporation","sector":"Information Technology"},{"symbol":"OTIS","name":"Otis Worldwide","sector":"Industrials"},{"symbol":"PCAR","name":"Paccar","sector":"Industrials"},{"symbol":"PKG","name":"Packaging Corporation of America","sector":"Materials"},{"symbol":"PLTR","name":"Palantir Technologies","sector":"Information Technology"},{"symbol":"PANW","name":"Palo Alto Networks","sector":"Information Technology"},{"symbol":"PSKY","name":"Paramount Skydance Corporation","sector":"Communication Services"},{"symbol":"PH","name":"Parker Hannifin","sector":"Industrials"},{"symbol":"PAYX","name":"Paychex","sector":"Industrials"},{"symbol":"PYPL","name":"PayPal","sector":"Financials"},{"symbol":"PNR","name":"Pentair","sector":"Industrials"},{"symbol":"PEP","name":"PepsiCo","sector":"Consumer Staples"},{"symbol":"PFE","name":"Pfizer","sector":"Health Care"},{"symbol":"PCG","name":"PG&E Corporation","sector":"Utilities"},{"symbol":"PM","name":"Philip Morris International","sector":"Consumer Staples"},{"symbol":"PSX","name":"Phillips 66","sector":"Energy"},{"symbol":"PNW","name":"Pinnacle West Capital","sector":"Utilities"},{"symbol":"PNC","name":"PNC Financial Services","sector":"Financials"},{"symbol":"PPG","name":"PPG Industries","sector":"Materials"},{"symbol":"PPL","name":"PPL Corporation","sector":"Utilities"},{"symbol":"PFG","name":"Principal Financial Group","sector":"Financials"},{"symbol":"PG","name":"Procter & Gamble","sector":"Consumer Staples"},{"symbol":"PGR","name":"Progressive Corporation","sector":"Financials"},{"symbol":"PLD","name":"Prologis","sector":"Real Estate"},{"symbol":"PRU","name":"Prudential Financial","sector":"Financials"},{"symbol":"PEG","name":"Public Service Enterprise Group","sector":"Utilities"},{"symbol":"PTC","name":"PTC Inc.","sector":"Information Technology"},{"symbol":"PSA","name":"Public Storage","sector":"Real Estate"},{"symbol":"PHM","name":"PulteGroup","sector":"Consumer Discretionary"},{"symbol":"PWR","name":"Quanta Services","sector":"Industrials"},{"symbol":"QCOM","name":"Qualcomm","sector":"Information Technology"},{"symbol":"DGX","name":"Quest Diagnostics","sector":"Health Care"},{"symbol":"Q","name":"Qnity Electronics","sector":"Information Technology"},{"symbol":"RL","name":"Ralph Lauren Corporation","sector":"Consumer Discretionary"},{"symbol":"RJF","name":"Raymond James Financial","sector":"Financials"},{"symbol":"RDDT","name":"Reddit","sector":"Communication Services"},{"symbol":"RTX","name":"RTX Corporation","sector":"Industrials"},{"symbol":"O","name":"Realty Income","sector":"Real Estate"},{"symbol":"REG","name":"Regency Centers","sector":"Real Estate"},{"symbol":"REGN","name":"Regeneron Pharmaceuticals","sector":"Health Care"},{"symbol":"RF","name":"Regions Financial Corporation","sector":"Financials"},{"symbol":"RSG","name":"Republic Services","sector":"Industrials"},{"symbol":"RMD","name":"ResMed|","sector":"Health Care"},{"symbol":"RVTY","name":"Revvity","sector":"Health Care"},{"symbol":"HOOD","name":"Robinhood Markets","sector":"Financials"},{"symbol":"ROK","name":"Rockwell Automation","sector":"Industrials"},{"symbol":"ROL","name":"Rollins, Inc.","sector":"Industrials"},{"symbol":"ROP","name":"Roper Technologies","sector":"Information Technology"},{"symbol":"ROST","name":"Ross Stores","sector":"Consumer Discretionary"},{"symbol":"RCL","name":"Royal Caribbean Group","sector":"Consumer Discretionary"},{"symbol":"SPGI","name":"S&P Global","sector":"Financials"},{"symbol":"CRM","name":"Salesforce","sector":"Information Technology"},{"symbol":"SNDK","name":"Sandisk","sector":"Information Technology"},{"symbol":"SBAC","name":"SBA Communications","sector":"Real Estate"},{"symbol":"SLB","name":"Schlumberger","sector":"Energy"},{"symbol":"STX","name":"Seagate Technology","sector":"Information Technology"},{"symbol":"SRE","name":"Sempra","sector":"Utilities"},{"symbol":"NOW","name":"ServiceNow","sector":"Information Technology"},{"symbol":"SHW","name":"Sherwin-Williams","sector":"Materials"},{"symbol":"SPG","name":"Simon Property Group","sector":"Real Estate"},{"symbol":"SWKS","name":"Skyworks Solutions","sector":"Information Technology"},{"symbol":"SJM","name":"J.M. Smucker Company (The)","sector":"Consumer Staples"},{"symbol":"SW","name":"Smurfit Westrock","sector":"Materials"},{"symbol":"SNA","name":"Snap-on","sector":"Industrials"},{"symbol":"SOLV","name":"Solventum","sector":"Health Care"},{"symbol":"SO","name":"Southern Company","sector":"Utilities"},{"symbol":"LUV","name":"Southwest Airlines","sector":"Industrials"},{"symbol":"SWK","name":"Stanley Black & Decker","sector":"Industrials"},{"symbol":"SBUX","name":"Starbucks","sector":"Consumer Discretionary"},{"symbol":"STT","name":"State Street Corporation","sector":"Financials"},{"symbol":"STLD","name":"Steel Dynamics","sector":"Materials"},{"symbol":"STE","name":"Steris","sector":"Health Care"},{"symbol":"SYK","name":"Stryker Corporation","sector":"Health Care"},{"symbol":"SMCI","name":"Supermicro","sector":"Information Technology"},{"symbol":"SYF","name":"Synchrony Financial","sector":"Financials"},{"symbol":"SNPS","name":"Synopsys","sector":"Information Technology"},{"symbol":"SYY","name":"Sysco","sector":"Consumer Staples"},{"symbol":"TMUS","name":"T-Mobile US","sector":"Communication Services"},{"symbol":"TROW","name":"T. Rowe Price","sector":"Financials"},{"symbol":"TTWO","name":"Take-Two Interactive","sector":"Communication Services"},{"symbol":"TPR","name":"Tapestry, Inc.","sector":"Consumer Discretionary"},{"symbol":"TRGP","name":"Targa Resources","sector":"Energy"},{"symbol":"TGT","name":"Target Corporation","sector":"Consumer Staples"},{"symbol":"TEL","name":"TE Connectivity","sector":"Information Technology"},{"symbol":"TDY","name":"Teledyne Technologies","sector":"Information Technology"},{"symbol":"TER","name":"Teradyne","sector":"Information Technology"},{"symbol":"TSLA","name":"Tesla, Inc.","sector":"Consumer Discretionary"},{"symbol":"TXN","name":"Texas Instruments","sector":"Information Technology"},{"symbol":"TPL","name":"Texas Pacific Land Corporation","sector":"Energy"},{"symbol":"TXT","name":"Textron","sector":"Industrials"},{"symbol":"TMO","name":"Thermo Fisher Scientific","sector":"Health Care"},{"symbol":"TJX","name":"TJX Companies","sector":"Consumer Discretionary"},{"symbol":"TKO","name":"TKO Group Holdings","sector":"Communication Services"},{"symbol":"TTD","name":"Trade Desk (The)","sector":"Communication Services"},{"symbol":"TSCO","name":"Tractor Supply","sector":"Consumer Discretionary"},{"symbol":"TT","name":"Trane Technologies","sector":"Industrials"},{"symbol":"TDG","name":"TransDigm Group","sector":"Industrials"},{"symbol":"TRV","name":"Travelers Companies (The)","sector":"Financials"},{"symbol":"TRMB","name":"Trimble Inc.","sector":"Information Technology"},{"symbol":"TFC","name":"Truist Financial","sector":"Financials"},{"symbol":"TYL","name":"Tyler Technologies","sector":"Information Technology"},{"symbol":"TSN","name":"Tyson Foods","sector":"Consumer Staples"},{"symbol":"USB","name":"U.S. Bancorp","sector":"Financials"},{"symbol":"UBER","name":"Uber","sector":"Industrials"},{"symbol":"UDR","name":"UDR, Inc.","sector":"Real Estate"},{"symbol":"ULTA","name":"Ulta Beauty","sector":"Consumer Discretionary"},{"symbol":"UNP","name":"Union Pacific Corporation","sector":"Industrials"},{"symbol":"UAL","name":"United Airlines Holdings","sector":"Industrials"},{"symbol":"UPS","name":"United Parcel Service","sector":"Industrials"},{"symbol":"URI","name":"United Rentals","sector":"Industrials"},{"symbol":"UNH","name":"UnitedHealth Group","sector":"Health Care"},{"symbol":"UHS","name":"Universal Health Services","sector":"Health Care"},{"symbol":"VLO","name":"Valero Energy","sector":"Energy"},{"symbol":"VEEV","name":"Veeva Systems","sector":"Health Care"},{"symbol":"VTR","name":"Ventas","sector":"Real Estate"},{"symbol":"VLTO","name":"Veralto","sector":"Industrials"},{"symbol":"VRSN","name":"Verisign","sector":"Information Technology"},{"symbol":"VRSK","name":"Verisk Analytics","sector":"Industrials"},{"symbol":"VZ","name":"Verizon","sector":"Communication Services"},{"symbol":"VRTX","name":"Vertex Pharmaceuticals","sector":"Health Care"},{"symbol":"VRT","name":"Vertiv","sector":"Industrials"},{"symbol":"VTRS","name":"Viatris","sector":"Health Care"},{"symbol":"VICI","name":"Vici Properties","sector":"Real Estate"},{"symbol":"V","name":"Visa Inc.","sector":"Financials"},{"symbol":"VST","name":"Vistra Corp.","sector":"Utilities"},{"symbol":"VMRK","name":"Vivmark Residential","sector":"Real Estate"},{"symbol":"VMC","name":"Vulcan Materials Company","sector":"Materials"},{"symbol":"WRB","name":"W. R. Berkley Corporation","sector":"Financials"},{"symbol":"GWW","name":"W. W. Grainger","sector":"Industrials"},{"symbol":"WAB","name":"Wabtec","sector":"Industrials"},{"symbol":"WMT","name":"Walmart","sector":"Consumer Staples"},{"symbol":"DIS","name":"Walt Disney Company (The)","sector":"Communication Services"},{"symbol":"WBD","name":"Warner Bros. Discovery","sector":"Communication Services"},{"symbol":"WM","name":"Waste Management","sector":"Industrials"},{"symbol":"WAT","name":"Waters Corporation","sector":"Health Care"},{"symbol":"WEC","name":"WEC Energy Group","sector":"Utilities"},{"symbol":"WFC","name":"Wells Fargo","sector":"Financials"},{"symbol":"WELL","name":"Welltower","sector":"Real Estate"},{"symbol":"WST","name":"West Pharmaceutical Services","sector":"Health Care"},{"symbol":"WDC","name":"Western Digital","sector":"Information Technology"},{"symbol":"WY","name":"Weyerhaeuser","sector":"Real Estate"},{"symbol":"WSM","name":"Williams-Sonoma, Inc.","sector":"Consumer Discretionary"},{"symbol":"WMB","name":"Williams Companies","sector":"Energy"},{"symbol":"WTW","name":"Willis Towers Watson","sector":"Financials"},{"symbol":"WDAY","name":"Workday, Inc.","sector":"Information Technology"},{"symbol":"WYNN","name":"Wynn Resorts","sector":"Consumer Discretionary"},{"symbol":"XEL","name":"Xcel Energy","sector":"Utilities"},{"symbol":"XYL","name":"Xylem Inc.","sector":"Industrials"},{"symbol":"YUM","name":"Yum! Brands","sector":"Consumer Discretionary"},{"symbol":"ZBRA","name":"Zebra Technologies","sector":"Information Technology"},{"symbol":"ZBH","name":"Zimmer Biomet","sector":"Health Care"},{"symbol":"ZTS","name":"Zoetis","sector":"Health Care"}]$snapshot$::jsonb)
as x(symbol text,name text,sector text);

create function private.universe_write_guard() returns trigger language plpgsql security invoker
set search_path = '' as $$
begin
  if current_user <> 'postgres'
    and coalesce(current_setting('quant.universe_write', true), '') <> 'on' then
    raise exception using errcode = '42501', message = 'Use the market publication command';
  end if;
  return new;
end;
$$;
revoke all on function private.universe_write_guard() from public;
create trigger guarded_universe_write before insert or update on public.instrument_universe
  for each row execute function private.universe_write_guard();

create function public.portfolio_command(
  p_action text, p_id uuid default null, p_name text default null,
  p_positions jsonb default null, p_revision integer default null, p_key text default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_id uuid := p_id;
  v_owner uuid := auth.uid();
  v_row public.portfolios;
  v_request jsonb;
  v_saved public.portfolio_write_requests;
  v_result jsonb;
  v_item jsonb;
  v_ordinal integer := 0;
begin
  if not private.is_member() then
    raise exception using errcode = '42501', message = 'Active team admission required';
  end if;
  if p_action is null or p_action not in ('list','get','create','update','delete') then
    raise exception using errcode = 'PT422', message = 'Unknown portfolio operation';
  end if;
  if p_action = 'list' then
    select coalesce(jsonb_agg(r.doc order by r.updated_at desc), '[]'::jsonb) into v_result
    from (select p.updated_at, (to_jsonb(p) - 'owner_id' - 'base_currency') || jsonb_build_object(
      'positions', coalesce((select jsonb_agg(jsonb_build_object('symbol',x.symbol,'weight_bps',x.weight_bps) order by x.ordinal)
       from public.portfolio_positions x where x.portfolio_id=p.id), '[]'::jsonb)) doc
      from public.portfolios p) r;
    return v_result;
  end if;
  if p_action in ('create','update') then
    if p_name is null or length(btrim(p_name)) not between 1 and 100
      or p_positions is null or jsonb_typeof(p_positions) <> 'array' then
      raise exception using errcode='PT422',message='Invalid portfolio';
    end if;
    if jsonb_array_length(p_positions) not between 1 and 30 then
      raise exception using errcode='PT422',message='Invalid positions';
    end if;
    for v_item in select value from jsonb_array_elements(p_positions) loop
      if jsonb_typeof(v_item) <> 'object' then
        raise exception using errcode='PT422',message='Invalid position';
      end if;
      if (v_item - 'symbol' - 'weight_bps') <> '{}'::jsonb
        or not (v_item ? 'symbol' and v_item ? 'weight_bps')
        or jsonb_typeof(v_item->'symbol') <> 'string' or (v_item->>'symbol') !~ '^[A-Z0-9.^=-]{1,20}$'
        or jsonb_typeof(v_item->'weight_bps') <> 'number' or (v_item->>'weight_bps') !~ '^[0-9]{1,5}$' then
        raise exception using errcode='PT422',message='Invalid position';
      end if;
      if (v_item->>'weight_bps')::integer > 10000 then
        raise exception using errcode='PT422',message='Invalid position';
      end if;
    end loop;
    if (select count(distinct value->>'symbol') from jsonb_array_elements(p_positions)) <> jsonb_array_length(p_positions) then
      raise exception using errcode='PT422',message='Duplicate symbols';
    end if;
    if exists(select 1 from jsonb_array_elements(p_positions) x where not exists(
      select 1 from public.instrument_universe i where i.symbol=x->>'symbol' and i.active)) then
      raise exception using errcode='PT422',message='Select a current S&P 500 constituent';
    end if;
    -- Draft targets may be incomplete; simulation enforces exactly 10,000 bps.
  end if;
  perform set_config('quant.portfolio_write','on',true);
  if p_action = 'create' then
    if p_key is not null and length(p_key) not between 1 and 128 then
      raise exception using errcode='PT422',message='Invalid retry key';
    end if;
    v_request := jsonb_build_object('name',btrim(p_name),'positions',p_positions);
    if p_key is not null then
      -- Serialize concurrent retries for the same owner/key; collisions only wait.
      perform pg_advisory_xact_lock(hashtextextended(v_owner::text || ':' || p_key, 0));
      select * into v_saved from public.portfolio_write_requests where owner_id=v_owner and request_key=p_key;
      if found then
        if v_saved.request_payload <> v_request then
          raise exception using errcode='PT409',message='Retry key payload conflict';
        end if;
        perform set_config('quant.portfolio_write','off',true);
        return v_saved.result;
      end if;
    end if;
    insert into public.portfolios(name) values(btrim(p_name)) returning * into v_row;
    v_id := v_row.id;
  else
    select * into v_row from public.portfolios where id=v_id for update;
    if not found then raise exception using errcode='PT404',message='Portfolio not found'; end if;
    if p_action in ('update','delete') and (p_revision is null or p_revision <> v_row.revision) then
      raise exception using errcode='PT409',message='Revision conflict';
    end if;
    if p_action = 'delete' then
      delete from public.portfolios where id=v_id;
      perform set_config('quant.portfolio_write','off',true);
      return 'null'::jsonb;
    end if;
    if p_action = 'update' then
      update public.portfolios set name=btrim(p_name), revision=revision+1, updated_at=clock_timestamp()
      where id=v_id returning * into v_row;
      delete from public.portfolio_positions where portfolio_id=v_id;
    end if;
  end if;
  if p_action in ('create','update') then
    for v_item in select value from jsonb_array_elements(p_positions) loop
      v_ordinal := v_ordinal + 1;
      insert into public.portfolio_positions(portfolio_id,symbol,weight_bps,ordinal)
      values(v_id,v_item->>'symbol',(v_item->>'weight_bps')::integer,v_ordinal);
    end loop;
  end if;
  select (to_jsonb(v_row) - 'owner_id' - 'base_currency') || jsonb_build_object('positions',
    coalesce(jsonb_agg(jsonb_build_object('symbol',symbol,'weight_bps',weight_bps) order by ordinal),'[]'::jsonb))
    into v_result from public.portfolio_positions where portfolio_id=v_id;
  if p_action='create' and p_key is not null then
    insert into public.portfolio_write_requests(owner_id,request_key,request_payload,result)
    values(v_owner,p_key,v_request,v_result);
  end if;
  perform set_config('quant.portfolio_write','off',true);
  return v_result;
end;
$$;
revoke all on function public.portfolio_command(text,uuid,text,jsonb,integer,text) from public, anon, service_role;
grant execute on function public.portfolio_command(text,uuid,text,jsonb,integer,text) to authenticated;

create table public.market_data_metadata (
  dataset_key text primary key,
  record jsonb not null check(jsonb_typeof(record)='object'),
  lease_fence bigint not null,
  published_at timestamptz not null default now()
);
create table public.data_refresh_status (
  dataset_key text primary key,
  lease_token uuid not null,
  lease_fence bigint not null default 1,
  lease_expires_at timestamptz not null,
  last_attempt_at timestamptz not null default now(),
  last_success_at timestamptz
);
alter table public.market_data_metadata enable row level security;
alter table public.data_refresh_status enable row level security;
revoke all on public.market_data_metadata, public.data_refresh_status from anon, authenticated;
grant all on public.market_data_metadata, public.data_refresh_status to service_role;

create function public.claim_market_refresh_lease(p_dataset_key text,p_lease_seconds integer)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare v_row public.data_refresh_status;
begin
  if length(p_dataset_key) not between 1 and 300 or p_lease_seconds not between 1 and 300 then
    raise exception using errcode='22023',message='Invalid lease request';
  end if;
  insert into public.data_refresh_status(dataset_key,lease_token,lease_expires_at)
  values(p_dataset_key,gen_random_uuid(),clock_timestamp()+make_interval(secs=>p_lease_seconds))
  on conflict(dataset_key) do update set lease_token=gen_random_uuid(),
    lease_fence=public.data_refresh_status.lease_fence+1,
    lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),last_attempt_at=clock_timestamp()
    where public.data_refresh_status.lease_expires_at <= clock_timestamp()
  returning * into v_row;
  if not found then return null; end if;
  return jsonb_build_object('lease_token',v_row.lease_token,'lease_fence',v_row.lease_fence,'lease_expires_at',v_row.lease_expires_at);
end;
$$;
create function public.publish_market_dataset(p_dataset_key text,p_fence bigint,p_lease_token uuid,p_record jsonb)
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
  insert into public.market_data_metadata(dataset_key,record,lease_fence) values(p_dataset_key,p_record,p_fence)
    on conflict(dataset_key) do update set record=excluded.record,lease_fence=excluded.lease_fence,published_at=clock_timestamp();
  update public.data_refresh_status set lease_expires_at=clock_timestamp(),last_success_at=clock_timestamp() where dataset_key=p_dataset_key;
  return true;
end;
$$;
revoke all on function public.claim_market_refresh_lease(text,integer), public.publish_market_dataset(text,bigint,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.claim_market_refresh_lease(text,integer), public.publish_market_dataset(text,bigint,uuid,jsonb) to service_role;
insert into storage.buckets(id,name,public) values('market-data','market-data',false);
-- No browser Storage policies: authenticated browser users cannot access raw
-- market artifacts; only the isolated market-ingestion credential uses this bucket.
