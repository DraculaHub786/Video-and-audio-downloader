import yt_dlp, sys

url = 'https://www.youtube.com/shorts/mn5cfMMquRQ'
opts = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'no_check_certificate': True,
    'extractor_args': {'youtube': {'player_client': ['android']}},
}
with yt_dlp.YoutubeDL(opts) as ydl:
    info = ydl.extract_info(url, download=False)
    formats = info.get('formats', [])
    print('TITLE:', info.get('title'))
    print('TOTAL FORMATS:', len(formats))
    print()
    print('PRE-MUXED (video+audio in one file):')
    for f in formats:
        vc = f.get('vcodec', 'none')
        ac = f.get('acodec', 'none')
        if vc != 'none' and ac != 'none':
            print(f"  id={f.get('format_id')} ext={f.get('ext')} h={f.get('height')} url_len={len(f.get('url',''))}")
    print()
    print('AUDIO ONLY:')
    for f in formats:
        vc = f.get('vcodec', 'none')
        ac = f.get('acodec', 'none')
        if vc == 'none' and ac != 'none':
            print(f"  id={f.get('format_id')} ext={f.get('ext')} abr={f.get('abr')}")
