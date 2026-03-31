# Troubleshooting YouTube Extraction Errors

## Error: "This video requires account login/age verification"

This error occurs when YouTube blocks automated downloaders or requires authentication. Here are the fixes applied:

### What I Fixed (Latest Update):

1. **Always-latest yt-dlp** - Automatically updates to latest version on every deploy and app start
2. **Enhanced browser headers** - Added more headers to mimic real browsers (Accept, Accept-Language, Sec-Fetch-Mode)
3. **Optimized player clients** - Using Android and Web clients (most reliable)
4. **Better fallback strategy** - Tries android_creator client as backup
5. **Age limit disabled** - Removes age restrictions where possible
6. **More retries** - Increased retry attempts from 2 to 3

### How It Works:

The app now uses a smarter YouTube extraction strategy:
- **First attempt**: Uses Android client (most reliable, bypasses many restrictions)
- **Fallback**: Uses android_creator and web clients with increased retries
- **Headers**: Mimics Chrome browser with all necessary headers

### Deploy Steps:

```bash
cd "c:\Users\afjal\Documents\Mini-Projects\video & audio downloader"
git add -A
git commit -m "Fix YouTube auth: use android client, enhance headers, auto-update yt-dlp"
git push
```

Then go to Render dashboard and wait for auto-redeploy (3-5 minutes).

### Testing:

After deployment, test with these videos in order:

1. **Public video (easy test)**:
   - `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
   
2. **YouTube Shorts (common use case)**:
   - Any shorts URL like `https://youtube.com/shorts/xxxxx`
   
3. **Recent video (bot detection test)**:
   - Try any recently uploaded video

### If it still fails:

#### Reasons why some videos may not work:

1. **Truly age-restricted videos** - Requires YouTube account login with verified age (impossible on cloud)
2. **Geoblocked content** - Only available in certain countries
3. **Private/Unlisted videos** - Only viewable by authorized users  
4. **Live streams** - May require special handling
5. **YouTube updated protection** - yt-dlp needs new update (usually fixed within hours/days)

#### What videos should work now:

✅ Public YouTube videos
✅ YouTube Shorts (now normalized to watch URLs)
✅ Most Instagram, TikTok, Twitter videos
✅ SoundCloud, Reddit videos
✅ Vimeo, Dailymotion, Facebook videos
✅ 1000+ other supported platforms

### Checking Logs in Render:

1. Go to your Render service
2. Click "Logs" tab
3. Look for these messages:
   - `yt-dlp version: ...` (should show latest version)
   - Any error messages containing `login`, `bot`, `age`
4. Share specific error messages for better diagnosis

### Advanced: For Persistent Age-Restricted Videos

If you absolutely need to download age-restricted content, you'll need YouTube cookies:

**Not recommended for public deployment (security risk), but possible:**

1. Export cookies from your browser using a cookies.txt browser extension
2. Add environment variable in Render: `YOUTUBE_COOKIES` (base64 encoded cookies.txt content)
3. The app would need modification to use these cookies

**Better alternative**: Tell users to download locally where they're logged into YouTube.

### Manual yt-dlp Update (Emergency):

If auto-update somehow fails, manually trigger in Render shell:

```bash
pip install --upgrade --force-reinstall yt-dlp
```

Then restart the service.

### Current App Configuration:

- **yt-dlp**: Auto-updates to latest on every deployment & restart
- **ffmpeg**: Bundled via imageio-ffmpeg
- **Rate limits**: 60 info requests/min, 20 downloads/min
- **Max file size**: 700 MB
- **Concurrent downloads**: 15 fragments simultaneously
- **Player clients**: android → android_creator → web (in order)
