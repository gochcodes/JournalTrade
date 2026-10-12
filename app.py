"""
Journal Trade - Profesjonalny Trading Journal
Kompletna aplikacja do prowadzenia dziennika tradingowego.
"""

import os
import sys
import sqlite3
import uuid
import csv
import io
import webbrowser
import threading
import math
from datetime import datetime, date, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, flash, send_from_directory, Response, make_response
)

# Determine base directory
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = 'journal-trade-secret-key-2024'

DB_PATH = os.path.join(BASE_DIR, 'data', 'trades.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max


def get_db():
    """Polaczenie z baza danych."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Inicjalizuj baze danych."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date DATE NOT NULL,
            godzina_wejscia TEXT,
            instrument TEXT,
            kierunek TEXT DEFAULT 'LONG',
            entry_price REAL,
            exit_price REAL,
            wielkosc_pozycji REAL,
            profit_loss REAL DEFAULT 0,
            notatki TEXT,
            tagi TEXT DEFAULT '',
            screenshot TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);
        CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument);
    ''')

    # Migracje: nowe kolumny
    existing = {r['name'] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
    for col, ddl in (('tagi', "TEXT DEFAULT ''"),
                     ('source', "TEXT DEFAULT 'manual'"),
                     ('external_id', 'TEXT')):
        if col not in existing:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {ddl}")
    conn.executescript('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_external
            ON trades(external_id) WHERE external_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')

    conn.commit()
    conn.close()


def allowed_file(filename):
    """Sprawdz czy rozszerzenie pliku jest dozwolone."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================
# ROUTES - PAGES
# ========================

@app.route('/')
def index():
    """Dashboard - strona glowna."""
    return render_template('dashboard.html', page='dashboard')


@app.route('/kalendarz')
def kalendarz():
    """Widok kalendarza."""
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    return render_template('kalendarz.html', year=year, month=month, today=today, page='kalendarz')


@app.route('/statystyki')
def statystyki():
    """Strona statystyk."""
    return render_template('statystyki.html', page='statystyki')


@app.route('/historia')
def historia():
    """Historia tradow."""
    return render_template('historia.html', page='historia')


@app.route('/kalkulator')
def kalkulator():
    """Kalkulator ryzyka."""
    return render_template('kalkulator.html', page='kalkulator')


@app.route('/dzien/<trade_date>')
def day_view(trade_date):
    """Widok szczegolowy dnia."""
    conn = get_db()
    trades = conn.execute(
        'SELECT * FROM trades WHERE trade_date = ? ORDER BY godzina_wejscia',
        (trade_date,)
    ).fetchall()

    summary = conn.execute('''
        SELECT
            COUNT(*) as count,
            SUM(profit_loss) as total_pl
        FROM trades WHERE trade_date = ?
    ''', (trade_date,)).fetchone()

    conn.close()
    return render_template('day_view.html',
                           trades=trades,
                           trade_date=trade_date,
                           summary=summary,
                           page='kalendarz')


@app.route('/dodaj', methods=['GET', 'POST'])
def add_trade():
    """Dodaj nowy trade."""
    if request.method == 'POST':
        trade_date = request.form.get('trade_date', date.today().isoformat())
        godzina_wejscia = request.form.get('godzina_wejscia', '')
        instrument = request.form.get('instrument', '').upper().strip()
        kierunek = request.form.get('kierunek', 'LONG')
        entry_price = request.form.get('entry_price', None, type=float)
        exit_price = request.form.get('exit_price', None, type=float)
        wielkosc_pozycji = request.form.get('wielkosc_pozycji', None, type=float)
        profit_loss = request.form.get('profit_loss', 0, type=float)
        notatki = request.form.get('notatki', '')
        tagi = request.form.get('tagi', '').strip()

        screenshot_filename = None
        if 'screenshot' in request.files:
            file = request.files['screenshot']
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                screenshot_filename = f"{uuid.uuid4().hex}.{ext}"
                file.save(os.path.join(UPLOAD_FOLDER, screenshot_filename))

        conn = get_db()
        conn.execute('''
            INSERT INTO trades
            (trade_date, godzina_wejscia, instrument, kierunek, entry_price,
             exit_price, wielkosc_pozycji, profit_loss, notatki, tagi, screenshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trade_date, godzina_wejscia, instrument, kierunek, entry_price,
              exit_price, wielkosc_pozycji, profit_loss, notatki, tagi, screenshot_filename))
        conn.commit()
        conn.close()

        flash('Trade został dodany!', 'success')
        return redirect(url_for('day_view', trade_date=trade_date))

    today = date.today().isoformat()
    selected_date = request.args.get('date', today)

    # Get existing tags for autocomplete
    conn = get_db()
    tag_rows = conn.execute("SELECT DISTINCT tagi FROM trades WHERE tagi != '' AND tagi IS NOT NULL").fetchall()
    conn.close()
    all_tags = set()
    for row in tag_rows:
        for tag in row['tagi'].split(','):
            tag = tag.strip()
            if tag:
                all_tags.add(tag)

    return render_template('add_trade.html', selected_date=selected_date, all_tags=sorted(all_tags), page='dodaj')


@app.route('/edytuj/<int:trade_id>', methods=['GET', 'POST'])
def edit_trade(trade_id):
    """Edytuj istniejacy trade."""
    conn = get_db()

    if request.method == 'POST':
        trade_date = request.form.get('trade_date')
        godzina_wejscia = request.form.get('godzina_wejscia', '')
        instrument = request.form.get('instrument', '').upper().strip()
        kierunek = request.form.get('kierunek', 'LONG')
        entry_price = request.form.get('entry_price', None, type=float)
        exit_price = request.form.get('exit_price', None, type=float)
        wielkosc_pozycji = request.form.get('wielkosc_pozycji', None, type=float)
        profit_loss = request.form.get('profit_loss', 0, type=float)
        notatki = request.form.get('notatki', '')
        tagi = request.form.get('tagi', '').strip()

        screenshot_filename = request.form.get('existing_screenshot', None)
        if 'screenshot' in request.files:
            file = request.files['screenshot']
            if file and file.filename and allowed_file(file.filename):
                if screenshot_filename:
                    old_path = os.path.join(UPLOAD_FOLDER, screenshot_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                ext = file.filename.rsplit('.', 1)[1].lower()
                screenshot_filename = f"{uuid.uuid4().hex}.{ext}"
                file.save(os.path.join(UPLOAD_FOLDER, screenshot_filename))

        conn.execute('''
            UPDATE trades SET
                trade_date = ?, godzina_wejscia = ?, instrument = ?, kierunek = ?,
                entry_price = ?, exit_price = ?, wielkosc_pozycji = ?,
                profit_loss = ?, notatki = ?, tagi = ?, screenshot = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (trade_date, godzina_wejscia, instrument, kierunek, entry_price,
              exit_price, wielkosc_pozycji, profit_loss, notatki, tagi,
              screenshot_filename, trade_id))
        conn.commit()
        conn.close()

        flash('Trade został zaktualizowany!', 'success')
        return redirect(url_for('day_view', trade_date=trade_date))

    trade = conn.execute('SELECT * FROM trades WHERE id = ?', (trade_id,)).fetchone()

    tag_rows = conn.execute("SELECT DISTINCT tagi FROM trades WHERE tagi != '' AND tagi IS NOT NULL").fetchall()
    conn.close()
    all_tags = set()
    for row in tag_rows:
        for tag in row['tagi'].split(','):
            tag = tag.strip()
            if tag:
                all_tags.add(tag)

    if not trade:
        flash('Nie znaleziono transakcji.', 'error')
        return redirect(url_for('index'))

    return render_template('edit_trade.html', trade=trade, all_tags=sorted(all_tags), page='kalendarz')


@app.route('/usun/<int:trade_id>', methods=['POST'])
def delete_trade(trade_id):
    """Usun trade."""
    conn = get_db()
    trade = conn.execute('SELECT trade_date, screenshot FROM trades WHERE id = ?', (trade_id,)).fetchone()

    if trade:
        if trade['screenshot']:
            screenshot_path = os.path.join(UPLOAD_FOLDER, trade['screenshot'])
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
        conn.execute('DELETE FROM trades WHERE id = ?', (trade_id,))
        conn.commit()
        trade_date = trade['trade_date']
    else:
        trade_date = date.today().isoformat()

    conn.close()
    flash('Trade został usunięty.', 'info')
    return redirect(url_for('day_view', trade_date=trade_date))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serwuj uploadowane pliki."""
    return send_from_directory(UPLOAD_FOLDER, filename)


# ========================
# API ENDPOINTS
# ========================

@app.route('/api/dashboard')
def api_dashboard():
    """API - dane dashboardu."""
    conn = get_db()
    today = date.today()

    # Dzisiejsze trady
    today_trades = conn.execute('''
        SELECT COUNT(*) as cnt, COALESCE(SUM(profit_loss), 0) as pl
        FROM trades WHERE trade_date = ?
    ''', (today.isoformat(),)).fetchone()

    # Ten tydzien
    week_start = today - timedelta(days=today.weekday())
    week_trades = conn.execute('''
        SELECT COUNT(*) as cnt, COALESCE(SUM(profit_loss), 0) as pl
        FROM trades WHERE trade_date >= ?
    ''', (week_start.isoformat(),)).fetchone()

    # Ten miesiac
    month_start = today.replace(day=1)
    month_trades = conn.execute('''
        SELECT COUNT(*) as cnt, COALESCE(SUM(profit_loss), 0) as pl
        FROM trades WHERE trade_date >= ?
    ''', (month_start.isoformat(),)).fetchone()

    # Calosciowe
    total = conn.execute('''
        SELECT COUNT(*) as cnt, COALESCE(SUM(profit_loss), 0) as pl,
               COALESCE(SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), 0) as wins,
               COALESCE(SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END), 0) as losses
        FROM trades
    ''').fetchone()

    # Seria wygranych/przegranych (streak)
    recent = conn.execute('''
        SELECT profit_loss FROM trades ORDER BY trade_date DESC, godzina_wejscia DESC LIMIT 50
    ''').fetchall()

    streak = 0
    streak_type = 'none'
    if recent:
        first_pl = recent[0]['profit_loss']
        if first_pl > 0:
            streak_type = 'win'
            for r in recent:
                if r['profit_loss'] > 0:
                    streak += 1
                else:
                    break
        elif first_pl < 0:
            streak_type = 'loss'
            for r in recent:
                if r['profit_loss'] < 0:
                    streak += 1
                else:
                    break

    # Najlepszy i najgorszy trade
    best = conn.execute('SELECT * FROM trades ORDER BY profit_loss DESC LIMIT 1').fetchone()
    worst = conn.execute('SELECT * FROM trades ORDER BY profit_loss ASC LIMIT 1').fetchone()

    # Ostatnie trady
    recent_trades = conn.execute('''
        SELECT * FROM trades ORDER BY trade_date DESC, godzina_wejscia DESC LIMIT 5
    ''').fetchall()

    # P/L dzienny z ostatnich 30 dni (do wykresu)
    thirty_days_ago = today - timedelta(days=30)
    daily_pl = conn.execute('''
        SELECT trade_date, SUM(profit_loss) as pl
        FROM trades WHERE trade_date >= ?
        GROUP BY trade_date ORDER BY trade_date
    ''', (thirty_days_ago.isoformat(),)).fetchall()

    # Equity curve - skumulowany P/L
    cumulative = []
    running_total = 0
    for row in daily_pl:
        running_total += row['pl']
        cumulative.append({'date': row['trade_date'], 'pl': round(row['pl'], 2), 'cumulative': round(running_total, 2)})

    conn.close()

    winrate = round(total['wins'] / total['cnt'] * 100, 1) if total['cnt'] else 0

    return jsonify({
        'today': {'count': today_trades['cnt'], 'pl': round(today_trades['pl'], 2)},
        'week': {'count': week_trades['cnt'], 'pl': round(week_trades['pl'], 2)},
        'month': {'count': month_trades['cnt'], 'pl': round(month_trades['pl'], 2)},
        'total': {
            'count': total['cnt'],
            'pl': round(total['pl'], 2),
            'wins': total['wins'],
            'losses': total['losses'],
            'winrate': winrate
        },
        'streak': {'count': streak, 'type': streak_type},
        'best': dict(best) if best else None,
        'worst': dict(worst) if worst else None,
        'recent_trades': [dict(t) for t in recent_trades],
        'equity_curve': cumulative,
    })


@app.route('/api/calendar/<int:year>/<int:month>')
def api_calendar(year, month):
    """API - dane kalendarza."""
    conn = get_db()

    rows = conn.execute('''
        SELECT
            trade_date,
            COUNT(*) as trade_count,
            SUM(profit_loss) as total_pl,
            SUM(CASE WHEN profit_loss > 0 THEN profit_loss ELSE 0 END) as total_profit,
            SUM(CASE WHEN profit_loss < 0 THEN profit_loss ELSE 0 END) as total_loss
        FROM trades
        WHERE strftime('%Y', trade_date) = ? AND strftime('%m', trade_date) = ?
        GROUP BY trade_date
        ORDER BY trade_date
    ''', (str(year), f'{month:02d}')).fetchall()

    conn.close()

    data = {}
    for row in rows:
        data[row['trade_date']] = {
            'trade_count': row['trade_count'],
            'total_pl': round(row['total_pl'], 2) if row['total_pl'] else 0,
            'total_profit': round(row['total_profit'], 2) if row['total_profit'] else 0,
            'total_loss': round(row['total_loss'], 2) if row['total_loss'] else 0,
        }

    return jsonify(data)


@app.route('/api/stats/<int:year>/<int:month>')
def api_month_stats(year, month):
    """API - statystyki miesiaca."""
    conn = get_db()

    row = conn.execute('''
        SELECT
            COUNT(*) as total_trades,
            COALESCE(SUM(profit_loss), 0) as total_pl,
            COALESCE(SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), 0) as winning_trades,
            COALESCE(SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END), 0) as losing_trades,
            COALESCE(SUM(CASE WHEN profit_loss > 0 THEN profit_loss ELSE 0 END), 0) as total_profit,
            COALESCE(SUM(CASE WHEN profit_loss < 0 THEN profit_loss ELSE 0 END), 0) as total_loss,
            COALESCE(AVG(profit_loss), 0) as avg_pl
        FROM trades
        WHERE strftime('%Y', trade_date) = ? AND strftime('%m', trade_date) = ?
    ''', (str(year), f'{month:02d}')).fetchone()

    conn.close()

    total = row['total_trades'] or 0
    wins = row['winning_trades'] or 0

    return jsonify({
        'total_trades': total,
        'total_pl': round(row['total_pl'], 2),
        'winning_trades': wins,
        'losing_trades': row['losing_trades'] or 0,
        'total_profit': round(row['total_profit'], 2),
        'total_loss': round(row['total_loss'], 2),
        'avg_pl': round(row['avg_pl'], 2),
        'winrate': round(wins / total * 100, 1) if total > 0 else 0,
    })


@app.route('/api/statistics')
def api_statistics():
    """API - pelne statystyki."""
    conn = get_db()

    # Global stats
    total = conn.execute('''
        SELECT
            COUNT(*) as cnt,
            COALESCE(SUM(profit_loss), 0) as total_pl,
            COALESCE(AVG(profit_loss), 0) as avg_pl,
            COALESCE(MAX(profit_loss), 0) as best_trade,
            COALESCE(MIN(profit_loss), 0) as worst_trade,
            COALESCE(SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), 0) as wins,
            COALESCE(SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END), 0) as losses,
            COALESCE(SUM(CASE WHEN profit_loss = 0 THEN 1 ELSE 0 END), 0) as breakeven,
            COALESCE(AVG(CASE WHEN profit_loss > 0 THEN profit_loss END), 0) as avg_win,
            COALESCE(AVG(CASE WHEN profit_loss < 0 THEN profit_loss END), 0) as avg_loss
        FROM trades
    ''').fetchone()

    # By instrument
    by_instrument = conn.execute('''
        SELECT
            instrument,
            COUNT(*) as cnt,
            COALESCE(SUM(profit_loss), 0) as pl,
            COALESCE(SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), 0) as wins
        FROM trades
        WHERE instrument IS NOT NULL AND instrument != ''
        GROUP BY instrument
        ORDER BY pl DESC
    ''').fetchall()

    # By day of week
    by_day = conn.execute('''
        SELECT
            CAST(strftime('%w', trade_date) AS INTEGER) as dow,
            COUNT(*) as cnt,
            COALESCE(SUM(profit_loss), 0) as pl,
            COALESCE(SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), 0) as wins
        FROM trades
        GROUP BY dow
        ORDER BY dow
    ''').fetchall()

    day_names = ['Niedziela', 'Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota']

    # By hour
    by_hour = conn.execute('''
        SELECT
            SUBSTR(godzina_wejscia, 1, 2) as hour,
            COUNT(*) as cnt,
            COALESCE(SUM(profit_loss), 0) as pl,
            COALESCE(SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), 0) as wins
        FROM trades
        WHERE godzina_wejscia IS NOT NULL AND godzina_wejscia != ''
        GROUP BY hour
        ORDER BY hour
    ''').fetchall()

    # By direction
    by_direction = conn.execute('''
        SELECT
            kierunek,
            COUNT(*) as cnt,
            COALESCE(SUM(profit_loss), 0) as pl,
            COALESCE(SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), 0) as wins
        FROM trades
        GROUP BY kierunek
    ''').fetchall()

    # Monthly P/L (last 12 months)
    monthly_pl = conn.execute('''
        SELECT
            strftime('%Y-%m', trade_date) as month,
            COUNT(*) as cnt,
            COALESCE(SUM(profit_loss), 0) as pl
        FROM trades
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    ''').fetchall()

    # By tags
    tag_rows = conn.execute("SELECT tagi, profit_loss FROM trades WHERE tagi IS NOT NULL AND tagi != ''").fetchall()
    tag_stats = {}
    for row in tag_rows:
        for tag in row['tagi'].split(','):
            tag = tag.strip()
            if tag:
                if tag not in tag_stats:
                    tag_stats[tag] = {'cnt': 0, 'pl': 0, 'wins': 0}
                tag_stats[tag]['cnt'] += 1
                tag_stats[tag]['pl'] += row['profit_loss']
                if row['profit_loss'] > 0:
                    tag_stats[tag]['wins'] += 1

    # Equity curve (all time)
    daily_pl = conn.execute('''
        SELECT trade_date, SUM(profit_loss) as pl
        FROM trades GROUP BY trade_date ORDER BY trade_date
    ''').fetchall()

    equity = []
    running = 0
    for row in daily_pl:
        running += row['pl']
        equity.append({'date': row['trade_date'], 'value': round(running, 2)})

    conn.close()

    cnt = total['cnt'] or 1
    wins = total['wins'] or 0

    # Profit factor
    gross_profit = abs(total['avg_win'] * wins) if wins else 0
    gross_loss = abs(total['avg_loss'] * total['losses']) if total['losses'] else 1
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0

    return jsonify({
        'total': {
            'count': total['cnt'],
            'pl': round(total['total_pl'], 2),
            'avg_pl': round(total['avg_pl'], 2),
            'best': round(total['best_trade'], 2),
            'worst': round(total['worst_trade'], 2),
            'wins': wins,
            'losses': total['losses'],
            'breakeven': total['breakeven'],
            'winrate': round(wins / cnt * 100, 1) if total['cnt'] > 0 else 0,
            'avg_win': round(total['avg_win'], 2),
            'avg_loss': round(total['avg_loss'], 2),
            'profit_factor': profit_factor,
        },
        'by_instrument': [{'name': r['instrument'], 'count': r['cnt'], 'pl': round(r['pl'], 2), 'winrate': round(r['wins']/r['cnt']*100, 1) if r['cnt'] else 0} for r in by_instrument],
        'by_day': [{'name': day_names[r['dow']], 'count': r['cnt'], 'pl': round(r['pl'], 2), 'winrate': round(r['wins']/r['cnt']*100, 1) if r['cnt'] else 0} for r in by_day],
        'by_hour': [{'hour': r['hour'], 'count': r['cnt'], 'pl': round(r['pl'], 2), 'winrate': round(r['wins']/r['cnt']*100, 1) if r['cnt'] else 0} for r in by_hour],
        'by_direction': [{'name': r['kierunek'], 'count': r['cnt'], 'pl': round(r['pl'], 2), 'winrate': round(r['wins']/r['cnt']*100, 1) if r['cnt'] else 0} for r in by_direction],
        'monthly_pl': [{'month': r['month'], 'count': r['cnt'], 'pl': round(r['pl'], 2)} for r in reversed(list(monthly_pl))],
        'by_tags': [{'name': k, 'count': v['cnt'], 'pl': round(v['pl'], 2), 'winrate': round(v['wins']/v['cnt']*100, 1) if v['cnt'] else 0} for k, v in sorted(tag_stats.items(), key=lambda x: x[1]['pl'], reverse=True)],
        'equity_curve': equity,
    })


@app.route('/api/trades')
def api_trades():
    """API - lista tradow z filtrowaniem."""
    conn = get_db()

    instrument = request.args.get('instrument', '').strip()
    kierunek = request.args.get('kierunek', '').strip()
    tag = request.args.get('tag', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    sort_by = request.args.get('sort', 'trade_date')
    sort_dir = request.args.get('dir', 'DESC')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Whitelist sort columns
    valid_sorts = {'trade_date', 'instrument', 'profit_loss', 'entry_price', 'exit_price', 'created_at'}
    if sort_by not in valid_sorts:
        sort_by = 'trade_date'
    if sort_dir not in ('ASC', 'DESC'):
        sort_dir = 'DESC'

    query = 'SELECT * FROM trades WHERE 1=1'
    count_query = 'SELECT COUNT(*) as cnt FROM trades WHERE 1=1'
    params = []
    count_params = []

    if instrument:
        query += ' AND instrument LIKE ?'
        count_query += ' AND instrument LIKE ?'
        params.append(f'%{instrument}%')
        count_params.append(f'%{instrument}%')

    if kierunek:
        query += ' AND kierunek = ?'
        count_query += ' AND kierunek = ?'
        params.append(kierunek)
        count_params.append(kierunek)

    if tag:
        query += ' AND tagi LIKE ?'
        count_query += ' AND tagi LIKE ?'
        params.append(f'%{tag}%')
        count_params.append(f'%{tag}%')

    if date_from:
        query += ' AND trade_date >= ?'
        count_query += ' AND trade_date >= ?'
        params.append(date_from)
        count_params.append(date_from)

    if date_to:
        query += ' AND trade_date <= ?'
        count_query += ' AND trade_date <= ?'
        params.append(date_to)
        count_params.append(date_to)

    total_count = conn.execute(count_query, count_params).fetchone()['cnt']
    total_pages = math.ceil(total_count / per_page) if per_page > 0 else 1

    query += f' ORDER BY {sort_by} {sort_dir}, godzina_wejscia DESC'
    query += ' LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])

    trades = conn.execute(query, params).fetchall()

    # Get unique instruments and tags for filters
    instruments = conn.execute("SELECT DISTINCT instrument FROM trades WHERE instrument IS NOT NULL AND instrument != '' ORDER BY instrument").fetchall()
    tag_rows = conn.execute("SELECT DISTINCT tagi FROM trades WHERE tagi IS NOT NULL AND tagi != ''").fetchall()
    all_tags = set()
    for row in tag_rows:
        for t in row['tagi'].split(','):
            t = t.strip()
            if t:
                all_tags.add(t)

    conn.close()

    return jsonify({
        'trades': [dict(t) for t in trades],
        'total': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'instruments': [r['instrument'] for r in instruments],
        'tags': sorted(all_tags),
    })


@app.route('/api/export/csv')
def export_csv():
    """Eksport tradow do CSV."""
    conn = get_db()
    trades = conn.execute('SELECT * FROM trades ORDER BY trade_date DESC, godzina_wejscia DESC').fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data', 'Godzina', 'Instrument', 'Kierunek', 'Entry Price', 'Exit Price',
                      'Wielkosc pozycji', 'Zysk/Strata', 'Tagi', 'Notatki'])

    for t in trades:
        writer.writerow([
            t['trade_date'], t['godzina_wejscia'], t['instrument'], t['kierunek'],
            t['entry_price'], t['exit_price'], t['wielkosc_pozycji'],
            t['profit_loss'], t['tagi'], t['notatki']
        ])

    response = make_response('\ufeff' + output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=journal_trade_export.csv'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return response


# ========================
# IMPORT / SYNCHRONIZACJA
# ========================

import importers  # noqa: E402

SYNC_KEYS = ['sync_provider', 'auto_sync', 'sync_interval', 'sync_days',
             'mt5_login', 'mt5_password', 'mt5_server', 'mt5_path',
             'binance_key', 'binance_secret', 'last_sync', 'last_sync_result']
SECRET_KEYS = {'mt5_password', 'binance_secret'}
sync_lock = threading.Lock()


def get_settings():
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return {r['key']: r['value'] or '' for r in rows}


def save_settings(values):
    conn = get_db()
    for k, v in values.items():
        conn.execute('INSERT INTO settings(key, value) VALUES(?, ?) '
                     'ON CONFLICT(key) DO UPDATE SET value = excluded.value', (k, str(v)))
    conn.commit()
    conn.close()


def insert_trades(trades):
    """Zapisz trady, pomijając duplikaty (external_id). Zwraca (dodane, duplikaty)."""
    conn = get_db()
    added = 0
    for t in trades:
        cur = conn.execute('''
            INSERT OR IGNORE INTO trades
            (trade_date, godzina_wejscia, instrument, kierunek, entry_price, exit_price,
             wielkosc_pozycji, profit_loss, notatki, tagi, source, external_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (t['trade_date'], t['godzina_wejscia'], t['instrument'], t['kierunek'],
              t['entry_price'], t['exit_price'], t['wielkosc_pozycji'], t['profit_loss'],
              t['notatki'], t['tagi'], t['source'], t['external_id']))
        added += cur.rowcount
    conn.commit()
    conn.close()
    return added, len(trades) - added


def run_sync():
    """Wykonaj synchronizację wg zapisanych ustawień."""
    if not sync_lock.acquire(blocking=False):
        return {'ok': False, 'message': 'Synchronizacja już trwa.'}
    try:
        s = get_settings()
        provider = s.get('sync_provider', '')
        try:
            days = max(1, min(365, int(s.get('sync_days') or 30)))
        except ValueError:
            days = 30
        since = datetime.now() - timedelta(days=days)
        try:
            if provider == 'mt5':
                trades = importers.sync_mt5(s, since)
            elif provider == 'binance':
                trades = importers.sync_binance(s, since)
            else:
                return {'ok': False, 'message': 'Wybierz dostawcę API w ustawieniach.'}
            added, dupes = insert_trades(trades)
            result = {'ok': True, 'added': added, 'duplicates': dupes,
                      'message': f'Pobrano {len(trades)} transakcji: {added} nowych, {dupes} już istniało.'}
        except Exception as e:  # noqa: BLE001
            result = {'ok': False, 'message': str(e)}
        save_settings({'last_sync': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                       'last_sync_result': result['message']})
        return result
    finally:
        sync_lock.release()


def auto_sync_loop():
    """Wątek w tle: automatyczna synchronizacja co N minut."""
    import time as _t
    _t.sleep(10)
    while True:
        try:
            s = get_settings()
            if s.get('auto_sync') == '1' and s.get('sync_provider'):
                interval = max(5, int(s.get('sync_interval') or 15))
                last = s.get('last_sync')
                due = True
                if last:
                    last_dt = datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
                    due = datetime.now() - last_dt >= timedelta(minutes=interval)
                if due:
                    run_sync()
        except Exception:  # noqa: BLE001
            pass
        _t.sleep(60)


@app.route('/import')
def import_page():
    """Strona: metody wprowadzania transakcji."""
    return render_template('import.html', page='import', mt5_available=importers.mt5_available())


@app.route('/api/import/file', methods=['POST'])
def api_import_file():
    """Import pliku CSV/HTML. preview=1 -> tylko podgląd."""
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'ok': False, 'message': 'Nie wybrano pliku.'}), 400
    data = file.read()
    if not data:
        return jsonify({'ok': False, 'message': 'Plik jest pusty.'}), 400
    try:
        trades, skipped = importers.parse_file(file.filename, data)
    except Exception as e:  # noqa: BLE001
        return jsonify({'ok': False, 'message': str(e)}), 400

    if not trades:
        return jsonify({'ok': False, 'message': 'Nie znaleziono żadnych transakcji w pliku.'}), 400

    if request.form.get('preview') == '1':
        conn = get_db()
        existing = set()
        ids = [t['external_id'] for t in trades]
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            q = f"SELECT external_id FROM trades WHERE external_id IN ({','.join('?' * len(chunk))})"
            existing.update(r['external_id'] for r in conn.execute(q, chunk).fetchall())
        conn.close()
        for t in trades:
            t['duplicate'] = t['external_id'] in existing
        return jsonify({'ok': True, 'trades': trades, 'skipped': skipped,
                        'total_pl': round(sum(t['profit_loss'] for t in trades), 2)})

    extra_tag = request.form.get('tag', '').strip()
    if extra_tag:
        for t in trades:
            t['tagi'] = ', '.join(x for x in [t['tagi'], extra_tag] if x)
    added, dupes = insert_trades(trades)
    return jsonify({'ok': True, 'added': added, 'duplicates': dupes, 'skipped': skipped,
                    'message': f'Zaimportowano {added} transakcji ({dupes} duplikatów pominięto).'})


@app.route('/api/sync/settings', methods=['GET', 'POST'])
def api_sync_settings():
    if request.method == 'POST':
        payload = request.get_json(force=True) or {}
        values = {}
        for k in SYNC_KEYS:
            if k in ('last_sync', 'last_sync_result') or k not in payload:
                continue
            v = str(payload[k]).strip()
            if k in SECRET_KEYS and v == '********':
                continue  # nie nadpisuj zapisanego sekretu maską
            values[k] = v
        save_settings(values)
        return jsonify({'ok': True, 'message': 'Ustawienia zapisane.'})

    s = get_settings()
    out = {k: s.get(k, '') for k in SYNC_KEYS}
    for k in SECRET_KEYS:
        if out.get(k):
            out[k] = '********'
    out['mt5_available'] = importers.mt5_available()
    return jsonify(out)


@app.route('/api/sync/run', methods=['POST'])
def api_sync_run():
    return jsonify(run_sync())


# ========================
# MAIN
# ========================

if __name__ == '__main__':
    init_db()
    port = 5555
    url = f'http://127.0.0.1:{port}'

    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    threading.Thread(target=auto_sync_loop, daemon=True).start()

    print("==========================================")
    print("       JOURNAL TRADE - Trading Journal      ")
    print(f"   Aplikacja: {url}")
    print("   Zamknij: Ctrl+C")
    print("==========================================")

    app.run(host='127.0.0.1', port=port, debug=False)
