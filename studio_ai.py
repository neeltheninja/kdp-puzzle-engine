"""Small OpenAI-compatible client. Credentials live in memory or environment only."""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

PROVIDERS = {
    'openrouter': {'name': 'OpenRouter', 'url': 'https://openrouter.ai/api/v1', 'env': 'OPENROUTER_API_KEY', 'docs': 'https://openrouter.ai/docs/quickstart'},
    'tokenharbor': {'name': 'Token Harbor', 'url': 'https://tokenharbor.ai/v1', 'env': 'TOKENHARBOR_API_KEY', 'docs': 'https://tokenharbor.ai/docs/api/curl'},
    'together': {'name': 'Together AI', 'url': 'https://api.together.ai/v1', 'env': 'TOGETHER_API_KEY', 'docs': 'https://docs.together.ai/docs/inference/openai-compatibility'},
    'deepseek': {'name': 'DeepSeek', 'url': 'https://api.deepseek.com', 'env': 'DEEPSEEK_API_KEY', 'docs': 'https://api-docs.deepseek.com/'},
    'ollama': {'name': 'Local Ollama', 'url': 'http://127.0.0.1:11434/v1', 'env': '', 'docs': 'https://docs.ollama.com/api/openai-compatibility'},
    'custom': {'name': 'Custom compatible endpoint', 'url': '', 'env': 'STUDIO_LLM_API_KEY', 'docs': ''},
}
CONNECTIONS = {}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Provider redirected the request. Use its final API base URL.')


def connection(data):
    provider = data.get('provider', 'ollama')
    if provider not in PROVIDERS:
        raise ValueError('Unknown AI provider.')
    config = {**CONNECTIONS.get(provider, {}), **data, 'provider': provider}
    config['url'] = PROVIDERS[provider]['url'] if provider != 'custom' else config.get('url', '').rstrip('/')
    parsed = urllib.parse.urlsplit(config['url'])
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('Use HTTPS for remote APIs; HTTP is allowed only for loopback services.')
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Enter a valid API base URL without credentials or query parameters.')
    previous = CONNECTIONS.get(provider, {})
    saved_key = previous.get('key', '') if previous.get('url') == config['url'] else ''
    config['key'] = data.get('key') or saved_key or os.environ.get(PROVIDERS[provider]['env'], '')
    if provider != 'ollama' and not config['key']:
        raise ValueError('Add an API key or set ' + PROVIDERS[provider]['env'] + '.')
    if len(config['key']) > 2048 or '\n' in config['key'] or '\r' in config['key']:
        raise ValueError('Invalid API key.')
    return config


def request(config, endpoint, payload=None):
    headers = {'Content-Type': 'application/json'}
    if config['key']:
        headers['Authorization'] = 'Bearer ' + config['key']
    req = urllib.request.Request(config['url'] + endpoint, headers=headers,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response:
            raw = response.read(32_000_001)
        if len(raw) > 32_000_000:
            raise ValueError('Provider response is too large.')
        result = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise ValueError(f'Provider returned HTTP {error.code}. Check the key, model access, credits, and endpoint. No automatic paid retry was made.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('Provider unavailable or timed out. Check its connection before retrying.') from None
    if not isinstance(result, dict) or result.get('error'):
        raise ValueError('Provider reported an error. Check its dashboard for details.')
    return result


def models(config, images=False):
    data = request(config, '/images/models' if images and config['provider'] == 'openrouter' else '/models')
    return [{'id': m['id'], 'name': m.get('name', m['id']), 'pricing': m.get('pricing', {}),
             'modalities': m.get('architecture', {}).get('output_modalities', [])}
            for m in data.get('data', []) if isinstance(m, dict) and isinstance(m.get('id'), str)]


def draft(config, brief, count, words, model):
    schema = {'title': 'Book title', 'subtitle': 'Short subtitle', 'author': 'E. P. Greenwood',
              'palette': 'nature', 'puzzles': [{'name': 'Specific topic', 'words': ['FOREST', 'FERN']}],
              'art_prompt': 'An original illustration idea, no typography',
              'design': {'bg':'#f4efe2','ink':'#203a26','accent':'#6b8e6b','highlight':'#ffd354','font':'serif','layout':'framed','pattern':'botanical'}}
    prompt = (f'Create exactly {count} distinct word-search puzzles with {words} unique real words each. '
              'All words must be English A-Z only, 3–15 letters, with no spaces. '
              'Use appropriate vocabulary for the audience. No fabricated words, brands, or duplicate puzzles. '
              'Suggest a coordinated six-digit hex palette. Design font must be sans, serif, or mono; '
              'layout must be framed, minimal, poster, split, band, or gallery; pattern must be plain, botanical, geometric, or waves. '
              'Return only a JSON object matching this shape: ' + json.dumps(schema) + '\nCreative brief: ' + brief)
    payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False,
               'max_tokens': min(12000, 800 + count * words * 14)}
    if config.get('json_mode'):
        payload['response_format'] = {'type': 'json_object'}
    result = request(config, '/chat/completions', payload)
    try:
        choice = result['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise ValueError('The model reached its output limit. Choose fewer puzzles or another model.')
        content = choice['message']['content']
        if not isinstance(content, str):
            raise ValueError('Model did not return text.')
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
        data = json.loads(content)
        if len(data.get('puzzles', [])) != count:
            raise ValueError('Model returned the wrong puzzle count. Edit the brief or choose another model.')
        if any(len(p.get('words', [])) != words for p in data['puzzles']):
            raise ValueError('Model returned the wrong word count. Choose another model or reduce the request.')
        data['ai_generated'] = True
        data['generation'] = {'provider': config['provider'], 'model': model}
        return data
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise ValueError('Model did not return valid theme JSON. Enable JSON mode if supported or choose another model.') from None


def image(config, prompt, model):
    if config['provider'] != 'openrouter':
        raise ValueError('Image generation currently uses the OpenRouter Image API. Other providers support theme text.')
    result = request(config, '/images', {'model': model, 'prompt': prompt})
    try:
        return base64.b64decode(result['data'][0]['b64_json'], validate=True)
    except (KeyError, IndexError, ValueError, TypeError):
        raise ValueError('The image model did not return a supported base64 image.') from None
