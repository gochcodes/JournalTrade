"""
Journal Trade - importy plików (CSV/HTML) oraz synchronizacja API.

Obsługiwane:
  * CSV  - dowolny broker (automatyczne rozpoznawanie kolumn), w tym eksport z Journal Trade
  * HTML - raporty MetaTrader 4 (Statement) i MetaTrader 5 (Report History)
  * API  - MetaTrader 5 (lokalny terminal, pakiet MetaTrader5)
         - Binance Futures (USDT-M), klucz API tylko do odczytu
"""

import csv
import hashlib
import hmac
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser


# ============================================================
#  WSPÓLNE NARZĘDZIA
# ============================================================

DATE_FORMATS = [
    '%Y.%m.%d %H:%M:%S', '%Y.%m.%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
    '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M',
    '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M',
    '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M',
    '%Y-%m-%d', '%Y.%m.%d', '%d.%m.%Y', '%d/%m/%Y', '%Y/%m/%d',
]


def parse_datetime(value):
    """Zamień tekst daty na datetime (różne formaty brokerów)."""
    if not value:
        return None
    v = str(value).strip().replace('\u00a0', ' ')
    if not v:
        return None
    # Timestamp w ms / s
    if v.isdigit() and len(v) >= 10:
        ts = int(v)
        if ts > 10 ** 12:
            ts /= 1000
        return datetime.fromtimestamp(ts)
    v = re.sub(r'(\d{1,2}:\d{2}:\d{2})[.,]\d+', r'\1', v)
    v = v.replace('Z', '').split('+')[0].strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def parse_number(value):
    """Zamień tekst na float (obsługuje spacje, przecinki, nawiasy)."""
    if value is None:
        return None
    v = str(value).strip().replace('\u00a0', '').replace(' ', '')
    for sym in ('$', '€', 'zł', 'PLN', 'USD', 'EUR', 'USDT'):
        v = v.replace(sym, '')
    if not v or v in ('-', '—'):
        return None
    neg = v.startswith('(') and v.endswith(')')
    v = v.strip('()')
    if ',' in v and '.' in v:
        v = v.replace(',', '')
    elif ',' in v:
        v = v.replace(',', '.')
    try:
        n = float(v)
        return -n if neg else n
    except ValueError:
        return None


def normalize_direction(value):
    v = (value or '').strip().lower()
    if v.startswith(('buy', 'long', 'kup', 'b')) and not v.startswith('bal'):
        return 'LONG'
    if v.startswith(('sell', 'short', 'sprz', 's')):
        return 'SHORT'
    return None


def make_external_id(source, *parts):
    raw = '|'.join(str(p) for p in parts)
    return f"{source}:{hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]}"


# ============================================================
#  MAPOWANIE KOLUMN
# ============================================================

# klucz -> możliwe nazwy nagłówków (małe litery)
COLUMN_ALIASES = {
    'ticket': ['ticket', 'position', 'pozycja', 'order', 'id', 'trade id', 'tradeid', 'deal id', 'nr'],
    'open_time': ['open time', 'opentime', 'open date', 'entry time', 'czas otwarcia', 'otwarcie',
                  'time', 'date', 'data', 'datetime', 'czas'],
    'time_only': ['godzina', 'hour', 'godzina wejścia', 'godzina wejscia'],
    'close_time': ['close time', 'closetime', 'close date', 'exit time', 'czas zamknięcia', 'zamknięcie'],
    'symbol': ['symbol', 'item', 'instrument', 'pair', 'ticker', 'market', 'asset', 'contract', 'para'],
    'type': ['type', 'side', 'direction', 'kierunek', 'typ', 'buy/sell', 'strona'],
    'volume': ['volume', 'size', 'lots', 'lot', 'qty', 'quantity', 'amount', 'wolumen', 'wielkość',
               'wielkosc', 'wielkosc pozycji', 'wielkość pozycji', 'ilość', 'ilosc'],
    'open_price': ['open price', 'entry price', 'entry', 'cena otwarcia', 'cena wejścia', 'price open'],
    'close_price': ['close price', 'exit price', 'exit', 'cena zamknięcia', 'cena wyjścia', 'price close'],
    'price': ['price', 'cena'],
    'profit': ['profit', 'p/l', 'pnl', 'p&l', 'realized pnl', 'realized p&l', 'net profit', 'zysk',
               'zysk/strata', 'profit/loss', 'wynik', 'result', 'gross p/l', 'net p/l'],
    'commission': ['commission', 'prowizja', 'fee', 'fees'],
    'swap': ['swap', 'swaps', 'rollover'],
    'taxes': ['taxes', 'tax', 'podatek'],
    'notes': ['notatki', 'comment', 'notes', 'komentarz', 'note'],
    'tags': ['tagi', 'tags', 'tag', 'strategia', 'strategy', 'setup'],
}

