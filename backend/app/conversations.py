"""Bounded local conversation snapshots, separate from the document/index schema."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.ingestion import IngestionError

MAX_CONVERSATIONS = 100
MAX_TURNS = 30
MAX_TURN_BYTES = 32768


class ConversationStore:
    def __init__(self, path: Path, documents):
        self.path = path
        self.documents = documents
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            if connection.execute('PRAGMA user_version').fetchone()[0] > 1:
                raise RuntimeError('Conversations require a newer ALETHIA version.')
            connection.execute('''CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0)''')
            connection.execute('''CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,created_at TEXT NOT NULL,response_json TEXT NOT NULL,
                UNIQUE(conversation_id,ordinal))''')
            connection.execute('PRAGMA user_version=1')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def metadata(connection, identity):
        result = connection.execute('''SELECT c.*, (SELECT count(*) FROM turns t WHERE t.conversation_id=c.id) AS turn_count
            FROM conversations c WHERE c.id=?''', (identity,)).fetchone()
        return dict(result) if result else None

    def list(self):
        with self.connect() as connection:
            return [self.metadata(connection, item['id']) for item in connection.execute(
                'SELECT id FROM conversations ORDER BY updated_at DESC,id')]

    def check(self, identity, revision):
        if identity is None:
            if revision is not None:
                raise IngestionError('A revision requires a saved conversation.', 422)
            with self.connect() as connection:
                if connection.execute('SELECT count(*) FROM conversations').fetchone()[0] >= MAX_CONVERSATIONS:
                    raise IngestionError('Conversation limit reached (100). Delete a saved conversation first.', 409)
            return
        with self.connect() as connection:
            current = self.metadata(connection, identity)
            self._check_current(current, revision)

    @staticmethod
    def _check_current(current, revision):
        if not current:
            raise IngestionError('The conversation was deleted or does not exist.', 404)
        if revision != current['revision']:
            raise IngestionError('The conversation changed in another tab. Reload it before asking again.', 409)
        if current['turn_count'] >= MAX_TURNS:
            raise IngestionError('This conversation has 30 turns. Start a new conversation.', 409)

    def append(self, response, identity=None, revision=None):
        payload = json.dumps(response, ensure_ascii=False)
        if len(payload.encode('utf8')) > MAX_TURN_BYTES:
            raise IngestionError('Answer exceeds the saved-turn size limit.', 413)
        now = datetime.now(timezone.utc).isoformat()
        turn_id = uuid4().hex
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if identity:
                current = self.metadata(connection, identity)
                self._check_current(current, revision)
                ordinal = current['revision'] + 1
            else:
                if revision is not None:
                    raise IngestionError('A revision requires a saved conversation.', 422)
                if connection.execute('SELECT count(*) FROM conversations').fetchone()[0] >= MAX_CONVERSATIONS:
                    raise IngestionError('Conversation limit reached (100).', 409)
                identity = uuid4().hex
                ordinal = 1
                connection.execute('INSERT INTO conversations VALUES (?,?,?,?,0)',
                    (identity, response['question'][:80], now, now))
            connection.execute('INSERT INTO turns VALUES (?,?,?,?,?)', (turn_id, identity, ordinal, now, payload))
            connection.execute('UPDATE conversations SET revision=?,updated_at=? WHERE id=?', (ordinal, now, identity))
        return {**self.annotate(response), 'conversation_id': identity, 'conversation_revision': ordinal,
                'turn_id': turn_id, 'created_at': now}

    def annotate(self, response):
        # Resolve all citations against one source snapshot. Never silently turn
        # a saved quote into a current-source assertion after replacement.
        response = {**response, 'sources': [dict(source) for source in response['sources']]}
        with self.documents.connect() as connection:
            connection.execute('BEGIN')
            for source in response['sources']:
                doc = connection.execute('SELECT revision,text FROM documents WHERE id=?', (source['document_id'],)).fetchone()
                parent = connection.execute('SELECT document_id,start_char,end_char FROM segments WHERE id=?', (source['id'],)).fetchone()
                current = (doc and parent and parent['document_id'] == source['document_id']
                    and doc['revision'] == source['revision']
                    and parent['start_char'] <= source['start_char'] < source['end_char'] <= parent['end_char']
                    and doc['text'][source['start_char']:source['end_char']] == source['text'])
                source['citation_state'] = 'current' if current else 'changed' if doc else 'deleted'
        return response

    def get(self, identity):
        with self.connect() as connection:
            connection.execute('BEGIN')
            metadata = self.metadata(connection, identity)
            if metadata is None:
                raise IngestionError('Conversation not found.', 404)
            turns = [dict(item) for item in connection.execute(
                'SELECT * FROM turns WHERE conversation_id=? ORDER BY ordinal', (identity,))]
        result = []
        for turn in turns:
            response = self.annotate(json.loads(turn['response_json']))
            result.append({**response, 'turn_id': turn['id'], 'created_at': turn['created_at'],
                'conversation_id': identity, 'conversation_revision': turn['ordinal']})
        return {**metadata, 'turns': result}

    def delete(self, identity):
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if not connection.execute('DELETE FROM conversations WHERE id=?', (identity,)).rowcount:
                raise IngestionError('Conversation not found.', 404)
