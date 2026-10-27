"""Local human-review tickets. No outbound messaging or model calls."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.ingestion import IngestionError

MAX_TICKETS = 500
MAX_EVENTS = 50
STATUSES = ('open','in_progress','resolved')


class TicketStore:
    def __init__(self, path: Path, conversations):
        self.path = path
        self.conversations = conversations
        path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as connection:
            if connection.execute('PRAGMA user_version').fetchone()[0] > 1:
                raise RuntimeError('Tickets require a newer ALETHIA version.')
            connection.execute('''CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,turn_id TEXT NOT NULL UNIQUE,
                question TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL,
                revision INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                resolution TEXT NOT NULL,snapshot_json TEXT NOT NULL)''')
            connection.execute('''CREATE TABLE IF NOT EXISTS ticket_events (
                id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL,
                created_at TEXT NOT NULL,UNIQUE(ticket_id,revision))''')
            connection.execute('PRAGMA user_version=1')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path,timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection: yield connection
        finally:
            connection.close()

    @staticmethod
    def summary(row):
        return {key:row[key] for key in ('id','conversation_id','turn_id','question','reason','status',
            'revision','created_at','updated_at','resolution')}

    def list(self, status=None):
        with self.connect() as connection:
            rows = connection.execute('SELECT * FROM tickets'+(' WHERE status=?' if status else '')+
                ' ORDER BY updated_at DESC,id',(status,) if status else ()).fetchall()
            return [self.summary(row) for row in rows]

    def links(self, turn_ids):
        if not turn_ids: return {}
        with self.connect() as connection:
            return {row['turn_id']:row['id'] for row in connection.execute(
                'SELECT id,turn_id FROM tickets WHERE turn_id IN ('+','.join('?' for _ in turn_ids)+')',turn_ids)}

    def get(self, identity):
        with self.connect() as connection:
            connection.execute('BEGIN')
            row = connection.execute('SELECT * FROM tickets WHERE id=?',(identity,)).fetchone()
            if row is None: raise IngestionError('Ticket not found.',404)
            detail = {**self.summary(row),'snapshot':json.loads(row['snapshot_json']),
                'events':[dict(event) for event in connection.execute(
                    'SELECT * FROM ticket_events WHERE ticket_id=? ORDER BY revision',(identity,))]}
        detail['snapshot'] = self.conversations.annotate(detail['snapshot'])
        with self.conversations.connect() as connection:
            detail['origin_available'] = connection.execute('SELECT 1 FROM turns WHERE id=? AND conversation_id=?',
                (detail['turn_id'],detail['conversation_id'])).fetchone() is not None
        return detail

    def create(self, conversation_id, turn_id):
        # Read the server's saved turn, never a browser/model-supplied snapshot.
        conversation = self.conversations.get(conversation_id)
        turn = next((turn for turn in conversation['turns'] if turn['turn_id']==turn_id),None)
        if turn is None: raise IngestionError('Saved answer not found in this conversation.',404)
        snapshot = json.dumps(turn,ensure_ascii=False)
        if len(snapshot.encode('utf8')) > 32768:
            raise IngestionError('Ticket context exceeds its 32 KiB limit.',413)
        reason = (turn.get('reason') or 'unsupported_question') if turn['status']=='needs_human' else (
            'clarification_review' if turn['status']=='needs_clarification' else 'requested_review')
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT id FROM tickets WHERE turn_id=?',(turn_id,)).fetchone()
            if existing:
                identity,outcome = existing['id'],'existing'
            else:
                if connection.execute('SELECT count(*) FROM tickets').fetchone()[0] >= MAX_TICKETS:
                    raise IngestionError('Local ticket limit reached (500). Remove an unneeded ticket first.',409)
                identity,outcome = uuid4().hex,'created'
                connection.execute('INSERT INTO tickets VALUES (?,?,?,?,?,?,1,?,?,?,?)',
                    (identity,conversation_id,turn_id,turn['question'],reason,'open',now,now,'',snapshot))
                connection.execute('INSERT INTO ticket_events VALUES (?,?,1,?,?,?,?)',
                    (uuid4().hex,identity,'created','open','Created locally for human review. No message was sent.',now))
        return {'outcome':outcome,'ticket':self.get(identity)}

    def update(self, identity, expected_revision, status, note):
        note = note.strip()
        if status not in STATUSES or len(note)>2000:
            raise IngestionError('Invalid ticket status or note.',422)
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM tickets WHERE id=?',(identity,)).fetchone()
            if row is None: raise IngestionError('Ticket not found.',404)
            if expected_revision != row['revision']:
                raise IngestionError('This ticket changed in another tab. Reload it before saving.',409)
            if status==row['status'] and not note:
                raise IngestionError('Choose a new status or add a note.',422)
            if status=='resolved' and status!=row['status'] and not note:
                raise IngestionError('Add a resolution note before resolving this ticket.',422)
            if row['revision'] >= MAX_EVENTS:
                raise IngestionError('This ticket reached its 50-event limit.',409)
            revision = row['revision']+1
            now = datetime.now(timezone.utc).isoformat()
            resolution = (note if note else row['resolution']) if status=='resolved' else ''
            connection.execute('UPDATE tickets SET status=?,revision=?,updated_at=?,resolution=? WHERE id=?',
                (status,revision,now,resolution,identity))
            connection.execute('INSERT INTO ticket_events VALUES (?,?,?,?,?,?,?)',
                (uuid4().hex,identity,revision,'status_changed' if status!=row['status'] else 'note_added',status,note,now))
        return self.get(identity)

    def delete(self, identity, expected_revision):
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT revision FROM tickets WHERE id=?',(identity,)).fetchone()
            if row is None: raise IngestionError('Ticket not found.',404)
            if row['revision'] != expected_revision:
                raise IngestionError('This ticket changed. Reload it before deleting.',409)
            connection.execute('DELETE FROM tickets WHERE id=?',(identity,))