SKIP_TYPES = ('balance', 'deposit', 'withdraw', 'credit', 'bonus', 'correction', 'buy limit',
              'sell limit', 'buy stop', 'sell stop', 'cancel')


def map_header(header):
    """Zwraca dict klucz -> indeks kolumny. Obsługuje powtórzone 'time'/'price' (MT4/MT5)."""
    mapping = {}
    times, prices = [], []
    for idx, raw in enumerate(header):
        h = (raw or '').strip().lower().replace('_', ' ').rstrip(':')
        if not h:
            continue
        if h in ('time', 'czas'):
            times.append(idx)
        if h in ('price', 'cena'):
            prices.append(idx)
        for key, aliases in COLUMN_ALIASES.items():
            if key in mapping:
                continue
            if h in aliases:
                mapping[key] = idx
                break
    # MT4/MT5: dwa razy "Time" i "Price" -> otwarcie / zamknięcie
    if len(times) >= 2:
        mapping['open_time'] = times[0]
        mapping.setdefault('close_time', times[1])
    if prices:
        mapping.setdefault('open_price', prices[0])
        if len(prices) >= 2:
            mapping.setdefault('close_price', prices[1])
    mapping.pop('price', None)
    return mapping


def is_valid_header(mapping, header):
    lowered = [(h or '').strip().lower() for h in header]
    if 'deal' in lowered or 'state' in lowered:   # sekcje Deals / Orders w MT5
        return False
    return 'symbol' in mapping and 'profit' in mapping and ('open_time' in mapping)


def looks_like_header(cells):
    lowered = [(c or '').strip().lower() for c in cells]
    hits = 0
    all_aliases = {a for v in COLUMN_ALIASES.values() for a in v}
    for c in lowered:
        if c in all_aliases:
            hits += 1
    return hits >= 3


def rows_to_trades(header, rows, source):
    """Zamienia wiersze tabeli na listę tradów (dict)."""
    m = map_header(header)
    trades, skipped = [], 0

    def get(row, key):
        idx = m.get(key)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    for row in rows:
        if not any((c or '').strip() for c in row):
            continue
        type_raw = (get(row, 'type') or '').strip().lower()
        if type_raw and any(type_raw.startswith(s) for s in SKIP_TYPES):
            skipped += 1
            continue
        symbol = (get(row, 'symbol') or '').strip().upper()
        dt = parse_datetime(get(row, 'open_time'))
        if not symbol or not dt:
            skipped += 1
            continue

        time_str = dt.strftime('%H:%M:%S') if (dt.hour or dt.minute or dt.second) else ''
        t_only = get(row, 'time_only')
        if t_only and t_only.strip():
            time_str = t_only.strip()

        profit = parse_number(get(row, 'profit')) or 0.0
        for extra in ('commission', 'swap', 'taxes'):
            val = parse_number(get(row, extra))
            if val:
                profit += val

        direction = normalize_direction(type_raw) or 'LONG'
        entry = parse_number(get(row, 'open_price'))
        exit_ = parse_number(get(row, 'close_price'))
        volume = parse_number(get(row, 'volume'))
        ticket = (get(row, 'ticket') or '').strip()

        ext_id = make_external_id(
            source, ticket or '', dt.isoformat(), symbol, entry, exit_, round(profit, 2)
        ) if not ticket else f"{source}:{ticket}"

        trades.append({
            'trade_date': dt.date().isoformat(),
            'godzina_wejscia': time_str,
            'instrument': symbol,
            'kierunek': direction,
            'entry_price': entry,
            'exit_price': exit_,
            'wielkosc_pozycji': volume,
            'profit_loss': round(profit, 2),
            'notatki': (get(row, 'notes') or '').strip(),
            'tagi': (get(row, 'tags') or '').strip(),
            'external_id': ext_id,
            'source': source,
        })
    return trades, skipped


# ============================================================
#  DEKODOWANIE PLIKÓW
# ============================================================

def decode_bytes(data):
    if data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        return data.decode('utf-16')
    if data[:200].count(b'\x00') > 20:
        try:
            return data.decode('utf-16-le')
        except UnicodeDecodeError:
            pass
    for enc in ('utf-8-sig', 'cp1250', 'latin-1'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='ignore')


# ============================================================
#  CSV
# ============================================================

def parse_csv(data):
    text = decode_bytes(data)
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ';' if sample.count(';') > sample.count(',') else ','

    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError('Plik CSV jest pusty.')

    # znajdź wiersz nagłówka (pierwszy wyglądający na nagłówek w top 20)
    header_idx = 0
    for i, r in enumerate(rows[:20]):
        if looks_like_header(r):
            header_idx = i
            break
    header = rows[header_idx]
    mapping = map_header(header)
    if 'symbol' not in mapping or 'open_time' not in mapping:
        raise ValueError('Nie rozpoznano kolumn. Plik musi zawierać co najmniej kolumny: '
                         'data/czas, symbol/instrument oraz zysk (profit).')
    return rows_to_trades(header, rows[header_idx + 1:], 'csv')


