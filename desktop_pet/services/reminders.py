"""Migrated local productivity storage and deterministic timezone-aware reminders."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import re
import sqlite3
import uuid
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from PySide6.QtCore import QObject,Signal,QTimer,QTimeZone

UTC=timezone.utc


def local_zone(name=''):
    selected=name or bytes(QTimeZone.systemTimeZoneId()).decode() or 'UTC'
    try:return ZoneInfo(selected)
    except ZoneInfoNotFoundError:
        raise ValueError('Unknown timezone. Enter an IANA name such as Asia/Manila or UTC. Install tzdata on Windows.') from None


def local_to_utc(value,zone):
    """Reject DST gaps/ambiguous wall times instead of scheduling the wrong hour."""
    if value.tzinfo is not None:return value.astimezone(UTC)
    first=value.replace(tzinfo=zone,fold=0);second=value.replace(tzinfo=zone,fold=1)
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None)!=value:
        raise ValueError('That local time does not exist because of daylight saving. Choose another time.')
    if first.utcoffset()!=second.utcoffset():
        raise ValueError('That local time occurs twice because of daylight saving. Choose an unambiguous time.')
    return first.astimezone(UTC)


def parse_reminder(text,zone_name='',now=None):
    source=re.sub(r'^Biscuit,?\s*','',text.strip(),flags=re.I)
    if not source.lower().startswith('remind me'):
        return None
    zone=local_zone(zone_name);now=now or datetime.now(UTC)
    local=now.astimezone(zone)
    match=re.fullmatch(r'remind me to (.+?) in (\d{1,5}) (minutes?|hours?|days?)\.?',source,re.I)
    if match:
        amount=int(match[2])
        if not 1<=amount<=525600:raise ValueError('Choose a positive reminder delay of at most one year.')
        multiplier=60 if match[3].lower().startswith('minute') else 3600 if match[3].lower().startswith('hour') else 86400
        seconds=amount*multiplier
        if seconds>366*86400:raise ValueError('Choose a reminder within one year.')
        return match[1],now+timedelta(seconds=seconds),str(zone)
    match=re.fullmatch(r'remind me to (.+?) (tomorrow )?at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?\.?',source,re.I)
    if match:
        title,tomorrow,hour,minute,meridiem=match.groups();hour=int(hour);minute=int(minute or 0)
        if meridiem:
            if not 1<=hour<=12:raise ValueError('Use an hour from 1 to 12 with AM/PM.')
            hour=hour%12+(12 if meridiem.lower()=='pm' else 0)
        if hour>23 or minute>59:raise ValueError('Enter a valid reminder time.')
        wall=local.replace(tzinfo=None,hour=hour,minute=minute,second=0,microsecond=0)
        if tomorrow or wall<=local.replace(tzinfo=None):wall+=timedelta(days=1)
        return title,local_to_utc(wall,zone),str(zone)
    if source.lower().startswith('remind me'):
        raise ValueError('Try “Remind me to take a break in 30 minutes” or use Tools → Reminders for a date and time.')
    return None


class ProductivityStore:
    VERSION=1
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version>self.VERSION:raise ValueError('Productivity data was created by a newer Biscuit. It has been left unchanged.')
            if version<1:
                db.executescript('''
                BEGIN;
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
                    due_at REAL NOT NULL,timezone TEXT NOT NULL,completed INTEGER NOT NULL DEFAULT 0,
                    notify INTEGER NOT NULL DEFAULT 1,notified_at REAL,created_at REAL NOT NULL,updated_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS reminders_due ON reminders(completed,due_at);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',due_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',source TEXT NOT NULL DEFAULT 'local',
                    external_id TEXT,list_id TEXT NOT NULL DEFAULT '',etag TEXT NOT NULL DEFAULT '',
                    dirty INTEGER NOT NULL DEFAULT 0,conflict TEXT NOT NULL DEFAULT '',updated_at REAL NOT NULL,
                    UNIQUE(source,list_id,external_id));
                CREATE TABLE IF NOT EXISTS calendar_notices (event_key TEXT PRIMARY KEY,notified_at REAL NOT NULL);
                PRAGMA user_version=1;
                COMMIT;
                ''')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(str(self.path),timeout=.25);db.row_factory=sqlite3.Row
        try:
            yield db;db.commit()
        except Exception:
            db.rollback();raise
        finally:db.close()

    def add_reminder(self,title,due,zone,description='',notify=True):
        title=title.strip()
        if not title:raise ValueError('Give your reminder a title.')
        if due.tzinfo is None:raise ValueError('A reminder needs an explicit timezone.')
        identifier=uuid.uuid4().hex;now=datetime.now(UTC).timestamp()
        with self.connection() as db:
            db.execute('INSERT INTO reminders(id,title,description,due_at,timezone,notify,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                       (identifier,title[:300],description[:4000],due.timestamp(),zone,int(notify),now,now))
        return identifier

    def reminders(self,include_completed=False):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM reminders '+('' if include_completed else 'WHERE completed=0 ')+'ORDER BY due_at LIMIT 500')]

    def due(self,now):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM reminders WHERE completed=0 AND notify=1 AND notified_at IS NULL AND due_at<=? ORDER BY due_at LIMIT 50',(now.timestamp(),))]

    def acknowledge(self,identifier,now):
        with self.connection() as db:db.execute('UPDATE reminders SET notified_at=?,updated_at=? WHERE id=?',(now.timestamp(),now.timestamp(),identifier))

    def complete_reminder(self,identifier):
        with self.connection() as db:db.execute('UPDATE reminders SET completed=1,updated_at=? WHERE id=?',(datetime.now(UTC).timestamp(),identifier))

    def add_task(self,title,description='',due_at=None):
        if not title.strip():raise ValueError('Give your task a title.')
        if due_at:
            datetime.fromisoformat(due_at)
        identifier=uuid.uuid4().hex
        with self.connection() as db:
            db.execute('INSERT INTO tasks(id,title,description,due_at,dirty,updated_at) VALUES(?,?,?,?,1,?)',
                       (identifier,title.strip()[:300],description[:4000],due_at,datetime.now(UTC).timestamp()))
        return identifier

    def tasks(self):
        with self.connection() as db:return [dict(row) for row in db.execute('SELECT * FROM tasks ORDER BY status,due_at,title LIMIT 1000')]

    def task(self,identifier):
        with self.connection() as db:
            row=db.execute('SELECT * FROM tasks WHERE id=?',(identifier,)).fetchone()
            return dict(row) if row else None

    def complete_task(self,identifier):
        with self.connection() as db:db.execute("UPDATE tasks SET status='completed',dirty=1,updated_at=? WHERE id=?",(datetime.now(UTC).timestamp(),identifier))

    def link_task(self,identifier,list_id,remote):
        with self.connection() as db:
            db.execute("UPDATE tasks SET source='google',external_id=?,list_id=?,etag=?,dirty=0,conflict='',updated_at=? WHERE id=?",
                       (remote['id'],list_id,remote.get('etag',''),datetime.now(UTC).timestamp(),identifier))

    def mark_task_issue(self,identifier,text):
        with self.connection() as db:db.execute('UPDATE tasks SET conflict=? WHERE id=?',(text,identifier))

    def merge_tasks(self,list_id,items):
        """Read synchronization only: no deletions, cloud writes, or lost local edits."""
        with self.connection() as db:
            for remote in items:
                if not isinstance(remote,dict) or not remote.get('id'):continue
                row=db.execute("SELECT * FROM tasks WHERE source='google' AND list_id=? AND external_id=?",(list_id,remote['id'])).fetchone()
                if row and row['dirty'] and row['etag']!=remote.get('etag',''):
                    db.execute('UPDATE tasks SET conflict=? WHERE id=?',('Cloud changed; refresh and resolve before writing.',row['id']));continue
                values=(remote.get('title','Untitled')[:300],remote.get('notes','')[:4000],remote.get('due'),
                        'completed' if remote.get('status')=='completed' else 'pending',remote.get('etag',''),datetime.now(UTC).timestamp())
                if row:
                    if not row['dirty']:
                        db.execute('UPDATE tasks SET title=?,description=?,due_at=?,status=?,etag=?,updated_at=?,conflict=\'\' WHERE id=?',values+(row['id'],))
                else:
                    db.execute("INSERT INTO tasks(title,description,due_at,status,etag,updated_at,id,source,external_id,list_id) VALUES(?,?,?,?,?,?,?,'google',?,?)",
                               values+(uuid.uuid4().hex,remote['id'],list_id))

    def event_notified(self,key):
        with self.connection() as db:return db.execute('SELECT 1 FROM calendar_notices WHERE event_key=?',(key,)).fetchone() is not None

    def mark_event_notified(self,key):
        with self.connection() as db:db.execute('INSERT OR IGNORE INTO calendar_notices VALUES(?,?)',(key,datetime.now(UTC).timestamp()))


class ReminderService(QObject):
    due_reminder=Signal(dict)
    changed=Signal()
    status=Signal(str)
    def __init__(self,settings,parent=None,clock=lambda:datetime.now(UTC)):
        super().__init__(parent);self.settings=settings;self.clock=clock;self.emitted=set();self.error=''
        try:self.store=ProductivityStore(Path(settings.directory)/'productivity.sqlite3')
        except (sqlite3.Error,OSError,ValueError):
            self.store=None;self.error='Local productivity data could not be opened. It was left unchanged.'
        self.timer=QTimer(self);self.timer.timeout.connect(self.check_due)
        if self.store:self.timer.start(15000)

    def check_due(self):
        if not self.store or not self.settings.get('notifications'):return
        try:
            for item in self.store.due(self.clock()):
                if item['id'] not in self.emitted:
                    self.emitted.add(item['id']);self.due_reminder.emit(item)
        except sqlite3.Error:self.status.emit('Reminder data is temporarily unavailable.')

    def acknowledge(self,identifier):
        if self.store:self.store.acknowledge(identifier,self.clock())

    def handle_message(self,text):
        if text.lower().strip() in ('show my tasks for today','show my tasks','my tasks'):
            if not self.store:return self.error
            today=self.clock().astimezone(local_zone(self.settings.get('reminder_timezone') or '')).date().isoformat()
            tasks=[t for t in self.store.tasks() if t['status']=='pending' and (not t['due_at'] or t['due_at'][:10]==today)]
            return 'Today’s local/cached tasks:\n'+'\n'.join('• '+t['title'] for t in tasks[:20]) if tasks else 'No pending local tasks for today.'
        try:parsed=parse_reminder(text,self.settings.get('reminder_timezone') or '',self.clock())
        except ValueError as exc:return str(exc)
        if parsed:
            if not self.store:return self.error
            title,due,zone=parsed
            self.store.add_reminder(title,due,zone);self.changed.emit()
            display=due.astimezone(local_zone(zone)).strftime('%Y-%m-%d %I:%M %p')
            return f'Reminder saved locally: {title} · {display} ({zone}).'
        return None

    def shutdown(self):self.timer.stop()
