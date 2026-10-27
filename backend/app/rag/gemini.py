"""Bounded Gemini REST adapter. No automatic retries, tools, or local fallback."""

import http.client
import json
import time

from app.generation_config import settings
from app.ingestion import IngestionError

GEMINI_MODEL = 'gemini-3.1-flash-lite'
HOST = 'generativelanguage.googleapis.com'
MAX_OUTPUT_TOKENS = 1024


class GeminiClient:
    provider = 'gemini'
    requires_local_inference = False
    model_digest = None  # Hosted weights cannot be hash-pinned by this client.

    def __init__(self):
        config = settings()
        self.model = config.get('GEMINI_MODEL') or GEMINI_MODEL
        if self.model != GEMINI_MODEL:
            raise ValueError(f'This integration supports only {GEMINI_MODEL}; no paid-model fallback is configured.')
        self._api_key = config.get('GEMINI_API_KEY','').strip()
        if '\r' in self._api_key or '\n' in self._api_key or not self._api_key.isascii():
            raise ValueError('GEMINI_API_KEY must be a single ASCII value.')

    def inspect(self):
        # Local configuration only; this does not claim the key/quota was tested.
        return {'state': 'configured' if self._api_key else 'key_missing', 'provider': self.provider,
                'model': self.model, 'digest': None, 'connection_verified': False,
                'sends_context_to': HOST, 'output_token_limit': MAX_OUTPUT_TOKENS}

    def generate(self, messages, schema):
        if not self._api_key:
            raise IngestionError('Set a replacement GEMINI_API_KEY in the backend environment or ignored project .env, then restart the API.', 503)
        payload = {'systemInstruction': {'parts': [{'text': messages[0]['content']}]},
            'contents': [{'role': 'user', 'parts': [{'text': messages[1]['content']}]}],
            'generationConfig': {'temperature': 0, 'maxOutputTokens': MAX_OUTPUT_TOKENS,
                'responseFormat': {'text': {'mimeType': 'APPLICATION_JSON', 'schema': schema}}}}
        body = json.dumps(payload,ensure_ascii=False).encode('utf8')
        if len(body) > 16384:
            raise IngestionError('Gemini request exceeds the bounded prompt size.', 422)
        connection = http.client.HTTPSConnection(HOST,timeout=60)
        started = time.perf_counter()
        try:
            connection.request('POST',f'/v1beta/models/{self.model}:generateContent',body,
                {'Content-Type':'application/json','x-goog-api-key':self._api_key})
            response = connection.getresponse()
            data = response.read(65537)
            if len(data) > 65536:
                raise IngestionError('Gemini returned an oversized response.', 503)
            if response.status in (401,403):
                raise IngestionError('Gemini authentication was rejected. Check the replacement key and project permissions.', 503)
            if response.status == 429:
                raise IngestionError('Gemini quota or rate limit reached. No retry or provider fallback was attempted.', 429)
            if response.status != 200:
                raise IngestionError('Gemini request failed. Check the configured model/project and retry manually.', 503)
            value = json.loads(data)
            candidates = value.get('candidates',[])
            if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
                raise IngestionError('Gemini blocked or did not complete the answer. No partial answer was returned.', 503)
            parts = candidates[0].get('content',{}).get('parts',[])
            text = ''.join(part['text'] for part in parts if isinstance(part,dict) and isinstance(part.get('text'),str) and not part.get('thought'))
            if not text:
                raise ValueError('Missing response text')
            version = value.get('modelVersion')
            if version is not None and (not isinstance(version,str) or len(version)>160):
                raise ValueError('Invalid model version')
            usage = value.get('usageMetadata',{})
            counts = {key:usage[key] for key in ('promptTokenCount','candidatesTokenCount','totalTokenCount','thoughtsTokenCount')
                      if isinstance(usage,dict) and isinstance(usage.get(key),int) and usage[key]>=0}
            return {'message':{'content':text},'provider':self.provider,'model_version':version,
                    'usage_metadata':counts,'request_duration_ms':(time.perf_counter()-started)*1000}
        except IngestionError:
            raise
        except (OSError,http.client.HTTPException,ValueError,TypeError,AttributeError,KeyError) as error:
            # Never echo a provider error body, request headers, key, or prompt.
            raise IngestionError('Gemini could not be reached or returned an invalid response. No automatic retry was attempted.',503) from error
        finally:
            connection.close()