# ============================================================
#  HTML (MT4 / MT5)
# ============================================================

class _TableParser(HTMLParser):
    """Zbiera wszystkie wiersze <tr> jako listy tekstów komórek (z uwzględnieniem colspan)."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self._row = None
        self._cell = None
        self._colspan = 1

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []
            a = dict(attrs)
            try:
                self._colspan = max(1, int(a.get('colspan', 1)))
            except ValueError:
                self._colspan = 1
        elif tag == 'br' and self._cell is not None:
            self._cell.append(' ')

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._row is not None and self._cell is not None:
            text = ' '.join(''.join(self._cell).split())
            self._row.append(text)
            for _ in range(self._colspan - 1):
                self._row.append('')
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


STOP_MARKERS = ('open trades', 'working orders', 'otwarte pozycje', 'orders', 'deals', 'zlecenia',
                'transakcje', 'summary', 'podsumowanie', 'open positions')


def parse_html(data):
    text = decode_bytes(data)
    p = _TableParser()
    p.feed(text)

    is_mt = 'metatrader' in text.lower() or 'mt5' in text.lower() or 'statement' in text.lower()
    source = 'mt-html' if is_mt else 'html'

    trades, skipped = [], 0
    header, section = None, []

    def flush():
        nonlocal trades, skipped, section
        if header and section:
            t, s = rows_to_trades(header, section, source)
            trades.extend(t)
            skipped += s
        section = []

    for row in p.rows:
        non_empty = [c for c in row if c.strip()]
        if not non_empty:
            continue
        if looks_like_header(row):
            flush()
            mapping = map_header(row)
            header = row if is_valid_header(mapping, row) else None
            continue
        if len(non_empty) == 1 and any(non_empty[0].strip().lower().startswith(sm) for sm in STOP_MARKERS):
            flush()
            header = None
            continue
        if header is not None:
            # wiersze danych muszą mieć podobną długość
            if abs(len(row) - len(header)) <= 1:
                section.append(row)
    flush()

    if not trades:
        raise ValueError('Nie znaleziono transakcji w pliku HTML. Obsługiwane są raporty MetaTrader 4 '
                         '(Statement) i MetaTrader 5 (Raport historii -> Pozycje) oraz tabele HTML '
                         'z kolumnami: czas, symbol, zysk.')
    # usuń duplikaty w obrębie jednego pliku
    seen, unique = set(), []
    for t in trades:
        if t['external_id'] not in seen:
            seen.add(t['external_id'])
            unique.append(t)
    return unique, skipped


def parse_file(filename, data):
    name = (filename or '').lower()
    if name.endswith(('.htm', '.html')):
        return parse_html(data)
    if name.endswith(('.csv', '.txt', '.tsv')):
        return parse_csv(data)
    # zgadnij po zawartości
    head = decode_bytes(data[:2000]).lower()
    if '<html' in head or '<table' in head:
        return parse_html(data)
    return parse_csv(data)


# ============================================================
#  API: METATRADER 5
# ============================================================

def mt5_available():
    try:
        import MetaTrader5  # noqa: F401
        return True
    except Exception:
        return False


def sync_mt5(settings, since):
    """Pobiera zamknięte pozycje z lokalnego terminala MetaTrader 5."""
    try:
        import MetaTrader5 as mt5
    except Exception:
        raise RuntimeError('Brak pakietu MetaTrader5. Zainstaluj go poleceniem: pip install MetaTrader5 '
                           '(wymaga zainstalowanego terminala MT5 na tym komputerze).')

    kwargs = {}
    if settings.get('mt5_path'):
        kwargs['path'] = settings['mt5_path']
    login = settings.get('mt5_login', '').strip()
    if login:
        kwargs['login'] = int(login)
        kwargs['password'] = settings.get('mt5_password', '')
        kwargs['server'] = settings.get('mt5_server', '')

    if not mt5.initialize(**kwargs):
        err = mt5.last_error()
        mt5.shutdown()
        raise RuntimeError(f'Nie udało się połączyć z terminalem MT5: {err}. '
                           f'Upewnij się, że MetaTrader 5 jest uruchomiony i zalogowany.')
    try:
        deals = mt5.history_deals_get(since, datetime.now() + timedelta(days=1))
        if deals is None:
            raise RuntimeError(f'Błąd pobierania historii: {mt5.last_error()}')

        positions = {}
        for d in deals:
            if d.position_id == 0 or not d.symbol:
                continue
            p = positions.setdefault(d.position_id, {'in': None, 'out': [], 'profit': 0.0})
            p['profit'] += (d.profit or 0) + (d.commission or 0) + (d.swap or 0) + (getattr(d, 'fee', 0) or 0)
            if d.entry == mt5.DEAL_ENTRY_IN:
                p['in'] = d
            else:
                p['out'].append(d)

        trades = []
        for pid, p in positions.items():
            if not p['in'] or not p['out']:
                continue  # pozycja wciąż otwarta
            din = p['in']
            last_out = p['out'][-1]
            open_dt = datetime.fromtimestamp(din.time)
            trades.append({
                'trade_date': open_dt.date().isoformat(),
                'godzina_wejscia': open_dt.strftime('%H:%M:%S'),
                'instrument': din.symbol.upper(),
                'kierunek': 'LONG' if din.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                'entry_price': din.price,
                'exit_price': last_out.price,
                'wielkosc_pozycji': din.volume,
                'profit_loss': round(p['profit'], 2),
                'notatki': din.comment or '',
                'tagi': '',
                'external_id': f'mt5:{pid}',
                'source': 'mt5',
            })
        return trades
    finally:
        mt5.shutdown()


# ============================================================
#  API: BINANCE FUTURES (USDT-M)
# ============================================================

BINANCE_BASE = 'https://fapi.binance.com'


def _binance_get(path, params, key, secret):
    params = dict(params)
    params['timestamp'] = int(time.time() * 1000)
    params['recvWindow'] = 10000
    query = urllib.parse.urlencode(params)
    sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f'{BINANCE_BASE}{path}?{query}&signature={sig}'
    req = urllib.request.Request(url, headers={'X-MBX-APIKEY': key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='ignore')
        try:
            msg = json.loads(body).get('msg', body)
        except ValueError:
            msg = body
        raise RuntimeError(f'Binance API: {msg}')
    except urllib.error.URLError as e:
        raise RuntimeError(f'Brak połączenia z Binance: {e.reason}')


def sync_binance(settings, since):
    key = settings.get('binance_key', '').strip()
    secret = settings.get('binance_secret', '').strip()
    if not key or not secret:
        raise RuntimeError('Podaj klucz API i Secret Binance w ustawieniach synchronizacji.')

    start = int(since.timestamp() * 1000)
    now = int(time.time() * 1000)
    week = 7 * 24 * 3600 * 1000

    # 1. Zrealizowane P/L (okna po 7 dni)
    incomes = []
    t = start
    while t < now:
        end = min(t + week, now)
        batch = _binance_get('/fapi/v1/income', {
            'incomeType': 'REALIZED_PNL', 'startTime': t, 'endTime': end, 'limit': 1000
        }, key, secret)
        incomes.extend(batch)
        t = end + 1

    # prowizje per tradeId
    fees = {}
    t = start
    while t < now:
        end = min(t + week, now)
        batch = _binance_get('/fapi/v1/income', {
            'incomeType': 'COMMISSION', 'startTime': t, 'endTime': end, 'limit': 1000
        }, key, secret)
        for f in batch:
            fees[str(f.get('tradeId'))] = fees.get(str(f.get('tradeId')), 0) + float(f['income'])
        t = end + 1

    if not incomes:
        return []

    # 2. Szczegóły fillów dla każdego symbolu
    fills = {}
    for symbol in {i['symbol'] for i in incomes}:
        t = start
        while t < now:
            end = min(t + week, now)
            batch = _binance_get('/fapi/v1/userTrades', {
                'symbol': symbol, 'startTime': t, 'endTime': end, 'limit': 1000
            }, key, secret)
            for f in batch:
                fills[str(f['id'])] = f
            t = end + 1

    trades = []
    for inc in incomes:
        tid = str(inc.get('tradeId'))
        fill = fills.get(tid, {})
        dt = datetime.fromtimestamp(int(inc['time']) / 1000)
        side = fill.get('side', '')
        # zamknięcie SELL = pozycja była LONG
        direction = 'LONG' if side == 'SELL' else ('SHORT' if side == 'BUY' else 'LONG')
        if fill.get('positionSide') in ('LONG', 'SHORT'):
            direction = fill['positionSide']
        pnl = float(inc['income']) + fees.get(tid, 0)
        trades.append({
            'trade_date': dt.date().isoformat(),
            'godzina_wejscia': dt.strftime('%H:%M:%S'),
            'instrument': inc['symbol'],
            'kierunek': direction,
            'entry_price': None,
            'exit_price': float(fill['price']) if fill.get('price') else None,
            'wielkosc_pozycji': float(fill['qty']) if fill.get('qty') else None,
            'profit_loss': round(pnl, 2),
            'notatki': 'Zsynchronizowano z Binance Futures',
            'tagi': 'binance',
            'external_id': f'binance:{inc.get("tranId") or tid}',
            'source': 'binance',
        })
    return trades
