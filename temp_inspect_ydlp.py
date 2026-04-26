import pathlib
import re
import yt_dlp

p = pathlib.Path(yt_dlp.__file__).resolve().parent

txt = (p / 'YoutubeDL.py').read_text(encoding='utf-8', errors='ignore')
m = re.search(r'def _clean_js_runtimes.*?def _js_runtimes', txt, re.S)
print(m.group(0)[:2500] if m else 'NO_JS_BLOCK')

src = (p / 'extractor' / 'youtube' / '_video.py').read_text(encoding='utf-8', errors='ignore')
needle = "for client in self._configuration_arg('player_client')"
i = src.find(needle)
print('---')
print(src[i-300:i+900] if i != -1 else 'NO_PLAYER_CLIENT_BLOCK')
