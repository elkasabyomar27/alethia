"""Conservative context selection and explicit heuristic checks, not entailment."""

import json
import re

from app.ingestion import IngestionError
from app.rag.analyzer import tokenize
from app.rag.ollama import CONTEXT_TOKENS, OUTPUT_TOKENS

CONTEXT_VERSION = 'sentence-windows-v1'
ATTACK_PATTERNS = [
    r'ignore\s+(?:(?:all|any|the)\s+)?(?:previous|prior|system|above)\s+(?:instructions|rules)',
    r'ignore\s+(?:all|any)\s+(?:instructions|rules)',
    r'(?:reveal|print|show|leak)\s+(?:the\s+)?system\s+prompt',
    r'<\|(?:im_start|im_end|system|assistant)\|>|\[/?INST\]',
    r'^\s*(?:system|assistant)\s*:',
    r'تجاهل\s+(?:(?:كل|جميع)\s+)?(?:التعليمات|القواعد)',
]


def suspicious(text):
    return any(re.search(pattern, text, re.I | re.M) for pattern in ATTACK_PATTERNS)


def ambiguous_followup(question):
    text = question.strip().casefold().rstrip('?.؟!')
    return bool(re.fullmatch(r'(?:what about (?:it|that|this|those)|and (?:it|that|this)|how about (?:it|that)|'
        r'طب (?:وده|و ده|ده|دي)|طيب (?:وده|ده|دي)|وماذا عنه|وماذا عن ذلك)', text))


def missing_numeric_answer(question, claims):
    if not re.search(r'\bhow (?:many|much)\b|\b(?:كم|كام|بكام)\b', question, re.I):
        return False
    text = ' '.join(claim['text'] for claim in claims)
    return not re.search(r'\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|thirty)\b|'
        r'يومين|ساعتين|أسبوعين|اسبوعين|يومان|ساعتان', text, re.I)


def sentence_spans(text):
    spans = []
    start = 0
    for boundary in re.finditer(r'[.!?؟](?=\s|$)|\n\s*\n', text):
        end = boundary.end()
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    # A source's final unterminated sentence is usable as a whole, never clipped.
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def select_context(question, rows, schema, system):
    selected = []
    terms = set(tokenize(question))
    def messages():
        return [{'role': 'system', 'content': system + json.dumps(schema, ensure_ascii=False)},
            {'role': 'user', 'content': json.dumps({'sources': [{'id': item['source_id'], 'text': item['context_text']}
                for item in selected], 'question': question}, ensure_ascii=False)}]
    def size(): return len(json.dumps(messages(), ensure_ascii=False).encode('utf8'))
    budget = CONTEXT_TOKENS-OUTPUT_TOKENS-256
    if size() > budget:
        raise IngestionError('Question exceeds the conservative prompt budget. Shorten it.', 422)
    candidates = []
    for row in rows:
        if suspicious(row['text']):
            continue
        if any(row['id'] == old['id'] and max(0, min(row['end_char'], old['end_char'])-max(row['start_char'], old['start_char']))
               >= .6*min(len(row['text']), len(old['text'])) for old in candidates):
            continue
        candidates.append(row)
    windows = []
    for row in candidates:
        if len(selected) == 3:
            break
        spans = sentence_spans(row['text'])
        # Skip standalone Markdown headings as the starting evidence sentence.
        usable = [i for i,(start,end) in enumerate(spans) if len(row['text'][start:end].strip()) >= 12
                  and not row['text'][start:end].strip().startswith('#')]
        if not usable:
            continue
        ranked = sorted(usable, key=lambda i: (-len(terms & set(tokenize(row['text'][spans[i][0]:spans[i][1]]))), i))
        best_overlap = len(terms & set(tokenize(row['text'][spans[ranked[0]][0]:spans[ranked[0]][1]])))
        for seed in ranked:
            if len(terms & set(tokenize(row['text'][spans[seed][0]:spans[seed][1]]))) < best_overlap:
                break  # Do not substitute an unrelated shorter sentence just because it fits.
            start,end = spans[seed]
            item = {**row, 'source_id': f'S{len(selected)+1}', 'context_text': row['text'][start:end],
                    'start_char': row['start_char']+start}
            selected.append(item)
            if size() <= budget:
                windows.append([row,spans,seed,seed,item])
                break
            selected.pop()
    # Once useful seeds have been offered space, grow contiguous windows in
    # rounds. Exact source slices preserve exclusions/conditions when they fit.
    changed = True
    while changed:
        changed = False
        for window in windows:
            row,spans,left,right,item = window
            for new_left,new_right in ((left,right+1),(left-1,right)):
                if new_left < 0 or new_right >= len(spans):
                    continue
                old_text,old_start = item['context_text'],item['start_char']
                start,end = spans[new_left][0],spans[new_right][1]
                item['context_text'],item['start_char'] = row['text'][start:end],row['start_char']+start
                if size() <= budget:
                    window[2],window[3] = new_left,new_right
                    changed = True
                    break
                item['context_text'],item['start_char'] = old_text,old_start
    return messages(),schema,selected,size()
